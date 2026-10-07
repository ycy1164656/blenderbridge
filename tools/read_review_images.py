"""Deliver registered current reference/model images through a fresh real MCP client."""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import sys
import uuid
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from blender_bridge.host.storage import Store


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reference');parser.add_argument('--model');args=parser.parse_args();store=Store()
    if args.reference:record=store.get('reference',args.reference);images=[v['artifact'] for v in record['views']]
    elif args.model:record=store.get('modeling',args.model);images=record['images']
    else:raise ValueError('reference or model required')
    out=store.root/'mcp-image-delivery'/uuid.uuid4().hex;out.mkdir(parents=True);delivered=[]
    async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','blender_bridge.mcp_server'])) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            for index,artifact in enumerate(images):
                response=await client.call_tool('blender_view_image',{'artifact_id':artifact['id']})
                if response.isError:raise RuntimeError(str(response.content))
                content=next(c for c in response.content if c.type=='image');path=out/f'{index:02d}.png';path.write_bytes(base64.b64decode(content.data))
                delivered.append({'artifact_id':artifact['id'],'source':artifact['path'],'image':str(path),'mimeType':content.mimeType})
    (out/'delivery.json').write_text(json.dumps(delivered,indent=2),encoding='utf-8');print(json.dumps(delivered,ensure_ascii=False))


if __name__=='__main__':asyncio.run(main())
