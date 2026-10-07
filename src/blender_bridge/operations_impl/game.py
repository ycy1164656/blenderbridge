"""Preserved-source retopology candidates and explicit game/export packaging."""
import hashlib
import json
from pathlib import Path
import shutil
import uuid
import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .common import resolve, guarded, fingerprint, info, new_mesh, index_check, write_json
from .objects import duplicate_object
from .common import collection as destination
from ..operations import selected
from ..core import BridgeError


def evaluated_bvh(ob):
    ev=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
    try:
        mesh.calc_loop_triangles()
        return BVHTree.FromPolygons([ev.matrix_world@v.co for v in mesh.vertices],[tuple(t.vertices) for t in mesh.loop_triangles],all_triangles=True)
    finally:ev.to_mesh_clear()


class GameOps:
    def retopo_prepare(self,source,name,collection=None):
        ob=resolve(source,'MESH');copy=duplicate_object(ob,name,destination(collection))
        copy['bb_role']='game_low';copy['bb_high_source']=ob.get('bb_object_id',ob.name);copy['bb_high_hash']=fingerprint(ob)
        return {'candidate':info(copy),'source':info(ob),'source_hash':fingerprint(ob)}

    def retopo_remesh(self,object,method,voxel_size=.05,ratio=.5,faces=1000,allow_data_loss=False):
        ob=resolve(object,'MESH',True);guarded(ob,topology_change=True)
        if ob.get('bb_role') not in ('game_low','editable_work'):raise ValueError('Use retopo.prepare to preserve source before remeshing')
        if (ob.data.uv_layers or ob.vertex_groups) and not allow_data_loss:raise BridgeError('DATA_LOSS_CONFIRMATION_REQUIRED','UV and weight data may be invalidated; set allow_data_loss=true for this candidate')
        if method=='decimate' and ratio<=0:raise ValueError('Positive decimation ratio required')
        checkpoint=self.checkpoint_create('before_remesh',[ob.name]);before=info(ob)
        with selected([ob]):
            if method=='voxel':ob.data.remesh_voxel_size=voxel_size;bpy.ops.object.voxel_remesh()
            elif method=='decimate':
                mod=ob.modifiers.new('BridgeRetopoDecimate','DECIMATE');mod.ratio=ratio;bpy.ops.object.modifier_apply(modifier=mod.name)
            else:
                try:bpy.ops.object.quadriflow_remesh.get_rna_type()
                except Exception as exc:raise BridgeError('UNSUPPORTED_CAPABILITY','QuadriFlow not available') from exc
                status=bpy.ops.object.quadriflow_remesh(mode='FACES',target_faces=faces,use_mesh_symmetry=False,preserve_attributes=False)
                if 'FINISHED' not in status:raise BridgeError('RETOPO_FAILED','QuadriFlow did not finish')
        ob['bb_surface_data_state']='requires_revalidation'
        return {'before':before,'after':info(ob),'checkpoint':checkpoint,'invalidated':['selection','UV_validation','weights_validation','bake'],'method':method}

    def retopo_strip(self,name,first,second,target=None,collection=None):
        if len(first)!=len(second):raise ValueError('Strip rails must have equal length')
        n=len(first);ob=new_mesh(name,first+second,[(i,i+1,n+i+1,n+i) for i in range(n-1)],collection)
        ob['bb_role']='editable_work'
        if target:self.retopo_project(ob.name,target,max_distance=1e6)
        return info(ob)

    def retopo_project(self,object,target,max_distance,indices=None):
        ob=resolve(object,'MESH',True);high=resolve(target,'MESH')
        if ob==high:raise ValueError('Source and candidate must differ')
        region=indices if indices is not None else list(range(len(ob.data.vertices)));index_check(region,len(ob.data.vertices));guarded(ob,region)
        tree=evaluated_bvh(high);inv=ob.matrix_world.inverted();updates={};miss=[]
        for i in region:
            point,normal,face,distance=tree.find_nearest(ob.matrix_world@ob.data.vertices[i].co,max_distance)
            if point is None:miss.append(i)
            else:updates[i]=inv@point
        for i,point in updates.items():ob.data.vertices[i].co=point
        ob.data.update()
        return {'object':ob.name,'projected':len(updates),'unmatched_count':len(miss),'unmatched_sample':miss[:32],'source_hash':fingerprint(high)}

    def retopo_validate(self,object,source,max_distance=.02,max_triangles=50000):
        ob=resolve(object,'MESH');high=resolve(source,'MESH');tree=evaluated_bvh(high);deps=bpy.context.evaluated_depsgraph_get();ev=ob.evaluated_get(deps);mesh=ev.to_mesh()
        try:
            mesh.calc_loop_triangles();points=[ev.matrix_world@v.co for v in mesh.vertices]
            points += [sum((ev.matrix_world@mesh.vertices[i].co for i in tri.vertices),Vector())/3 for tri in mesh.loop_triangles]
            distances=[tree.find_nearest(p)[3] for p in points];distances=[d for d in distances if d is not None]
            worst=max(distances,default=0);triangles=len(mesh.loop_triangles)
        finally:ev.to_mesh_clear()
        return {'state':'passed' if distances and worst<=max_distance and triangles<=max_triangles else 'failed','object':ob.name,'source':high.name,
                'samples':len(distances),'max_deviation':worst,'rms_deviation':(sum(d*d for d in distances)/len(distances))**.5 if distances else None,
                'triangles':triangles,'limits':{'max_distance':max_distance,'max_triangles':max_triangles},'measurement':'evaluated vertices and triangle centers to high surface; not silhouette or joint acceptance'}

    def game_validate(self,objects,profile=None):
        profile=profile or {};unknown=set(profile)-{'max_triangles','max_materials','max_influences','require_uv','require_applied_scale','allow_open_mesh','target_skeleton','height_m','height_tolerance'}
        if unknown:raise ValueError('Unknown game profile fields: '+','.join(sorted(unknown)))
        issues=[];records=[];triangles=0
        for name in objects:
            ob=resolve(name);record=info(ob)
            if ob.type=='MESH':
                inspection=self.mesh_inspect(ob.name,mode='evaluated');triangles+=inspection['triangles'];record['health']=inspection['health']
                if inspection['health']['zero_area_faces']:issues.append({'object':ob.name,'code':'DEGENERATE_FACES'})
                if not profile.get('allow_open_mesh',False) and inspection['health']['non_manifold_edges']:issues.append({'object':ob.name,'code':'NON_MANIFOLD'})
                if profile.get('require_uv',True) and not ob.data.uv_layers:issues.append({'object':ob.name,'code':'UV_MISSING'})
                if len(ob.material_slots)>profile.get('max_materials',16):issues.append({'object':ob.name,'code':'MATERIAL_BUDGET'})
                if profile.get('require_applied_scale',True) and any(abs(s-1)>1e-5 for s in ob.scale):issues.append({'object':ob.name,'code':'UNAPPLIED_SCALE'})
                for mod in ob.modifiers:
                    if mod.type=='ARMATURE' and mod.object:
                        validation=self.rig_validate(ob.name,mod.object.name,profile.get('max_influences',4));record['weights']=validation
                        if validation['state']!='passed':issues.append({'object':ob.name,'code':'DEFORM_WEIGHTS'})
            records.append(record)
        if triangles>profile.get('max_triangles',100000):issues.append({'code':'TRIANGLE_BUDGET','triangles':triangles})
        meshes=[resolve(o) for o in objects if resolve(o).type=='MESH'];bounds=[o.matrix_world@Vector(v) for o in meshes for v in o.bound_box]
        height=(max(v.z for v in bounds)-min(v.z for v in bounds))*bpy.context.scene.unit_settings.scale_length if bounds else None
        if 'height_m' in profile and (height is None or abs(height-profile['height_m'])>profile.get('height_tolerance',.01)):issues.append({'code':'HEIGHT_MISMATCH','height_m':height})
        unknowns=['collision_acceptance','target_engine_import','art_reference_match','joint_deformation_review']
        if profile.get('target_skeleton'):unknowns.append('target_skeleton_mapping_requires_external_bone_contract')
        return {'state':'passed' if not issues else 'failed','profile':profile,'objects':records,'triangles':triangles,'height_m':height,'issues':issues,'not_validated':unknowns,'ue_validation':'not_run'}

    def game_lod(self,object,ratios,collection=None):
        source=resolve(object,'MESH');results=[]
        if any(r<=0 for r in ratios):raise ValueError('LOD ratio must be positive')
        for index,ratio in enumerate(ratios,1):
            name=source.name+'_LOD'+str(index)
            if name in bpy.data.objects:raise ValueError('LOD name conflict: '+name)
        for index,ratio in enumerate(ratios,1):
            copy=duplicate_object(source,source.name+'_LOD'+str(index),destination(collection))
            mod=copy.modifiers.new('BridgeLOD','DECIMATE');mod.ratio=ratio
            with selected([copy]):bpy.ops.object.modifier_apply(modifier=mod.name)
            results.append({'object':info(copy),'ratio':ratio,'deviation':self.retopo_validate(copy.name,source.name)})
        return {'lods':results,'source_preserved':True}

    def game_collision(self,object,name,kind='convex',collection=None):
        source=resolve(object,'MESH');ev=source.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
        try:points=[ev.matrix_world@v.co for v in mesh.vertices]
        finally:ev.to_mesh_clear()
        if kind=='box':
            low=[min(p[i] for p in points) for i in range(3)];high=[max(p[i] for p in points) for i in range(3)]
            vertices=[(x,y,z) for x in (low[0],high[0]) for y in (low[1],high[1]) for z in (low[2],high[2])]
            faces=[(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6)]
        else:
            bm=bmesh.new()
            try:
                for point in points:bm.verts.new(point)
                result=bmesh.ops.convex_hull(bm,input=list(bm.verts),use_existing_faces=False)
                unused=[e for e in result['geom_unused']+result['geom_interior'] if isinstance(e,bmesh.types.BMVert) and e.is_valid]
                if unused:bmesh.ops.delete(bm,geom=unused,context='VERTS')
                bm.verts.ensure_lookup_table();bm.verts.index_update();vertices=[list(v.co) for v in bm.verts];faces=[tuple(v.index for v in f.verts) for f in bm.faces]
            finally:bm.free()
        ob=new_mesh(name,vertices,faces,collection);ob['bb_role']='collision';ob['bb_collision_source']=source.name
        return {'object':info(ob),'kind':kind,'ue_name_valid':name.startswith('UCX_'+source.name+'_') if kind=='convex' else name.startswith('UBX_'+source.name+'_')}

    def export_package(self,objects,directory,formats=('fbx','glb'),animation=False,frame_start=None,frame_end=None,profile=None):
        obs=[resolve(o) for o in objects]
        dependencies={o.parent for o in obs if o.parent}|{m.object for o in obs for m in o.modifiers if m.type=='ARMATURE' and m.object}
        missing=dependencies-set(obs)
        if missing:raise ValueError('Explicit export set must include dependencies: '+','.join(o.name for o in missing))
        if (frame_start is None)!=(frame_end is None) or frame_start is not None and (not animation or frame_start>frame_end):raise ValueError('Invalid explicit animation range')
        scene=bpy.context.scene;old_range=(scene.frame_start,scene.frame_end,scene.frame_current);images={};textures=[];artifacts=[]
        for ob in obs:
            for slot in ob.material_slots:
                if slot.material and slot.material.use_nodes:
                    for node in slot.material.node_tree.nodes:
                        if node.type=='TEX_IMAGE' and node.image:images[node.image]=node.image.filepath
        try:
            for index,(img,original) in enumerate(images.items()):
                if img.source not in ('FILE','GENERATED'):raise ValueError('Only single FILE or GENERATED textures supported by package')
                from .textures import save_raw_image
                path=self.state.output_path(f'{directory}/textures/{index:03d}.png','.png')
                save_raw_image(img,path)
                textures.append(self.state.artifact(path,'image/png',{'image':img.name,'original_path':original,'colorspace':img.colorspace_settings.name}))
                img.filepath=str(path)
            if frame_start is not None:scene.frame_start=frame_start;scene.frame_end=frame_end
            source=self._save_source(obs,f'{directory}/source.blend');artifacts.append(source)
            for fmt in formats:
                if fmt=='fbx':artifact=self.legacy.export_fbx(objects,f'{directory}/asset.fbx',animation,False,frame_start,frame_end)
                else:
                    output=self.state.output_path(f'{directory}/asset.{fmt}','.'+fmt)
                    with selected(obs):
                        if fmt=='glb':bpy.ops.export_scene.gltf(filepath=str(output),export_format='GLB',use_selection=True,export_animations=animation,export_frame_range=True,export_apply=True)
                        else:bpy.ops.wm.obj_export(filepath=str(output),export_selected_objects=True,export_uv=True,export_materials=True,forward_axis='NEGATIVE_Y',up_axis='Z')
                    artifact=self.state.artifact(output,'model/gltf-binary' if fmt=='glb' else 'model/obj')
                artifacts.append(artifact)
                if fmt=='obj':
                    sidecar=Path(artifact['path']).with_suffix('.mtl')
                    if sidecar.is_file():artifacts.append(self.state.artifact(sidecar,'model/mtl'))
        finally:
            for img,path in images.items():img.filepath=path
            scene.frame_start,scene.frame_end=old_range[:2];scene.frame_set(old_range[2])
        manifest={'schema_version':1,'delivery_id':uuid.uuid4().hex,'source':source,'artifacts':artifacts,'textures':textures,
                  'objects':[info(o) for o in obs],'source_hashes':{o.name:fingerprint(o) for o in obs},'profile':profile or {},
                  'animation':{'enabled':animation,'frame_range':[frame_start or scene.frame_start,frame_end or scene.frame_end],'fps':scene.render.fps/scene.render.fps_base},
                  'coordinate_convention':'+Z up, front -Y; meters scaled by scene units','scale_length':scene.unit_settings.scale_length,
                  'technical_validation':self.game_validate(objects,profile),'independent_readback':'not_run','visual_self_review':'not_run','user_visual_acceptance':'pending','ue_validation':'not_run'}
        artifact=write_json(self.state,f'{directory}/delivery.json',manifest)
        return {**manifest,'manifest':artifact}

    def export_prepare_ue(self,manifest,destination='/ShooterRoyal/Generated'):
        source=self.state.input_path(manifest);data=json.loads(source.read_text(encoding='utf-8'))
        if not destination.startswith('/ShooterRoyal/'):raise ValueError('Plan destination must be under /ShooterRoyal/')
        plan={'delivery_id':data['delivery_id'],'destination':destination,'files':data['artifacts'],'source_units':data['scale_length'],
              'actions':['核对尺寸与朝向','按目标骨架核对重定向映射','显式确认导入资产白名单','导入后检查材质、碰撞、LOD、动画与运行时表现'],
              'status':'plan_only','content_written':False,'ue_validation':'not_run'}
        return write_json(self.state,f'ue-plans/{data["delivery_id"]}-{uuid.uuid4().hex[:8]}.json',plan)
