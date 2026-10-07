"""Fresh real stdio client for catalog/reconnect/image verification, no bypass API."""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import sys
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tool');parser.add_argument('--args-file');parser.add_argument('--output',required=True)
    args=parser.parse_args();output=Path(args.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    params=StdioServerParameters(command=sys.executable,args=['-m','blender_bridge.mcp_server'])
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            initialized=await session.initialize();listed=await session.list_tools()
            record={'initialize':initialized.model_dump(mode='json'),'tools':[t.name for t in listed.tools]}
            if args.tool:
                values=json.loads(Path(args.args_file).read_text(encoding='utf-8-sig')) if args.args_file else {}
                result=await session.call_tool(args.tool,values);blocks=[]
                for index,content in enumerate(result.content):
                    if content.type=='image':
                        path=output.with_name(output.stem+f'-image-{index}.png');path.write_bytes(base64.b64decode(content.data));blocks.append({'type':'image','mimeType':content.mimeType,'path':str(path),'bytes':path.stat().st_size})
                    elif content.type=='text':
                        try:blocks.append({'type':'text','json':json.loads(content.text)})
                        except ValueError:blocks.append({'type':'text','text':content.text})
                record.update(tool=args.tool,isError=result.isError,content=blocks)
            output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'output':str(output),'tools':record['tools'],'isError':record.get('isError'),'images':[b for b in record.get('content',[]) if b['type']=='image']},ensure_ascii=False))


if __name__=='__main__':asyncio.run(main())
