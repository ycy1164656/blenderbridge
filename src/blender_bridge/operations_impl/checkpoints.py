"""Scoped immutable checkpoints and explicitly non-atomic ordered batches."""
import json
import time
import uuid
import bpy
from .common import resolve, identify, fingerprint, part_map, save_parts, protection_snapshot, verify_protection, write_json
from ..core import BridgeError
from ..catalog import OPS, validate


class CheckpointOps:
    def _save_source(self, objects, path):
        output=self.state.output_path(path,'.blend')
        scene=bpy.data.scenes.new('__bb_checkpoint_'+uuid.uuid4().hex)
        try:
            for ob in objects: scene.collection.objects.link(ob)
            source=bpy.context.scene
            scene.unit_settings.system=source.unit_settings.system;scene.unit_settings.scale_length=source.unit_settings.scale_length
            scene.frame_start=source.frame_start;scene.frame_end=source.frame_end;scene.render.fps=source.render.fps;scene.render.fps_base=source.render.fps_base
            scene.world=source.world
            if source.camera in objects:scene.camera=source.camera
            scene.view_settings.view_transform=source.view_settings.view_transform;scene.view_settings.look=source.view_settings.look
            scene.view_settings.exposure=source.view_settings.exposure;scene.view_settings.gamma=source.view_settings.gamma
            scene['bb_parts']=source.get('bb_parts','{}')
            # Sync the new scene's layer tree before Blender 5.2 copies it for a partial write.
            # An unsynchronized view layer can crash BKE_view_layer_copy_data.
            for layer in scene.view_layers: layer.update()
            scene.frame_set(source.frame_current)
            bpy.data.libraries.write(str(output),{scene},path_remap='RELATIVE_ALL',fake_user=True,compress=True)
        finally: bpy.data.scenes.remove(scene)
        return self.state.artifact(output,'application/x-blender')

    def checkpoint_create(self, label, objects=None):
        obs=[resolve(o) for o in objects] if objects else list(bpy.context.scene.objects)
        if not obs: raise ValueError('Checkpoint requires objects')
        requested=set(obs);closure=set(obs);pending=list(obs)
        while pending:
            ob=pending.pop();deps=([ob.parent] if ob.parent else [])+[getattr(m,p.identifier,None) for m in ob.modifiers for p in m.bl_rna.properties if p.type=='POINTER']
            for dep in deps:
                if isinstance(dep,bpy.types.Object) and dep not in closure:closure.add(dep);pending.append(dep)
        obs=sorted(closure,key=lambda ob:ob.name)
        cid=uuid.uuid4().hex;directory='checkpoints/'+cid
        source=self._save_source(obs,directory+'/source.blend')
        ids={o.get('bb_object_id') for o in obs}
        manifest={'checkpoint_id':cid,'label':label,'created':time.time(),'source':source,
                  'objects':[{'name':o.name,'object_id':o.get('bb_object_id'),'hash':fingerprint(o)} for o in obs],
                  'parts':{p:v for p,v in part_map().items() if set(v['object_ids'])<=ids},
                  'session':self.state.session,'revision':self.state.revision,'included_dependencies':[ob.name for ob in obs if ob not in requested]}
        artifact=write_json(self.state,directory+'/checkpoint.json',manifest)
        return {**manifest,'manifest':artifact}

    def checkpoint_list(self):
        return {'checkpoints':[json.loads(p.read_text(encoding='utf-8')) for p in sorted((self.state.output_root/'checkpoints').glob('*/checkpoint.json'))]}

    def checkpoint_restore(self, checkpoint_id, name):
        found=next((m for m in self.checkpoint_list()['checkpoints'] if m['checkpoint_id']==checkpoint_id),None)
        if not found: raise BridgeError('CHECKPOINT_NOT_FOUND',checkpoint_id)
        if name in bpy.data.collections: raise ValueError('New candidate collection name required')
        import hashlib
        source=self.state.input_path(found['source']['path'])
        if hashlib.sha256(source.read_bytes()).hexdigest()!=found['source']['sha256']: raise BridgeError('CHECKPOINT_CHANGED','Checkpoint source hash mismatch')
        requested=[o['name'] for o in found['objects']]
        with bpy.data.libraries.load(str(source),link=False) as (src,dst):
            if set(requested)-set(src.objects): raise ValueError('Checkpoint object list does not match blend')
            dst.objects=requested
        col=bpy.data.collections.new(name);bpy.context.scene.collection.children.link(col)
        mapping={};names=[]
        for ob in dst.objects:
            old_id=ob.get('bb_object_id');identify(ob,True);ob.name=name+'_'+ob.name;col.objects.link(ob)
            mapping[old_id]=ob['bb_object_id'];names.append(ob.name)
        parts=part_map()
        for pid,part in found['parts'].items():
            copied=dict(part);copied['object_ids']=[mapping[i] for i in part['object_ids']];copied['locked']=False
            parts[name+':'+pid]=copied
        save_parts(parts);self.state.rotate_session();bpy.context.view_layer.update()
        return {'checkpoint_id':checkpoint_id,'collection':name,'objects':names,'identity_mapping':mapping,'session':self.state.session,'restored_as_new_candidate':True,'existing_scene_preserved':True}

    def batch_execute(self, steps, protected_parts=(), expected_hashes=None):
        for step in steps:
            operation=step['operation'];spec=OPS.get(operation)
            if not spec or spec['execution_domain']!='blender_main_thread' or operation in ('batch.execute','checkpoint.restore','python.execute'):
                raise ValueError('Operation is not batch-safe: '+operation)
            validate(step['args'],spec['inputSchema'])
        for ob,value in (expected_hashes or {}).items():
            if fingerprint(resolve(ob))!=value: raise BridgeError('SOURCE_CHANGED',ob)
        before=protection_snapshot(protected_parts);completed=[]
        parts=part_map();locked={p:parts[p].get('locked',False) for p in protected_parts}
        for p in protected_parts: parts[p]['locked']=True
        save_parts(parts)
        try:
            for index,step in enumerate(steps):
                try:
                    result=self.legacy.execute(step['operation'],step['args'])
                    completed.append({'index':index,'operation':step['operation'],'result':result})
                    verify_protection(before)
                except Exception as exc:
                    error=BridgeError(getattr(exc,'code','BATCH_STEP_FAILED'),f'Batch stopped at step {index}: {exc}')
                    error.details={'completed':completed,'failed_step':index,'atomic':False,'rollback_performed':False}
                    raise error from exc
        finally:
            current=part_map()
            for p,value in locked.items():
                if p in current: current[p]['locked']=value
            save_parts(current)
        return {'completed':completed,'protected':verify_protection(before),'atomic':False}
