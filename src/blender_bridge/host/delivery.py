"""Independent export readback and factual Chinese reports."""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from .storage import sha,process_identity
from ..core import BridgeError,atomic_json


class DeliveryOps:
    def delivery_inspect(self,manifest):
        path=self.store.input(manifest);data=json.loads(path.read_text(encoding='utf-8-sig'));checks=[]
        for artifact in data['artifacts']+data.get('textures',[]):
            source=self.store.input(artifact['path']);checks.append({'path':str(source),'expected':artifact['sha256'],'actual':sha(source),'valid':sha(source)==artifact['sha256']})
        return {'manifest':data,'manifest_sha256':sha(path),'hash_checks':checks,'hashes_valid':all(c['valid'] for c in checks),'independent_validation':self._validation_record(data['delivery_id'])}

    def _validation_record(self,identity):
        try:return self.store.get('delivery_validation',identity)
        except BridgeError as exc:
            if exc.code!='RECORD_NOT_FOUND':raise
            return {'state':'not_run'}

    def delivery_verify(self,manifest):
        inspected=self.delivery_inspect(manifest);data=inspected['manifest']
        if not inspected['hashes_valid']:raise BridgeError('DELIVERY_CHANGED','Manifest output hash mismatch')
        run_id=uuid.uuid4().hex;root=self.store.root/'delivery-readback'/run_id;root.mkdir(parents=True)
        script=Path(__file__).resolve().parents[1]/'workers'/'readback.py';measurements=[]
        for index,artifact in enumerate(data['artifacts']):
            path=self.store.input(artifact['path'])
            if path.suffix.lower() not in ('.blend','.fbx','.glb','.obj'):continue
            spec={'path':str(path),'result':str(root/f'{index:02d}-result.json'),'package_parent':str(Path(self.store.config.get('addon_parent',Path(__file__).resolve().parents[2])).resolve())}
            specpath=root/f'{index:02d}-request.json';atomic_json(specpath,spec)
            command=[self.store.config['blender'],'--background','--factory-startup','--python-exit-code','1','--python',str(script),'--',str(specpath)]
            log=root/f'{index:02d}-blender.log'
            with log.open('wb') as output:
                process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,start_new_session=os.name!='nt')
            identity=process_identity(process.pid);worker_id=run_id+f'-{index:02d}'
            if not identity:raise BridgeError('WORKER_START_FAILED','Readback process exited before registration')
            worker={'worker_id':worker_id,**identity,'state':'running','operation':'delivery.readback','directory':str(root),'log':str(log),'started':time.time(),'request_id':self.request['request_id']}
            self.store.put('worker',worker_id,worker,create=True)
            process.wait();record_path=Path(spec['result'])
            result=json.loads(record_path.read_text(encoding='utf-8')) if record_path.is_file() else {'state':'interrupted','error':'No readback result'}
            worker.update(state=result['state'],exit_code=process.returncode,finished=time.time());self.store.put('worker',worker_id,worker)
            if process.returncode!=0 or result['state']!='succeeded':raise BridgeError('READBACK_FAILED',json.dumps({'result':result,'log':str(log)},ensure_ascii=False))
            result['artifact']=artifact;measurements.append(result)
        source=next((m for m in measurements if Path(m['path']).suffix=='.blend'),None)
        if not source:raise ValueError('Editable source readback required')
        source_meshes=[o for o in source['objects'] if o['type']=='MESH'];source_triangles=sum(o.get('evaluated_triangles',o.get('triangles',0)) for o in source_meshes)
        source_bones={b['name'] for o in source['objects'] if o['type']=='ARMATURE' for b in o['bones']};checks=[]
        for result in measurements:
            ext=Path(result['path']).suffix;meshes=[o for o in result['objects'] if o['type']=='MESH'];bones={b['name'] for o in result['objects'] if o['type']=='ARMATURE' for b in o['bones']}
            triangles=sum(o.get('evaluated_triangles',o.get('triangles',0)) for o in meshes);issues=[]
            if triangles!=source_triangles:issues.append({'code':'TRIANGLE_MISMATCH','source':source_triangles,'readback':triangles})
            if not result['bounds'] or not source['bounds']:issues.append({'code':'BOUNDS_MISSING'})
            else:
                errors=[abs(result['bounds'][key][i]*result['scale_length']-source['bounds'][key][i]*source['scale_length']) for key in ('min','max') for i in range(3)]
                if max(errors)>max(.001,data.get('profile',{}).get('height_tolerance',.001)):issues.append({'code':'AXIS_DIMENSIONS_OR_PIVOT_MISMATCH','max_m':max(errors)})
            if any(o.get('uv_layers') for o in source_meshes) and any(not o.get('uv_layers') for o in meshes):issues.append({'code':'UV_LOST'})
            if ext!='.obj' and source_bones-bones:issues.append({'code':'BONES_LOST','bones':sorted(source_bones-bones)})
            if ext!='.obj' and any(o.get('weights',{}).get('unweighted',0) or o.get('weights',{}).get('non_normalized',0) for o in meshes if o.get('weights',{}).get('armature_present')):issues.append({'code':'DEFORM_WEIGHTS_CHANGED'})
            if any(not t['exists'] or not all(t['size']) for t in result['textures']):issues.append({'code':'TEXTURE_MISSING'})
            if data['animation']['enabled'] and ext in ('.fbx','.glb'):
                ranges=[o['action_range'] for o in result['objects'] if o.get('action_range')]
                expected=data['animation']['frame_range']
                if not ranges or abs(min(r[0] for r in ranges)-expected[0])>.1 or abs(max(r[1] for r in ranges)-expected[1])>.1:issues.append({'code':'ANIMATION_RANGE_MISMATCH','expected':expected,'ranges':ranges})
            checks.append({'format':ext,'state':'passed' if not issues else 'failed','issues':issues,'triangles':triangles,'mesh_count':len(meshes),'bone_count':len(bones),'vertex_count_comparison':'not_required_due_to_export_vertex_splitting','textures':len(result['textures'])})
        record={'delivery_id':data['delivery_id'],'manifest_sha256':inspected['manifest_sha256'],'state':'passed' if all(c['state']=='passed' for c in checks) else 'failed','checks':checks,'measurements':measurements,
                'art_match':'not_evaluated_by_readback','ue_validation':'not_run','user_visual_acceptance':'pending'}
        report=self.store.json_artifact(f'delivery-readback/{run_id}/verification.json',record);record['report']=report
        self.store.put('delivery_validation',data['delivery_id'],record)
        return record

    def delivery_report(self,manifest,path):
        result=self.delivery_inspect(manifest);data=result['manifest'];validation=result['independent_validation']
        lines=['# BlenderBridge 交付记录','',f"交付 ID：`{data['delivery_id']}`",'',f"文件哈希：{'通过' if result['hashes_valid'] else '失败'}",f"模型技术检查：{data.get('technical_validation',{}).get('state','not_run')}",f"独立读回：{validation.get('state','not_run')}",f"视觉自评：{data.get('visual_self_review','not_run')}",f"用户视觉验收：{data.get('user_visual_acceptance','pending')}",f"UE 验证：{data.get('ue_validation','not_run')}",'','## 文件','']
        lines += [f"- `{a['path']}` — SHA256 `{a['sha256']}`" for a in data['artifacts']+data.get('textures',[])]
        lines += ['','## 验证边界','','文件存在、技术检查和独立读回不代表参考匹配、关节美术质量、用户体验或 UE 验收。', '', '```json',json.dumps(validation.get('checks',[]),ensure_ascii=False,indent=2),'```','']
        output=self.store.output(path,'.md');output.write_text('\n'.join(lines),encoding='utf-8')
        return self.store.artifact(output,'text/markdown',{'manifest':str(self.store.input(manifest)),'manifest_sha256':result['manifest_sha256']})
