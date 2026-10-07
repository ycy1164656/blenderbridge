import json
import math
import uuid
import bpy
import bmesh
from mathutils import Vector
from ..core import BridgeError
from .common import Base, resolve, identify, info, topology, part_map, save_parts, fingerprint, index_check


class SelectionOps(Base):
    def part_register(self,part_id,objects,indices=None,source='explicit',role=''):
        parts=part_map()
        if part_id in parts:raise BridgeError('NAME_CONFLICT',part_id)
        obs=[resolve(n,writable=True) for n in objects]
        if indices is not None:
            if len(obs)!=1 or obs[0].type!='MESH':raise ValueError('Region part requires exactly one mesh')
            index_check(indices,len(obs[0].data.vertices))
        for ob in obs:identify(ob)
        parts[part_id]={'part_id':part_id,'object_ids':[o['bb_object_id'] for o in obs],'indices':indices,'source':source,'role':role,'locked':False,'mapping_status':'current',
                        'topology_revision':topology(obs[0].data) if indices is not None else None}
        save_parts(parts);return parts[part_id]

    def part_assign_region(self,part_id,object,indices):
        parts=part_map()
        if part_id not in parts:raise BridgeError('PART_NOT_FOUND',part_id)
        if parts[part_id]['locked']:raise BridgeError('PROTECTED_REGION_TOUCHED','Unlock before redefining a protected region')
        ob=resolve(object,'MESH',True);index_check(indices,len(ob.data.vertices));identify(ob)
        parts[part_id].update(object_ids=[ob['bb_object_id']],indices=indices,topology_revision=topology(ob.data),mapping_status='current')
        save_parts(parts);return parts[part_id]

    def part_inspect(self,part_id=None):
        parts=part_map()
        if part_id is not None:
            if part_id not in parts:raise BridgeError('PART_NOT_FOUND',part_id)
            parts={part_id:parts[part_id]}
        results=[]
        for part in parts.values():
            part=dict(part)
            try:
                obs=[resolve(oid) for oid in part['object_ids']]
                part['object_names']=[o.name for o in obs]
                if part.get('indices') is not None and (len(obs)!=1 or topology(obs[0].data)!=part['topology_revision']):part['mapping_status']='stale'
            except BridgeError:part['mapping_status']='missing_object'
            results.append(part)
        return {'parts':results}

    def part_lock(self,part_id):
        parts=part_map();part=self.part_inspect(part_id)['parts'][0]
        if part['mapping_status']!='current':raise BridgeError('STALE_SELECTION','Part mapping must be rebuilt before locking')
        parts[part_id]['locked']=True
        parts[part_id]['locked_hashes']={oid:fingerprint(resolve(oid),part.get('indices')) for oid in part['object_ids']}
        save_parts(parts);return parts[part_id]

    def part_unlock(self,part_id):
        parts=part_map()
        if part_id not in parts:raise BridgeError('PART_NOT_FOUND',part_id)
        parts[part_id]['locked']=False;save_parts(parts);return parts[part_id]

    def _save_selection(self,ob,indices,source):
        if not ob.get('bb_object_id'):raise BridgeError('IDENTITY_REQUIRED','Call scene.identify before creating persistent selections')
        indices=sorted(set(indices));sid=str(uuid.uuid4())
        self.state.selections[sid]={'selection_id':sid,'object_id':ob['bb_object_id'],'mesh_id':ob.data.get('bb_mesh_id'),'topology_revision':topology(ob.data),'session':self.state.session,'indices':indices,'source':source}
        points=[ob.matrix_world@ob.data.vertices[i].co for i in indices]
        return {'selection_id':sid,'object_id':ob['bb_object_id'],'object':ob.name,'count':len(indices),'sample_indices':indices[:32],'topology_revision':topology(ob.data),
                'bounds_world':[[min(p[j] for p in points) for j in range(3)],[max(p[j] for p in points) for j in range(3)]] if points else None}

    def _selection(self,selection_id):
        saved=self.state.selections.get(selection_id)
        if not saved or saved['session']!=self.state.session:raise BridgeError('STALE_SELECTION','Selection is not valid in this session')
        ob=resolve(saved['object_id'],'MESH')
        if ob.data.get('bb_mesh_id')!=saved['mesh_id'] or topology(ob.data)!=saved['topology_revision']:raise BridgeError('STALE_SELECTION','Topology or mesh identity changed; query a new selection')
        return saved

    def selection_query(self,objects=None,part_id=None,indices=None,box_min=None,box_max=None,center=None,radius=None,height_range=None,normal=None,angle_degrees=45,material=None,vertex_group=None,connected_from=None,boundary=None,sharp_angle=None,space='world'):
        region=None
        if part_id:
            p=self.part_inspect(part_id)['parts'][0]
            if p['mapping_status']!='current':raise BridgeError('STALE_SELECTION','Part region is stale')
            if objects:raise ValueError('Use objects or part_id')
            objects=p['object_ids'];region=p.get('indices')
        if not objects:raise ValueError('Explicit objects or part_id required')
        if (box_min is None)!=(box_max is None) or (center is None)!=(radius is None):raise ValueError('Incomplete spatial predicate')
        results=[]
        for name in objects:
            ob=resolve(name,'MESH');chosen=set(range(len(ob.data.vertices)))
            if indices is not None:index_check(indices,len(ob.data.vertices));chosen&=set(indices)
            if region is not None:chosen&=set(region)
            def co(v):return ob.matrix_world@v.co if space=='world' else v.co
            if box_min is not None:chosen={i for i in chosen if all(box_min[j]<=co(ob.data.vertices[i])[j]<=box_max[j] for j in range(3))}
            if center is not None:chosen={i for i in chosen if (co(ob.data.vertices[i])-Vector(center)).length<=radius}
            if height_range is not None:chosen={i for i in chosen if height_range[0]<=co(ob.data.vertices[i]).z<=height_range[1]}
            if normal is not None:
                n=Vector(normal)
                if n.length<1e-8:raise ValueError('Normal must be nonzero')
                n.normalize();mat=ob.matrix_world.to_3x3().inverted().transposed()
                chosen={i for i in chosen if (mat@ob.data.vertices[i].normal if space=='world' else ob.data.vertices[i].normal).normalized().dot(n)>=math.cos(math.radians(angle_degrees))}
            if material:
                slots={i for i,m in enumerate(ob.data.materials) if m and m.name==material}
                chosen&={v for p in ob.data.polygons if p.material_index in slots for v in p.vertices}
            if vertex_group:
                group=ob.vertex_groups.get(vertex_group)
                if group is None:raise ValueError('Vertex group not found')
                chosen={i for i in chosen if any(g.group==group.index and g.weight>0 for g in ob.data.vertices[i].groups)}
            if connected_from is not None:
                index_check([connected_from],len(ob.data.vertices));neighbors={i:set() for i in range(len(ob.data.vertices))}
                for e in ob.data.edges:a,b=e.vertices;neighbors[a].add(b);neighbors[b].add(a)
                visited={connected_from};todo=[connected_from]
                while todo:
                    for v in neighbors[todo.pop()]-visited:visited.add(v);todo.append(v)
                chosen&=visited
            if boundary is not None or sharp_angle is not None:
                bm=bmesh.new()
                try:
                    bm.from_mesh(ob.data);bm.verts.ensure_lookup_table()
                    if boundary is not None:
                        edge_vertices={v.index for e in bm.edges if e.is_boundary for v in e.verts}
                        chosen=chosen&edge_vertices if boundary else chosen-edge_vertices
                    if sharp_angle is not None:chosen&={v.index for e in bm.edges if e.calc_face_angle(math.pi)>=math.radians(sharp_angle) for v in e.verts}
                finally:bm.free()
            results.append(self._save_selection(ob,chosen,'query'))
        return results[0] if len(results)==1 else {'selections':results}

    def selection_combine(self,selections,mode,steps=1):
        items=[self._selection(s) for s in selections]
        if len({x['object_id'] for x in items})!=1:raise ValueError('Selection combination requires one mesh')
        ob=resolve(items[0]['object_id'],'MESH');values=[set(x['indices']) for x in items];result=values[0]
        for value in values[1:]:
            if mode=='union':result|=value
            elif mode=='intersection':result&=value
            elif mode=='difference':result-=value
            else:raise ValueError('Grow/shrink accepts a single selection')
        if mode in ('grow','shrink'):
            neighbors={i:set() for i in range(len(ob.data.vertices))}
            for e in ob.data.edges:a,b=e.vertices;neighbors[a].add(b);neighbors[b].add(a)
            for _ in range(steps):
                result=result|{n for i in result for n in neighbors[i]} if mode=='grow' else {i for i in result if neighbors[i]<=result}
        return self._save_selection(ob,result,mode)

    def _image_camera(self,artifact_id):
        artifact=self.state.artifacts.get(artifact_id);meta=(artifact or {}).get('provenance')
        if not meta or not meta.get('camera'):raise BridgeError('ARTIFACT_INVALID','Registered camera-backed render required')
        cam=resolve(meta['camera'],'CAMERA')
        if self._camera_record(cam,meta['width'],meta['height'])!=meta['camera_state']:raise BridgeError('REVIEW_STALE','Camera changed after rendering')
        for name,digest in meta['object_hashes'].items():
            if fingerprint(resolve(name))!=digest:raise BridgeError('REVIEW_STALE','Geometry changed after rendering')
        if meta.get('environment') is not None and self._environment_record(meta['style'])!=meta['environment']:raise BridgeError('REVIEW_STALE','Render environment changed after rendering')
        return cam,meta

    def _ray(self,cam,meta,pixel):
        projection=cam.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),x=meta['width'],y=meta['height'],scale_x=1,scale_y=1)
        inverse=(projection@cam.matrix_world.inverted()).inverted()
        x=2*(pixel[0]+.5)/meta['width']-1;y=1-2*(pixel[1]+.5)/meta['height']
        near=inverse@Vector((x,y,-1,1));far=inverse@Vector((x,y,1,1));near=near.xyz/near.w;far=far.xyz/far.w
        origin=near if cam.data.type=='ORTHO' else cam.matrix_world.translation.copy()
        return origin,(far-origin).normalized()

    def _ray_hits(self,objects,origin,direction):
        hits=[];deps=bpy.context.evaluated_depsgraph_get()
        for ob in objects:
            ev=ob.evaluated_get(deps);inv=ob.matrix_world.inverted();local_direction=(inv.to_3x3()@direction).normalized()
            success,point,normal,index=ev.ray_cast(inv@origin,local_direction)
            if success:
                world=ob.matrix_world@point;hits.append((float((world-origin).length),ob,world,index))
        return sorted(hits,key=lambda x:x[0])

    def selection_pick(self,artifact_id,objects,pixel=None,rectangle=None,radius=.05,visible_only=True,image_transform=None):
        if (pixel is None)==(rectangle is None):raise ValueError('Specify pixel or rectangle')
        cam,meta=self._image_camera(artifact_id);obs=[resolve(o,'MESH') for o in objects]
        if image_transform:
            x0,y0,x1,y1=image_transform['source_rectangle'];dw,dh=image_transform['display_size']
            if not 0<=x0<x1<=meta['width'] or not 0<=y0<y1<=meta['height'] or dw<=0 or dh<=0:raise ValueError('Invalid source crop or display dimensions')
            if pixel is not None:
                if not 0<=pixel[0]<dw or not 0<=pixel[1]<dh:raise ValueError('Pixel outside displayed image')
                pixel=[x0+(pixel[0]+.5)*(x1-x0)/dw-.5,y0+(pixel[1]+.5)*(y1-y0)/dh-.5]
            else:
                if not 0<=rectangle[0]<rectangle[2]<=dw or not 0<=rectangle[1]<rectangle[3]<=dh:raise ValueError('Rectangle outside displayed image')
                rectangle=[x0+rectangle[0]*(x1-x0)/dw,y0+rectangle[1]*(y1-y0)/dh,x0+rectangle[2]*(x1-x0)/dw,y0+rectangle[3]*(y1-y0)/dh]
        if set(o.name for o in obs)-set(meta['object_hashes']):raise ValueError('Pick objects must be in the registered image subject')
        results=[];hit_report=[]
        if pixel is not None:
            if not 0<=pixel[0]<meta['width'] or not 0<=pixel[1]<meta['height']:raise ValueError('Pixel outside image')
            origin,direction=self._ray(cam,meta,pixel);hits=self._ray_hits(obs,origin,direction)
            if visible_only:hits=hits[:1]
            for distance,ob,point,index in hits:
                chosen=[v.index for v in ob.data.vertices if (ob.matrix_world@v.co-point).length<=radius]
                hit_report.append({'object':ob.name,'world':list(point),'evaluated_face_index':index,'base_mapping':'world_space_radius','distance':distance})
                results.append(self._save_selection(ob,chosen,'image_ray_radius'))
        else:
            from bpy_extras.object_utils import world_to_camera_view
            x0,y0,x1,y1=rectangle
            if x0>=x1 or y0>=y1:raise ValueError('Invalid rectangle')
            # Projection must use the image aspect, not unrelated current render settings.
            scene=bpy.context.scene;old=(scene.render.resolution_x,scene.render.resolution_y,scene.render.pixel_aspect_x,scene.render.pixel_aspect_y)
            scene.render.resolution_x=meta['width'];scene.render.resolution_y=meta['height'];scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1
            try:
              for ob in obs:
                chosen=[]
                for v in ob.data.vertices:
                    world=ob.matrix_world@v.co;ndc=world_to_camera_view(scene,cam,world)
                    px=ndc.x*meta['width'];py=(1-ndc.y)*meta['height']
                    if ndc.z<=0 or not (x0<=px<=x1 and y0<=py<=y1):continue
                    if visible_only:
                        origin,direction=self._ray(cam,meta,(px,py));hits=self._ray_hits(obs,origin,direction)
                        if hits and hits[0][0]<(world-origin).length-max(.001,radius):continue
                    chosen.append(v.index)
                results.append(self._save_selection(ob,chosen,'image_rectangle'))
            finally:scene.render.resolution_x,scene.render.resolution_y,scene.render.pixel_aspect_x,scene.render.pixel_aspect_y=old
        return {'selections':results,'hits':hit_report,'evaluated_indices_are_editable':False,'source_pixel':pixel,'source_rectangle':rectangle,'image_transform':image_transform}

    def selection_preview(self,selection_id,camera,path,width=960,height=540):
        selected=self._selection(selection_id);source=resolve(selected['object_id'],'MESH')
        copy=source.copy();copy.data=source.data.copy();copy.name='__bb_selection_'+uuid.uuid4().hex[:8];bpy.context.scene.collection.objects.link(copy)
        materials=[]
        try:
            copy.data.materials.clear()
            for name,color in [('Base',(.35,.38,.42,1)),('Selection',(1,.12,.03,1))]:
                mat=bpy.data.materials.new(copy.name+'_'+name);mat.diffuse_color=color;materials.append(mat);copy.data.materials.append(mat)
            indices=set(selected['indices'])
            for p in copy.data.polygons:p.material_index=int(bool(set(p.vertices)&indices))
            artifact=self.preview_render(camera,path,width,height,style='parts',objects=[copy.name])
            artifact['selection_id']=selection_id
            return artifact
        finally:
            mesh=copy.data;bpy.data.objects.remove(copy,do_unlink=True);bpy.data.meshes.remove(mesh)
            for material in materials:bpy.data.materials.remove(material)
