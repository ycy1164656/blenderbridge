"""Actual installed runtime through fresh MCP clients, persisted review and restart recovery."""
import argparse,asyncio,base64,json,sys,uuid
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from blender_bridge.host.storage import Store
from blender_bridge.core import atomic_json
OUT=Path('C:/dev/BlenderBridge/artifacts/native-modeling');STATE=OUT/'a06/progress.json'

async def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','review','reconnect','fix','final-review']);a=p.parse_args();s=json.loads(STATE.read_text()) if STATE.exists() else {};trace=[]
    async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','blender_bridge.mcp_server'])) as (read,write):
      async with ClientSession(read,write) as client:
        init=await client.initialize();listed=await client.list_tools();assert len(listed.tools)==7
        async def call(tool,args):
            response=await client.call_tool(tool,args);trace.append({'tool':tool,'args':args,'result':response.model_dump(mode='json') if tool!='blender_view_image' else {'isError':response.isError,'image_returned':any(c.type=='image' for c in response.content)}})
            if response.isError:raise RuntimeError(str(response.content))
            values=[json.loads(c.text) for c in response.content if c.type=='text']
            if tool=='blender_discover':return values[0] if len(values)==1 and isinstance(values[0],list) else values
            return values[0]
        sessions=await call('blender_discover',{});assert len(sessions)==1,sessions;h=await call('blender_health',{'session':sessions[0]['session']});s.update(session=h['session'],revision=h['revision'])
        async def execute(op,args,wait=30):
            j=await call('blender_execute',{'operation':op,'args':args,'request_id':str(uuid.uuid4()),'session':s['session'],'revision':s['revision'],'wait_seconds':wait})
            if j['state'] in ('queued','running'):
                native=op.startswith(('geometry.','camera.','preview.','scene.','mesh.'))
                while j['state'] in ('queued','running'):
                    await asyncio.sleep(.2);j=await call('blender_job',{'job_id':j['id'],**({'session':s['session']} if native else {})})
            if j['state']=='succeeded' and 'revision' in j:s['revision']=j['revision']
            return j
        async def require(op,args):
            j=await execute(op,args)
            if j['state']!='succeeded':raise RuntimeError(json.dumps(j))
            return j['result']
        async def images(model):
            paths=[]
            for i,artifact in enumerate(model['images']):
                response=await client.call_tool('blender_view_image',{'artifact_id':artifact['id']});assert not response.isError
                content=next(c for c in response.content if c.type=='image');path=OUT/'a06'/f'r{model["candidate_revision"]}'/f'actual-mcp-{i}.png';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(base64.b64decode(content.data));paths.append(str(path))
                trace.append({'tool':'blender_view_image','artifact_id':artifact['id'],'mimeType':content.mimeType,'saved_actual_image':str(path)})
            return paths
        if a.stage=='prepare':
            catalog=await call('blender_catalog',{'session':s['session'],'describe':'geometry.loft'});assert catalog['availability']=='runtime_advertised'
            ref=Store().get('reference_frozen','a01-asymmetric-pylon-full:1')
            views=(await require('preview.camera_set',{'name':'A06Camera','center':[0,0,1.45],'scale':5.4}))['views']
            rings=[[[x*width,y*depth,z] for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]] for width,depth,z in [(.7,.5,0),(.7,.5,2.1),(.4,.3,2.75)]]
            m=await require('modeling.plan',{'modeling_id':'a06-installed-mcp-loop','asset_id':'a06-protocol-fixture','reference_id':ref['reference_id'],'reference_revision':ref['revision'],'reference_sha256':ref['frozen_sha256'],'objects':['A06_Probe'],'steps':[{'operation':'geometry.loft','args':{'name':'A06_Probe','sections':rings}}],'views':views[:3],'directory':'a06/model','assumptions':['Protocol-only engineering fixture; reference receipt and state guards tested, no artwork fidelity acceptance claimed.','Explicit controlled error: top ring z=2.75, intended 2.50; fix only four upper vertices.']})
            m=await require('modeling.submit',{'modeling_id':m['modeling_id']});s['revision']=m['revision']
            premature=await execute('review.record',{'modeling_id':m['modeling_id'],'review_id':'a06-unread-must-reject','candidate_revision':1,'artifact_ids':[v['id'] for v in m['images']],'issues':[],'summary':'Protocol negative test: images have not been delivered yet.','decision':'self_review_passed','reviewer':'fixture_protocol'})
            assert premature['state']=='failed' and premature['error']['code']=='IMAGE_NOT_READ',premature
            s.update(model=m,views=views,negative_unread=premature,images=await images(m))
        elif a.stage=='review':
            m=await require('modeling.inspect',{'modeling_id':'a06-installed-mcp-loop'});s['revision']=m['revision']
            review=await require('review.record',{'modeling_id':m['modeling_id'],'review_id':'a06-initial-actual-review','candidate_revision':1,'artifact_ids':[v['id'] for v in m['images']],'issues':[{'issue_id':'a06-top-height','observation':'Read front/left/back actual MCP images: tall tapered cap corresponds to declared +0.25m top-ring error. Lower only indices8..11; rectangular lower body must remain unchanged.','status':'open'}],'summary':'Actual images inspected. This is a protocol engineering fixture and cannot grant art acceptance. Preserve this open correction across Blender replacement and MCP reconnection.','decision':'needs_work','reviewer':'fixture_protocol'})
            s['review']=review
            saved=await require('scene.save',{'path':'session/a06-pending-review.blend','copy':True});s['restart_source']=saved
        elif a.stage=='reconnect':
            old=s['model'];m=await require('modeling.reconnect',{'modeling_id':old['modeling_id']});assert m['session']==s['session'] and m['open_issues'][0]['issue_id']=='a06-top-height'
            s['model']=m;s['reconnected_without_replay']=m['history'][-1]
        elif a.stage=='fix':
            m=await require('modeling.inspect',{'modeling_id':'a06-installed-mcp-loop'});s['revision']=m['revision'];before=await require('mesh.inspect',{'object':'A06_Probe','limit':12})
            m=await require('modeling.resume',{'modeling_id':m['modeling_id'],'review_id':s['review']['review_id'],'steps':[{'operation':'mesh.region_transform','args':{'object':'A06_Probe','indices':[8,9,10,11],'delta':[0,0,-.25]}}]});s['revision']=m['revision'];after=await require('mesh.inspect',{'object':'A06_Probe','limit':12})
            assert before['vertex_data'][:8]==after['vertex_data'][:8];assert all(abs(after['vertex_data'][i]['co'][2]-2.50)<1e-6 for i in range(8,12))
            stale=await execute('review.record',{'modeling_id':m['modeling_id'],'review_id':'a06-old-candidate-must-reject','candidate_revision':1,'artifact_ids':[v['id'] for v in s['model']['images']],'issues':[],'summary':'Old candidate negative test.','decision':'self_review_passed','reviewer':'fixture_protocol'})
            assert stale['state']=='failed' and stale['error']['code']=='REVIEW_STALE';s.update(model=m,before_fix=before,after_fix=after,negative_stale=stale,images=await images(m))
        else:
            m=await require('modeling.inspect',{'modeling_id':'a06-installed-mcp-loop'});s['revision']=m['revision']
            r=await require('review.record',{'modeling_id':m['modeling_id'],'review_id':'a06-final-actual-review','candidate_revision':2,'artifact_ids':[v['id'] for v in m['images']],'issues':[{'issue_id':'a06-top-height','observation':'Front/left/back images rechecked after correction: cap shortened while lower rectangular body unchanged. Exact top z=2.50 and untouched eight lower vertices independently read back.','status':'resolved'}],'summary':'Protocol recovery and bounded edit succeeded, images actually viewed. Fixture-only visual review; user art acceptance remains pending.','decision':'self_review_passed','reviewer':'fixture_protocol'})
            m=await require('modeling.resume',{'modeling_id':m['modeling_id'],'review_id':r['review_id']});assert m['phase']=='ready_for_technical_validation' and m['visual_self_review']=='fixture_protocol_only';s['model']=m
        s.setdefault('runs',[]).append({'stage':a.stage,'initialize':init.model_dump(mode='json'),'tools':[v.name for v in listed.tools],'trace':trace});atomic_json(STATE,s)
        print(json.dumps({'stage':a.stage,'session':s['session'],'revision':s['revision'],'phase':s.get('model',{}).get('phase'),'images':s.get('images',[])}))

if __name__=='__main__':asyncio.run(main())
