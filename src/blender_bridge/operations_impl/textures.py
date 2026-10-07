"""Actual UV-space camera projection and frozen high/low Cycles baking."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import uuid
import bpy
from mathutils import Vector
from .common import resolve, fingerprint, topology, write_json
from .surface import uv_triangles, raster_triangle
from ..operations import selected
from ..core import BridgeError, atomic_json


def save_raw_image(image,path):
    old=(image.filepath_raw,image.file_format)
    try:
        image.filepath_raw=str(path);image.file_format='PNG';image.save()
    finally:image.filepath_raw,image.file_format=old


def image_stats(image):
    import numpy as np
    pixels=np.empty(len(image.pixels),dtype=np.float32);image.pixels.foreach_get(pixels);pixels=pixels.reshape(-1,image.channels)
    rgb=pixels[:,:min(3,image.channels)]
    return {'width':image.size[0],'height':image.size[1],'channels':image.channels,'min':rgb.min(axis=0).tolist(),'max':rgb.max(axis=0).tolist(),
            'mean':rgb.mean(axis=0).tolist(),'std':rgb.std(axis=0).tolist(),'constant':bool((rgb.max(axis=0)-rgb.min(axis=0)<1e-5).all()),'finite':bool(np.isfinite(pixels).all())}


class TextureOps:
    def texture_project(self,object,views,path,resolution=512,background=(0,0,0,0),material=None):
        import numpy as np
        from bpy_extras.object_utils import world_to_camera_view
        ob=resolve(object,'MESH');output=self.state.output_path(path,'.png');scene=bpy.context.scene
        sources=[];temporary=[];old_res=(scene.render.resolution_x,scene.render.resolution_y,scene.render.pixel_aspect_x,scene.render.pixel_aspect_y)
        try:
            for view in views:
                cam=resolve(view['camera'],'CAMERA');source=self.state.input_path(view['image']);img=bpy.data.images.load(str(source),check_existing=False);temporary.append(img)
                if img.channels!=4:raise ValueError('Projection images must decode to RGBA')
                pixels=np.empty(len(img.pixels),dtype=np.float32);img.pixels.foreach_get(pixels)
                sources.append({'camera':cam,'pixels':pixels.reshape(img.size[1],img.size[0],4),'width':img.size[0],'height':img.size[1],
                                'weight':view.get('weight',1),'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'covered':0})
            result=np.zeros((resolution,resolution,4),dtype=np.float32);weights=np.zeros((resolution,resolution),dtype=np.float32);surface=np.zeros((resolution,resolution),dtype=bool)
            deps=bpy.context.evaluated_depsgraph_get();mesh=ob.data
            for tri,uv in uv_triangles(ob):
                vertices=[ob.matrix_world@mesh.vertices[i].co for i in tri.vertices]
                normal=(vertices[1]-vertices[0]).cross(vertices[2]-vertices[0]).normalized()
                for x,y,bary in raster_triangle(uv,resolution):
                    surface[y,x]=True;point=sum((p*w for p,w in zip(vertices,bary)),Vector())
                    for src in sources:
                        cam=src['camera'];scene.render.resolution_x=src['width'];scene.render.resolution_y=src['height'];scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1
                        ndc=world_to_camera_view(scene,cam,point)
                        if ndc.z<=0 or not (0<=ndc.x<1 and 0<=ndc.y<1):continue
                        to_camera=(cam.matrix_world.translation-point).normalized() if cam.data.type!='ORTHO' else cam.matrix_world.to_quaternion()@Vector((0,0,1))
                        facing=normal.dot(to_camera)
                        if facing<=.001:continue
                        # Ray from surface toward camera; any mesh surface in front occludes projection.
                        hit,loc,norm,face,hitob,matrix=scene.ray_cast(deps,point+to_camera*1e-4,to_camera,distance=(cam.matrix_world.translation-point).length)
                        if hit:continue
                        color=src['pixels'][min(src['height']-1,int(ndc.y*src['height'])),min(src['width']-1,int(ndc.x*src['width']))]
                        weight=src['weight']*facing*float(color[3])
                        if weight<=0:continue
                        result[y,x]+=color*weight;weights[y,x]+=weight;src['covered']+=1
            covered=weights>0;result[covered]/=weights[covered,None];result[~covered]=background
            image=bpy.data.images.new('__bb_projection_'+uuid.uuid4().hex,resolution,resolution,alpha=True);temporary.append(image)
            image.pixels.foreach_set(result.reshape(-1));image.update();save_raw_image(image,output)
            provenance={'object_hash':fingerprint(ob),'views':[{'camera':self._camera_record(s['camera'],s['width'],s['height']),'path':s['path'],'sha256':s['sha256'],'samples':s['covered']} for s in sources]}
            artifact=self.state.artifact(output,'image/png',provenance)
            counts={'surface_pixels':int(surface.sum()),'covered_pixels':int((surface&covered).sum()),'uncovered_pixels':int((surface&~covered).sum())}
            return {'image':artifact,'coverage':counts,'coverage_fraction':counts['covered_pixels']/counts['surface_pixels'] if counts['surface_pixels'] else 0,'backface_and_occlusion_tested':True,
                    'material_assignment':{'operation':'material.relink','args':{'material':material,'channel':'BaseColor','path':str(output)}} if material else None}
        finally:
            scene.render.resolution_x,scene.render.resolution_y,scene.render.pixel_aspect_x,scene.render.pixel_aspect_y=old_res
            for image in temporary:bpy.data.images.remove(image)

    def _bake_plan_path(self,plan_id):
        if not plan_id.isalnum():raise ValueError('Invalid plan ID')
        return self.state.output_root/'.bridge'/'bakes'/(plan_id+'.json')

    def _bake_plan(self,plan_id):
        path=self._bake_plan_path(plan_id)
        if not path.is_file():raise BridgeError('BAKE_PLAN_NOT_FOUND',plan_id)
        return json.loads(path.read_text(encoding='utf-8'))

    def bake_prepare(self,low,channels,directory,high=(),cage=None,resolution=1024,margin=8,ray_distance=.1):
        target=resolve(low,'MESH');sources=[resolve(o,'MESH') for o in high]
        if target in sources:raise ValueError('High and low must differ')
        if not target.data.uv_layers.active:raise BridgeError('UV_MISSING',low)
        if cage:
            shell=resolve(cage,'MESH')
            if topology(shell.data)!=topology(target.data):raise ValueError('Cage and low topology must match exactly')
        names=list(dict.fromkeys([low]+list(high)+([cage] if cage else [])));plan_id=uuid.uuid4().hex
        plan={'plan_id':plan_id,'low':low,'high':list(high),'cage':cage,'channels':channels,'directory':directory,'resolution':resolution,'margin':margin,'ray_distance':ray_distance,
              'hashes':{name:fingerprint(resolve(name)) for name in names},'state':'prepared','session':self.state.session,'revision':self.state.revision}
        atomic_json(self._bake_plan_path(plan_id),plan)
        return {**plan,'manifest':write_json(self.state,f'{directory}/bake-plan-{plan_id}.json',plan)}

    def bake_inspect(self,plan_id):
        plan=self._bake_plan(plan_id);stale=[]
        for name,digest in plan['hashes'].items():
            try:
                if fingerprint(resolve(name))!=digest:stale.append(name)
            except BridgeError:stale.append(name)
        return {**plan,'stale_sources':stale,'usable':not stale and plan['state']=='completed'}

    @contextmanager
    def _bake_channel_materials(self,objects,channel):
        """Temporarily route unsupported scalar channels through emission."""
        saved=[]
        try:
            if channel in ('Metallic','Opacity'):
                materials={s.material for ob in objects for s in ob.material_slots if s.material}
                for mat in materials:
                    if not mat.use_nodes:raise ValueError('PBR channel bake requires node materials')
                    tree=mat.node_tree;principled=next((n for n in tree.nodes if n.type=='BSDF_PRINCIPLED'),None);out=next((n for n in tree.nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output),None)
                    if not principled or not out:raise ValueError('Principled/output required for channel bake')
                    links=[(l.from_socket,l.to_socket) for l in out.inputs['Surface'].links];emit=tree.nodes.new('ShaderNodeEmission');saved.append((tree,emit,links,out))
                    socket=principled.inputs['Metallic' if channel=='Metallic' else 'Alpha']
                    if socket.is_linked:tree.links.new(socket.links[0].from_socket,emit.inputs['Color'])
                    else:value=socket.default_value;emit.inputs['Color'].default_value=(value,value,value,1)
                    tree.links.new(emit.outputs[0],out.inputs['Surface'])
            yield
        finally:
            for tree,emit,links,out in saved:
                tree.nodes.remove(emit)
                for a,b in links:tree.links.new(a,b)

    def bake_execute(self,plan_id):
        plan=self.bake_inspect(plan_id)
        if plan['stale_sources']:raise BridgeError('BAKE_SOURCE_CHANGED',','.join(plan['stale_sources']))
        if plan['state']!='prepared':raise BridgeError('BAKE_ALREADY_EXECUTED','Create a new frozen plan; never silently overwrite prior bake')
        low=resolve(plan['low'],'MESH');high=[resolve(o,'MESH') for o in plan['high']];scene=bpy.context.scene;render=scene.render;bake=render.bake
        props=('use_selected_to_active','use_cage','cage_object','cage_extrusion','max_ray_distance','margin','use_clear','use_pass_direct','use_pass_indirect','use_pass_color')
        settings={p:getattr(bake,p) for p in props};engine=render.engine;samples=scene.cycles.samples;device=scene.cycles.device
        temporary_mat=None;nodes=[];artifacts=[];plan['state']='running';atomic_json(self._bake_plan_path(plan_id),plan)
        try:
            if not low.data.materials:
                temporary_mat=bpy.data.materials.new('__bb_bake_mat_'+plan_id);temporary_mat.use_nodes=True;low.data.materials.append(temporary_mat)
            used_slots={p.material_index for p in low.data.polygons}
            used_materials={low.data.materials[i] if i<len(low.data.materials) else None for i in used_slots}
            if any(m is None or not m.use_nodes for m in used_materials):raise ValueError('Bake target faces must reference node materials')
            for mat in used_materials:
                tree=mat.node_tree;active=tree.nodes.active;selection=[n for n in tree.nodes if n.select];node=tree.nodes.new('ShaderNodeTexImage')
                nodes.append((tree,node,active,selection))
                for n in tree.nodes:n.select=False
                node.select=True;tree.nodes.active=node
            render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=32
            bake.use_selected_to_active=bool(high);bake.use_cage=bool(plan['cage']);bake.cage_object=resolve(plan['cage']) if plan['cage'] else None
            bake.cage_extrusion=plan['ray_distance'];bake.max_ray_distance=plan['ray_distance'];bake.margin=plan['margin'];bake.use_clear=True
            bake.use_pass_direct=False;bake.use_pass_indirect=False;bake.use_pass_color=True
            mapping={'Normal':'NORMAL','AO':'AO','BaseColor':'DIFFUSE','Roughness':'ROUGHNESS','Metallic':'EMIT','Emissive':'EMIT','Opacity':'EMIT'}
            with selected([low]+high):
                for channel in plan['channels']:
                    path=self.state.output_path(f'{plan["directory"]}/{channel}.png','.png')
                    image=bpy.data.images.new('__bb_bake_'+plan_id+'_'+channel,plan['resolution'],plan['resolution'],alpha=True)
                    try:
                        image.colorspace_settings.name='sRGB' if channel in ('BaseColor','Emissive') else 'Non-Color'
                        for tree,node,active,selection in nodes:node.image=image
                        with self._bake_channel_materials(high or [low],channel):
                            status=bpy.ops.object.bake(type=mapping[channel])
                        if 'FINISHED' not in status:raise BridgeError('BAKE_FAILED','Blender did not report FINISHED')
                        stats=image_stats(image)
                        if not stats['finite']:raise BridgeError('BAKE_INVALID_PIXELS','Non-finite pixels')
                        save_raw_image(image,path);artifact=self.state.artifact(path,'image/png',{'plan_id':plan_id,'channel':channel,'source_hashes':plan['hashes'],'statistics':stats,'colorspace':image.colorspace_settings.name})
                        artifacts.append(artifact)
                    finally:bpy.data.images.remove(image)
            plan.update(state='completed',artifacts=artifacts,semantic_quality='requires_image_review',warnings=['constant_channel_requires_contextual_review'] if any(a['provenance']['statistics']['constant'] for a in artifacts) else [])
        except Exception as exc:
            plan.update(state='failed',artifacts=artifacts,error={'code':getattr(exc,'code','BAKE_FAILED'),'message':str(exc)})
            raise
        finally:
            for tree,node,active,selection in nodes:
                tree.nodes.remove(node);tree.nodes.active=active
                for n in tree.nodes:n.select=n in selection
            if temporary_mat:low.data.materials.clear();bpy.data.materials.remove(temporary_mat)
            for prop,value in settings.items():setattr(bake,prop,value)
            render.engine=engine;scene.cycles.samples=samples;scene.cycles.device=device
            atomic_json(self._bake_plan_path(plan_id),plan)
        return plan
