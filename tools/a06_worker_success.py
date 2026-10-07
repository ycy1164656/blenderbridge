"""Real MCP background snapshot render, disconnect, reconnect and actual inline image."""
import asyncio,base64,json,sys,uuid
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
OUT=Path('C:/dev/BlenderBridge/artifacts/native-modeling');PATH=OUT/'a06/worker-success.json'
async def invoke(tool,args):
    async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','blender_bridge.mcp_server'])) as (read,write):
      async with ClientSession(read,write) as client:
        await client.initialize();response=await client.call_tool(tool,args)
        assert not response.isError,response
        return response
def data(r):return json.loads(next(v.text for v in r.content if v.type=='text'))
async def main():
    source=json.loads((OUT/'a04/progress.json').read_text())['bake_checkpoint']['source']
    job=data(await invoke('blender_execute',{'operation':'worker.submit','args':{'blend':source['path'],'expected_sha256':source['sha256'],'operation':'preview.turntable','args':{'objects':['A04_Body'],'center':[0,0,1.3],'scale':4,'directory':'turntable','frames':4,'width':480,'height':360},'directory':'a06/mcp-worker-'+uuid.uuid4().hex[:8]},'request_id':str(uuid.uuid4()),'wait_seconds':0}))
    request=job.copy()
    while job['state'] in ('queued','running'):
        await asyncio.sleep(.5);job=data(await invoke('blender_job',{'job_id':job['id']}))
    assert job['state']=='succeeded',job
    image_record=next(a for a in job['result']['artifacts'] if a['path'].endswith('.png'))
    response=await invoke('blender_view_image',{'artifact_id':image_record['id']});block=next(v for v in response.content if v.type=='image')
    image_path=OUT/'a06/worker-actual-mcp.png';image_path.write_bytes(base64.b64decode(block.data))
    PATH.write_text(json.dumps({'initial':request,'final':job,'actual_inline_image':str(image_path),'mcp_disconnect_between_submit_query':True},indent=2))
    print(json.dumps({'path':str(PATH),'state':job['state'],'image':str(image_path)}))
if __name__=='__main__':asyncio.run(main())
