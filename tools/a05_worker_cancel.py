"""Controlled interruption of one precisely owned render worker; no scene process stopped."""
import asyncio,json,sys,time,uuid
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from blender_bridge.host.gateway import Gateway
from blender_bridge.host.storage import sha
from blender_bridge.core import atomic_json
OUT=Path('C:/dev/BlenderBridge/artifacts/native-modeling');source=OUT/'a04/export/source.blend';request_id='a05-controlled-worker-cancel-'+uuid.uuid4().hex[:8]

async def dispatch():
    async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','blender_bridge.mcp_server'])) as (read,write):
        async with ClientSession(read,write) as client:
            init=await client.initialize();listed=await client.list_tools()
            response=await client.call_tool('blender_execute',{'operation':'worker.submit','args':{'blend':str(source),'expected_sha256':sha(source),'operation':'preview.turntable','args':{'objects':json.loads((OUT/'a04/progress.json').read_text())['objects'],'center':[0,0,1.8],'scale':7.7,'frames':64,'width':1920,'height':1080,'style':'material','directory':'frames'},'directory':'a05/interrupted-render-'+uuid.uuid4().hex[:8]},'request_id':request_id,'wait_seconds':0})
            assert not response.isError,response
            return {'initialize':init.model_dump(mode='json'),'tools':[t.name for t in listed.tools],'response':response.model_dump(mode='json')}

mcp=asyncio.run(dispatch());g=Gateway();deadline=time.time()+45;worker=None
while time.time()<deadline:
    job=g.job(request_id)
    if job.get('worker_id'):
        worker=g.store.get('worker',job['worker_id']);log=Path(worker['log']);text=log.read_text(encoding='utf-8',errors='replace') if log.exists() else ''
        # Wait for real rendering work rather than cancelling before Blender starts.
        if worker['state']=='running' and any(marker in text for marker in ('Rendering','Sample ','Syncing','Saved:')):break
    if job['state'] in ('failed','succeeded','interrupted','cancelled'):raise RuntimeError('Worker ended before controlled interruption: '+json.dumps(job))
    time.sleep(.2)
else:raise RuntimeError('Render did not begin within bounded wait')
assert worker
bad=g.execute('worker.cancel',{'worker_id':worker['worker_id'],'pid':worker['pid']+1},str(uuid.uuid4()),wait_seconds=1)
assert bad['state']=='failed' and bad['error']['code']=='WORKER_IDENTITY_MISMATCH'
cancel=g.execute('worker.cancel',{'worker_id':worker['worker_id'],'pid':worker['pid']},str(uuid.uuid4()),wait_seconds=1);assert cancel['state']=='succeeded'
for _ in range(50):
    job=g.job(request_id)
    if job['state'] not in ('queued','running'):break
    time.sleep(.1)
inspection=g.execute('worker.inspect',{'worker_id':worker['worker_id']},str(uuid.uuid4()),wait_seconds=1)
record=inspection['result']['workers'][0];assert record['state']=='cancelled' and not record['identity_matches'] and job['state']=='cancelled',(record,job)
registered=[a for a in g.store.artifacts() if Path(a['path']).is_relative_to(Path(worker['directory']))];assert not registered,registered
report={'request_id':request_id,'mcp_client_disconnected_before_worker_finished':True,'mcp':mcp,'worker_before':worker,'wrong_pid_rejected':bad,'cancel':cancel,'terminal_job':job,'worker_after':record,'partial_files':[str(p) for p in Path(worker['directory']).rglob('*') if p.is_file()],'published_success_artifacts':registered,'source_unchanged':sha(source)==worker['source_sha256']}
atomic_json(OUT/'a05'/('worker-cancel-'+worker['worker_id']+'.json'),report)
print(json.dumps({'worker_id':worker['worker_id'],'pid':worker['pid'],'state':record['state'],'job_state':job['state'],'published_artifacts':len(registered)}))
