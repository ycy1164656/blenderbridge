"""Owned background Blender processes, exact identity and immutable snapshots."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import psutil
from .storage import sha,process_identity,matches_process
from ..core import BridgeError,atomic_json
from ..catalog import OPS,validate


WORKER_OPERATIONS={'preview.render','preview.multiview','preview.turntable','bake.execute','batch.execute','retopo.remesh','game.validate','export.package','scene.inspect','scene.capabilities'}


class WorkerOps:
    def worker_submit(self,blend,operation,args,directory,expected_sha256,bake_plan=None):
        if operation not in WORKER_OPERATIONS:raise BridgeError('UNSUPPORTED_WORKER_OPERATION',operation)
        validate(args,OPS[operation]['inputSchema'])
        source=self.store.input(blend)
        if source.suffix.lower()!='.blend' or sha(source)!=expected_sha256:raise BridgeError('SNAPSHOT_CHANGED','Expected exact .blend source hash')
        if operation=='batch.execute':
            for step in args['steps']:
                if step['operation'] in ('python.execute','checkpoint.restore','batch.execute') or step['operation'] not in OPS or OPS[step['operation']]['execution_domain']!='blender_main_thread':raise ValueError('Unsafe or unknown worker batch operation')
                validate(step['args'],OPS[step['operation']]['inputSchema'])
        frozen_plan=None
        if operation=='bake.execute':
            if not bake_plan:raise BridgeError('BAKE_PLAN_REQUIRED','Frozen snapshot bake requires the exact prepared plan manifest')
            plan_path=self.store.input(bake_plan);frozen_plan=json.loads(plan_path.read_text(encoding='utf-8'))
            if frozen_plan.get('plan_id')!=args['plan_id'] or frozen_plan.get('state')!='prepared':raise BridgeError('BAKE_PLAN_CONFLICT','Expected matching, unexecuted prepared bake plan')
        elif bake_plan:raise ValueError('bake_plan is only accepted for bake.execute')
        worker_id=uuid.uuid4().hex
        marker=self.store.output(f'{directory}/worker-request.json','.json');root=marker.parent
        snapshot=root/'snapshot.blend';shutil.copy2(source,snapshot)
        if frozen_plan:atomic_json(root/'.bridge'/'bakes'/(frozen_plan['plan_id']+'.json'),frozen_plan)
        package_parent=Path(self.store.config.get('addon_parent',Path(__file__).resolve().parents[2])).resolve()
        script=Path(__file__).resolve().parents[1]/'workers'/'blender_worker.py'
        request={'worker_id':worker_id,'blend':str(snapshot),'expected_sha256':expected_sha256,'operation':operation,'args':args,'output_root':str(root),
                 'read_roots':[str(self.store.root)]+self.store.config['read_roots'],'package_parent':str(package_parent)}
        atomic_json(marker,request)
        command=[self.store.config['blender'],'--background','--factory-startup','--python-exit-code','1','--python',str(script),'--',str(marker)]
        log=root/'blender.log'
        with log.open('wb') as output:
            process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,start_new_session=os.name!='nt')
        identity=process_identity(process.pid)
        if not identity:raise BridgeError('WORKER_START_FAILED','Blender exited before identity registration')
        record={'worker_id':worker_id,**identity,'state':'running','operation':operation,'directory':str(root),'log':str(log),'source_sha256':expected_sha256,'started':time.time(),'request_id':self.request['request_id']}
        self.store.put('worker',worker_id,record,create=True)
        from .jobs import HostJobs
        HostJobs(self.store).update(self.request['request_id'],worker_id=worker_id)
        while process.poll() is None:
            time.sleep(.2)
        current=self.store.get('worker',worker_id)
        if current['state']=='cancelled':
            error=BridgeError('WORKER_CANCELLED','Exact owned worker was cancelled; partial output retained and not published')
            error.details={'worker':current};raise error
        result_path=root/'worker-result.json'
        if result_path.is_file():
            result=json.loads(result_path.read_text(encoding='utf-8'));record.update(result)
            if process.returncode!=0 and result.get('state')=='succeeded':record.update(state='failed',error={'code':'WORKER_EXIT','message':'Blender nonzero exit after result'})
            if record['state']=='succeeded' and result.get('artifacts'):self.store.import_artifacts(result['artifacts'],root)
            elif result.get('artifacts'):
                record['partial_artifacts']=record.pop('artifacts',[])
        else:record.update(state='interrupted',error={'code':'RESULT_UNKNOWN','message':'Blender exited without terminal result; partial files retained'})
        record.update(exit_code=process.returncode,finished=time.time());self.store.put('worker',worker_id,record)
        if record['state']!='succeeded':
            error=BridgeError('WORKER_'+record['state'].upper(),record.get('error',{}).get('message','Worker failed'));error.details={'worker':record};raise error
        return record

    def worker_inspect(self,worker_id=None):
        records=[self.store.get('worker',worker_id)] if worker_id else self.store.records('worker')
        for record in records:
            record['identity_matches']=matches_process(record)
            if record['state']=='running' and not record['identity_matches']:
                path=Path(record['directory'])/'worker-result.json'
                if path.is_file():record.update(json.loads(path.read_text(encoding='utf-8')))
                else:record.update(state='interrupted',error={'code':'RESULT_UNKNOWN','message':'Owned process no longer exists; no automatic replay'})
                self.store.put('worker',record['worker_id'],record)
        return {'workers':records}

    def worker_cancel(self,worker_id,pid):
        record=self.store.get('worker',worker_id)
        if record['pid']!=pid or record['state']!='running' or not matches_process(record):raise BridgeError('WORKER_IDENTITY_MISMATCH','Exact running owned PID/start/executable/command required')
        record.update(state='cancelled',cancel_requested=time.time(),partial_output_retained=True);self.store.put('worker',worker_id,record)
        psutil.Process(pid).terminate()
        return record
