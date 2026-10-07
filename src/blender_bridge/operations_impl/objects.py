import hashlib
import json
from pathlib import Path
import uuid
import bpy
from mathutils import Matrix, Vector, Euler
from ..core import BridgeError
from .common import Base, resolve, identify, info, collection, guarded, fingerprint, part_map, save_parts


def duplicate_object(ob,name,dest,linked=False):
    if name in bpy.data.objects:raise BridgeError('NAME_CONFLICT',name)
    copy=ob.copy();copy.name=name
    if ob.data and not linked:copy.data=ob.data.copy()
    copy['bb_object_id']=str(uuid.uuid4())
    if copy.data and not linked:copy.data['bb_mesh_id']=str(uuid.uuid4())
    copy['bb_source_object_id']=ob.get('bb_object_id',ob.name)
    dest.objects.link(copy)
    return copy


class ObjectOps(Base):
    def scene_identify(self,objects):
        return {'objects':[info(identify(resolve(n,writable=True))) for n in objects]}

    def scene_fingerprint(self,objects):
        bpy.context.view_layer.update()
        return {'objects':{n:{'name':resolve(n).name,'object_id':resolve(n).get('bb_object_id'),'sha256':fingerprint(resolve(n))} for n in objects}}

    def scene_capabilities(self):
        from ..catalog import OPS
        from .. import __version__
        import sys
        imports={}
        for fmt,path in {'glb':('import_scene','gltf'),'fbx':('import_scene','fbx'),'obj':('wm','obj_import')}.items():
            try:getattr(getattr(bpy.ops,path[0]),path[1]).get_rna_type();imports[fmt]='available'
            except Exception:imports[fmt]='unsupported_capability'
        renders=[e.identifier for e in bpy.context.scene.render.bl_rna.properties['engine'].enum_items]
        return {'bridge_version':__version__,'blender':bpy.app.version_string,'python':sys.version,
                'binary':bpy.app.binary_path,'background':bpy.app.background,'render_engines':renders,
                'importers':imports,'blend_append':'available','operations':[n for n,v in OPS.items() if v['execution_domain']=='blender_main_thread' and (hasattr(self,n.replace('.','_')) or hasattr(self.legacy,n.replace('.','_'))) and (n!='python.execute' or self.state.allow_python)],
                'visual_review':'requires_actual_agent_image_review','probe_is_runtime_acceptance':False,
                'sculpt_implementation':'geometry_with_masks','native_brush_replay':'not_implemented','neural_3d_required':False}

    def scene_configure(self,unit_system=None,scale_length=None,world_color=None,samples=None):
        scene=bpy.context.scene
        if unit_system is not None:scene.unit_settings.system=unit_system
        if scale_length is not None:scene.unit_settings.scale_length=scale_length
        if world_color is not None:
            if scene.world is None:scene.world=bpy.data.worlds.new('BridgeWorld')
            scene.world.color=world_color;scene.world.use_nodes=True
            background=scene.world.node_tree.nodes.get('Background')
            if background:background.inputs['Color'].default_value=(*world_color,1)
        if samples is not None:scene.cycles.samples=samples
        return {'units':scene.unit_settings.system,'scale_length':scene.unit_settings.scale_length,'samples':scene.cycles.samples}

    def object_inspect(self,object):return info(resolve(object))

    def object_transform(self,object,location=None,rotation=None,scale=None,apply=False,space='local',apply_location=None,apply_rotation=None,apply_scale=None):
        flags=(apply,)*3 if apply else tuple(bool(x) for x in (apply_location,apply_rotation,apply_scale))
        ob=resolve(object,writable=any(flags));guarded(ob)
        if ob.library:raise BridgeError('LINKED_READ_ONLY',ob.name)
        for child in ob.children_recursive:guarded(child)
        if apply and any(x is not None for x in (apply_location,apply_rotation,apply_scale)):
            raise ValueError('Legacy apply=true cannot be combined with per-channel apply flags')
        if space=='world':
            loc,rot,scl=ob.matrix_world.decompose()
            ob.matrix_world=Matrix.LocRotScale(Vector(location) if location is not None else loc,Euler(rotation,'XYZ').to_quaternion() if rotation is not None else rot,Vector(scale) if scale is not None else scl)
        else:
            if location is not None:ob.location=location
            if rotation is not None:ob.rotation_mode='XYZ';ob.rotation_euler=rotation
            if scale is not None:ob.scale=scale
        if any(flags):
            from ..operations import selected
            with selected([ob]):bpy.ops.object.transform_apply(location=flags[0],rotation=flags[1],scale=flags[2])
        bpy.context.view_layer.update();return info(ob)

    def object_duplicate(self,object,name,linked=False,children=False,collection=None):
        source=resolve(object);dest=globals()['collection'](collection)
        obs=[source]+list(source.children_recursive) if children else [source]
        names={o:name if o==source else name+'__'+o.name for o in obs}
        if any(n in bpy.data.objects for n in names.values()):raise BridgeError('NAME_CONFLICT','Duplicate names already exist')
        copies={ob:duplicate_object(ob,names[ob],dest,linked) for ob in obs}
        for ob,copy in copies.items():
            world=copy.matrix_world.copy()
            if ob.parent in copies:copy.parent=copies[ob.parent]
            for modifier in copy.modifiers:
                if hasattr(modifier,'object') and modifier.object in copies:modifier.object=copies[modifier.object]
            copy.matrix_world=world
        return {'objects':[info(c) for c in copies.values()],'mapping':{o.get('bb_object_id',o.name):c['bb_object_id'] for o,c in copies.items()}}

    def object_make_single_user(self,object):
        ob=resolve(object);guarded(ob)
        if ob.library:raise BridgeError('LINKED_READ_ONLY','Linked objects cannot be copied in place')
        if ob.data:
            ob.data=ob.data.copy();ob.data['bb_mesh_id']=str(uuid.uuid4())
        identify(ob);return info(ob)

    def object_rename(self,object,name):
        ob=resolve(object,writable=True)
        if name in bpy.data.objects and bpy.data.objects[name]!=ob:raise BridgeError('NAME_CONFLICT',name)
        old=ob.name;ob.name=name
        return {'old_name':old,**info(ob)}

    def object_delete(self,objects,confirm=False):
        obs=[resolve(n) for n in objects];preview=[info(o) for o in obs]
        if not confirm:return {'deleted':False,'preview':preview}
        for ob in obs:
            if ob.library:raise BridgeError('LINKED_READ_ONLY',ob.name)
            guarded(ob,topology_change=True)
        ids={o.get('bb_object_id') for o in obs};parts=part_map()
        for part in parts.values():
            if ids&set(part['object_ids']):
                part['object_ids']=[i for i in part['object_ids'] if i not in ids];part['mapping_status']='removed' if not part['object_ids'] else 'partial'
        save_parts(parts)
        for ob in obs:bpy.data.objects.remove(ob,do_unlink=True)
        return {'deleted':True,'objects':preview}

    def object_parent(self,objects,parent=None,clear=False,keep_world=True):
        if (parent is None)==(not clear):raise ValueError('Specify parent or clear=true')
        obs=[resolve(n,writable=True) for n in objects];p=resolve(parent) if parent else None
        for ob in obs:
            guarded(ob)
            ancestor=p
            while ancestor:
                if ancestor==ob:raise ValueError('Parenting would create a cycle')
                ancestor=ancestor.parent
        for ob in obs:
            world=ob.matrix_world.copy();ob.parent=p
            if keep_world:ob.matrix_world=world
        return {'objects':[info(ob) for ob in obs],'parent':p.name if p else None}

    def object_origin(self,object,location):
        ob=resolve(object,'MESH',True);guarded(ob)
        children={child:child.matrix_world.copy() for child in ob.children}
        old=ob.matrix_world.copy();new=old.copy();new.translation=Vector(location)
        ob.data.transform(new.inverted()@old);ob.matrix_world=new
        for child,matrix in children.items():child.matrix_world=matrix
        ob.data.update();return info(ob)

    def object_visibility(self,objects,viewport=None,render=None):
        obs=[resolve(n) for n in objects]
        for ob in obs:
            if viewport is not None:ob.hide_set(not viewport)
            if render is not None:ob.hide_render=not render
        return {'objects':[{'name':o.name,'viewport':not o.hide_get(),'render':not o.hide_render} for o in obs]}

    def object_join(self,objects,name):
        from ..operations import selected
        obs=[resolve(n,'MESH',True) for n in objects]
        if len(set(obs))!=len(obs) or len(obs)<2:raise ValueError('At least two distinct meshes required')
        if name in bpy.data.objects and bpy.data.objects[name] not in obs:raise BridgeError('NAME_CONFLICT',name)
        for ob in obs:guarded(ob,topology_change=True);identify(ob)
        provenance=[{'object_id':o['bb_object_id'],'name':o.name,'vertices':len(o.data.vertices)} for o in obs]
        parts=part_map();old_ids={o['bb_object_id'] for o in obs};active=obs[0]
        with selected(obs):bpy.ops.object.join()
        active.name=name;active.data['bb_mesh_id']=str(uuid.uuid4())
        for part in parts.values():
            if set(part['object_ids'])&old_ids:
                part['object_ids']=list(dict.fromkeys([active['bb_object_id'] if x in old_ids else x for x in part['object_ids']]))
                if part.get('indices') is not None:part['mapping_status']='needs_region_reassignment'
        save_parts(parts);active['bb_join_sources']=json.dumps(provenance)
        return {'object':info(active),'sources':provenance,'region_mappings':'requires_explicit_reassignment'}

    def object_separate(self,object,name,faces=None,mode='faces'):
        from ..operations import selected
        from .common import index_check
        ob=resolve(object,'MESH',True);guarded(ob,topology_change=True);identify(ob)
        if mode=='faces' and not faces:raise ValueError('Exact face indices required')
        if faces:index_check(faces,len(ob.data.polygons))
        existing=set(bpy.data.objects);source_id=ob['bb_object_id']
        with selected([ob]):
            for poly in ob.data.polygons:poly.select=mode=='loose' or poly.index in set(faces or [])
            bpy.ops.object.mode_set(mode='EDIT')
            try:bpy.ops.mesh.separate(type='LOOSE' if mode=='loose' else 'SELECTED')
            finally:
                if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        created=sorted(set(bpy.data.objects)-existing,key=lambda x:x.name)
        for i,part in enumerate(created):
            part.name=f'{name}_{i+1:03d}';part['bb_object_id']=str(uuid.uuid4());part.data['bb_mesh_id']=str(uuid.uuid4());part['bb_source_object_id']=source_id
        parts=part_map()
        for part in parts.values():
            if source_id in part['object_ids']:
                part['object_ids']+= [x['bb_object_id'] for x in created]
                if part.get('indices') is not None:part['mapping_status']='needs_region_reassignment'
        save_parts(parts)
        return {'source':info(ob),'created':[info(x) for x in created]}

    def collection_inspect(self,collection):
        col=globals()['collection'](collection)
        return {'name':col.name,'objects':[info(o) for o in col.objects],'children':[c.name for c in col.children],'asset_id':col.get('bb_asset_id'),'candidate_revision':col.get('bb_candidate_revision')}

    def collection_move(self,objects,collection,unlink_others=False):
        dest=globals()['collection'](collection);obs=[resolve(n) for n in objects]
        for ob in obs:
            if ob.name not in dest.objects:dest.objects.link(ob)
            if unlink_others:
                for old in list(ob.users_collection):
                    if old!=dest:old.objects.unlink(ob)
        return self.collection_inspect(collection)

    def collection_duplicate(self,collection,name,linked=False):
        source=globals()['collection'](collection)
        if name in bpy.data.collections:raise BridgeError('NAME_CONFLICT',name)
        all_obs=list(source.all_objects)
        if any(name+'__'+ob.name in bpy.data.objects for ob in all_obs):raise BridgeError('NAME_CONFLICT','Candidate objects already exist')
        collections={}
        def walk(old,new_name,parent):
            new=bpy.data.collections.new(new_name);parent.children.link(new);collections[old]=new
            for key in old.keys():new[key]=old[key]
            for child in old.children:walk(child,name+'__'+child.name,new)
            return new
        dest=walk(source,name,bpy.context.scene.collection);copies={}
        for ob in all_obs:
            memberships=[collections[c] for c in ob.users_collection if c in collections]
            copy=duplicate_object(ob,name+'__'+ob.name,memberships[0],linked);copies[ob]=copy
            for col in memberships[1:]:col.objects.link(copy)
        for ob,copy in copies.items():
            world=copy.matrix_world.copy()
            if ob.parent in copies:copy.parent=copies[ob.parent]
            for modifier in copy.modifiers:
                if hasattr(modifier,'object') and modifier.object in copies:modifier.object=copies[modifier.object]
            copy.matrix_world=world
        dest['bb_asset_id']=str(uuid.uuid4())
        return {'collection':dest.name,'asset_id':dest['bb_asset_id'],'objects':[info(c) for c in copies.values()], 'mapping':{o.get('bb_object_id',o.name):c['bb_object_id'] for o,c in copies.items()}}

    def collection_visibility(self,collection,viewport=None,render=None):
        col=globals()['collection'](collection)
        if viewport is not None:col.hide_viewport=not viewport
        if render is not None:col.hide_render=not render
        return {'collection':col.name,'viewport':not col.hide_viewport,'render':not col.hide_render}

    def asset_create(self,asset_id,name,revision=1,role='editable_work'):
        if name in bpy.data.collections or any(c.get('bb_asset_id')==asset_id for c in bpy.data.collections):raise BridgeError('NAME_CONFLICT','Asset ID or collection already exists')
        col=bpy.data.collections.new(name);bpy.context.scene.collection.children.link(col)
        col['bb_asset_id']=asset_id;col['bb_candidate_revision']=revision;col['bb_role']=role
        return self.collection_inspect(name)

    def asset_inspect(self,asset_id):
        col=next((c for c in bpy.data.collections if c.get('bb_asset_id')==asset_id),None)
        if not col:raise BridgeError('ASSET_NOT_FOUND',asset_id)
        return self.collection_inspect(col.name)

    def asset_clone_revision(self,asset_id,name,revision):
        source=self.asset_inspect(asset_id);result=self.collection_duplicate(source['name'],name)
        dest=collection(name);dest['bb_source_asset_id']=asset_id;dest['bb_candidate_revision']=revision
        result['candidate_revision']=revision;return result

    def asset_import(self,path,collection,objects=None,prefix='',scale=1):
        from ..operations import selected
        source=self.state.input_path(path);suffix=source.suffix.lower();dest=globals()['collection'](collection)
        before=set(bpy.data.objects);old_selected=list(bpy.context.selected_objects);active=bpy.context.view_layer.objects.active
        try:
            if suffix=='.blend':
                if not objects:raise ValueError('Blend append requires explicit object names')
                with bpy.data.libraries.load(str(source),link=False) as (data_from,data_to):
                    if set(objects)-set(data_from.objects):raise ValueError('Requested blend objects not found')
                    data_to.objects=list(objects)
                for ob in data_to.objects:
                    if ob:dest.objects.link(ob)
            elif suffix in ('.glb','.gltf'):
                if suffix=='.gltf':
                    manifest=json.loads(source.read_text(encoding='utf-8'))
                    for item in manifest.get('images',[])+manifest.get('buffers',[]):
                        uri=item.get('uri','')
                        if uri and not uri.startswith('data:'):
                            if '://' in uri:raise BridgeError('PATH_DENIED','Remote glTF dependencies are not accepted')
                            self.state.input_path(str(source.parent/uri))
                bpy.ops.import_scene.gltf(filepath=str(source))
            elif suffix=='.fbx':bpy.ops.import_scene.fbx(filepath=str(source),anim_offset=0)
            elif suffix=='.obj':bpy.ops.wm.obj_import(filepath=str(source))
            else:raise BridgeError('UNSUPPORTED_CAPABILITY',f'Unsupported import extension {suffix}')
            created=sorted(set(bpy.data.objects)-before,key=lambda x:x.name)
            if not created:raise BridgeError('ARTIFACT_INVALID','Import produced no objects')
            warnings=[]
            for ob in created:
                if prefix:ob.name=prefix+ob.name
                ob['bb_object_id']=str(uuid.uuid4())
                if ob.data:ob.data['bb_mesh_id']=str(uuid.uuid4())
                if ob.name not in dest.objects:dest.objects.link(ob)
                for col in list(ob.users_collection):
                    if col!=dest:col.objects.unlink(ob)
                if ob.parent not in created:ob.scale*=scale;ob.location*=scale
                for slot in ob.material_slots:
                    if slot.material and slot.material.use_nodes:
                        for node in slot.material.node_tree.nodes:
                            if node.type=='TEX_IMAGE' and node.image and not node.image.packed_file:
                                image_path=Path(bpy.path.abspath(node.image.filepath))
                                if not image_path.is_file():warnings.append('Missing texture: '+str(image_path))
            bpy.context.view_layer.update()
            return {'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'objects':[info(o) for o in created],'warnings':warnings,'scale_applied':scale}
        finally:
            for ob in bpy.context.selected_objects:ob.select_set(False)
            for ob in old_selected:
                if ob.name in bpy.context.scene.objects:ob.select_set(True)
            bpy.context.view_layer.objects.active=active

    def asset_append(self,**args):return self.asset_import(**args)
