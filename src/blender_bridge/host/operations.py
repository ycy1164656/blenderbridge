"""Host dispatcher; no scene API imported in this process."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import uuid
import psutil
from .references import ReferenceOps
from .modeling import ModelingOps
from .workers import WorkerOps
from .comparison import ComparisonOps
from .delivery import DeliveryOps
from .storage import sha,process_identity
from ..catalog import OPS
from ..core import BridgeError


class HostOperations(ReferenceOps,ModelingOps,WorkerOps,ComparisonOps,DeliveryOps):
    def __init__(self,store,request):self.store=store;self.request=request

    def execute(self,name,args):
        method=getattr(self,name.replace('.','_'),None)
        if method is None:raise BridgeError('UNSUPPORTED_CAPABILITY','Host implementation unavailable: '+name)
        return method(**args)

    def job_recover(self,job_id):
        from .jobs import HostJobs
        return HostJobs(self.store).recover_before_start(job_id)

    def system_doctor(self):
        from .. import __version__
        blender=Path(self.store.config['blender']);version=None
        if blender.is_file():
            result=subprocess.run([str(blender),'--version'],capture_output=True,text=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            version=result.stdout.splitlines()[0] if result.returncode==0 and result.stdout else None
        packages={}
        for name in ('mcp','Pillow','psutil'):
            try:packages[name]=importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:packages[name]='missing'
        gpu=[]
        executable=shutil.which('nvidia-smi')
        if executable:
            result=subprocess.run([executable,'--query-gpu=name,memory.total,memory.free,driver_version','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if result.returncode==0:gpu=result.stdout.strip().splitlines()
        memory=psutil.virtual_memory();disk=shutil.disk_usage(self.store.root)
        from .broker import broker_ready
        broker=broker_ready(self.store)
        return {'bridge_version':__version__,'host_python':sys.version,'executable':sys.executable,'platform':platform.platform(),'blender':{'path':str(blender),'exists':blender.is_file(),'version':version},'host_broker':{'state':'running' if broker else 'not_running','pid':broker['pid'] if broker else None},
                'packages':packages,'output_root':str(self.store.root),'read_roots':self.store.config['read_roots'],'ram_bytes':{'total':memory.total,'available':memory.available},
                'disk_free_bytes':disk.free,'gpu':gpu,'neural_3d_required':False,'weights_downloaded':False,'allow_external_3d_inference':False,'state':'ready' if version and all(v!='missing' for v in packages.values()) else 'missing_required_dependency'}

    def system_capabilities(self):
        from .. import __version__
        host=[n for n,v in OPS.items() if v['execution_domain']=='host_cpu' and hasattr(self,n.replace('.','_'))]
        result={'bridge_version':__version__,'host_operations':host,'catalog_operations':len(OPS),'native_runtime_probe':'not_requested','neural_3d_required':False,'test_evidence_is_separate':True}
        if self.request.get('session'):
            from ..client import connect
            client=connect(self.request['session'],self.store.config.get('sessions_dir'));job=client.submit('scene.capabilities',{},request_id=self.request['request_id']+':native')
            result['native_runtime_probe']=client.wait(job['id'],30)
        return result

    def system_verify(self,suite='native-modeling',run_fixture=False):
        if not run_fixture:return {'suite':suite,'state':'not_run','reason':'Set run_fixture=true to create an owned background Blender fixture; art acceptance remains separate'}
        repository=Path(__file__).resolve().parents[3];script=repository/'tests'/'blender_native_fixture.py'
        if not script.is_file():raise BridgeError('FIXTURE_MISSING','Installed Host does not include the repository fixture')
        run_id=uuid.uuid4().hex;log=self.store.output(f'verification/{run_id}/blender.log','.log')
        command=[self.store.config['blender'],'--background','--factory-startup','--python-exit-code','1','--python',str(script)]
        with log.open('wb') as stream:process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,start_new_session=os.name!='nt')
        identity=process_identity(process.pid)
        if identity:self.store.put('worker',run_id,{'worker_id':run_id,**identity,'state':'running','directory':str(log.parent),'log':str(log),'operation':'system.verify','request_id':self.request['request_id']},create=True)
        process.wait();text=log.read_text(encoding='utf-8',errors='replace');markers=[line.removeprefix('NATIVE_FIXTURE_RESULT ').strip() for line in text.splitlines() if line.startswith('NATIVE_FIXTURE_RESULT ')]
        result=json.loads(Path(markers[-1]).read_text(encoding='utf-8')) if markers and Path(markers[-1]).is_file() else None
        state='passed' if process.returncode==0 and result and all(r['state']=='passed' for r in result['results']) else 'failed'
        if identity:
            worker=self.store.get('worker',run_id);worker.update(state='succeeded' if state=='passed' else 'failed',exit_code=process.returncode);self.store.put('worker',run_id,worker)
        return {'suite':suite,'state':state,'exit_code':process.returncode,'result_path':markers[-1] if markers else None,'results':result['results'] if result else [],'log':str(log),'art_acceptance':'not_performed','ue_validation':'not_run'}
