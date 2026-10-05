import asyncio
import json
from pathlib import Path
import sys
import uuid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from blender_bridge.client import connect

c = connect()
root = Path(c.call('health')['output_root'])


def run(name,args,timeout=60):
    h = c.call('health')
    j = c.submit(name,args,h['revision'],str(uuid.uuid4()))
    j = c.wait(j['id'],timeout)
    assert j['state'] == 'succeeded', j
    print('PASS ' + name,flush=True)
    return j['result']


clay = run('preview.render',{'camera':'ReviewCamera','objects':['ArmorStudy','Mount'],
            'path':'smoke/clay-subject.png','style':'clay','overwrite':True})
material = run('preview.render',{'camera':'ReviewCamera','objects':['ArmorStudy','Mount'],
            'path':'smoke/material-subject.png','style':'material','overwrite':True})
viewport = run('preview.viewport',{'path':'smoke/viewport.png','overwrite':True})


def result_dict(result):
    assert not result.isError, result
    if result.structuredContent: return result.structuredContent
    return json.loads(result.content[0].text)


async def test_mcp():
    params = StdioServerParameters(command=sys.executable,args=['-m','blender_bridge.mcp_server'])
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 7
            health = result_dict(await session.call_tool('blender_health',{'session':c.session}))
            cat = result_dict(await session.call_tool('blender_catalog',{'session':c.session,'describe':'mesh.vertices'}))
            assert cat['name'] == 'mesh.vertices'
            job = result_dict(await session.call_tool('blender_execute',{'session':c.session,
                'operation':'scene.inspect','args':{},'request_id':str(uuid.uuid4()),'revision':health['revision'],'wait_seconds':2}))
            assert job['state'] == 'succeeded'
            image = await session.call_tool('blender_view_image',{'session':c.session,'artifact_id':clay['id']})
            assert not image.isError and any(i.type == 'image' for i in image.content)
            report = {'tools':[t.name for t in tools.tools], 'scene_inspect':job, 'inline_image':True,
                      'clay':clay,'material':material,'viewport':viewport}
            (root/'smoke'/'mcp-integration.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print('PASS MCP stdio initialize/list/catalog/execute/image',flush=True)


asyncio.run(test_mcp())

