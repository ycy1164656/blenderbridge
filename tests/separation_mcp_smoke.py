"""Fresh MCP client, restricted to an explicitly identified owned 0.3.0 runtime."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import uuid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    parser.add_argument('--expected-pid', required=True, type=int)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = output / ('mcp-config-' + uuid.uuid4().hex[:8] + '.json')
    # The test must not write to the user's configured Host output directory.
    config.write_text(json.dumps({'output_root': str(output), 'read_roots': [],
                                 'sessions_dir': str(output / '.bridge' / 'sessions')}), encoding='utf-8')
    parameters = StdioServerParameters(command=sys.executable, args=['-m', 'blender_bridge.mcp_server'],
                                       env={'BLENDER_BRIDGE_CONFIG': str(config),
                                            'BLENDER_BRIDGE_SESSIONS': str(output / '.bridge' / 'sessions')})
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            listed = await client.list_tools()
            async def call(tool, values):
                result = await client.call_tool(tool, values)
                blocks = [block.text for block in result.content if block.type == 'text']
                if result.isError:
                    raise RuntimeError('\n'.join(blocks))
                return json.loads(blocks[0])
            async def health():
                return await call('blender_health', {'session': args.session})
            initial = await health()
            assert initial['pid'] == args.expected_pid
            assert Path(initial['output_root']).resolve() == output
            assert initial['bridge_version'] == '0.3.0' and not initial['allow_python']
            assert initial['snapshot']['background'] and not initial['snapshot']['filepath']
            assert initial['revision'] == 0, 'Use a fresh owned factory runtime'
            catalog = await call('blender_catalog', {'session': args.session, 'describe': 'object.separate'})
            assert {'selection_id', 'face_policy', 'keep_original'} <= catalog['inputSchema']['properties'].keys()
            async def submit(operation, values):
                current = await health()
                request = {'operation': operation, 'args': values, 'session': args.session,
                           'revision': current['revision'], 'request_id': str(uuid.uuid4()), 'wait_seconds': 1}
                job = await call('blender_execute', request)
                while job['state'] in ('queued', 'running'):
                    await asyncio.sleep(.1)
                    job = await call('blender_job', {'session': args.session, 'job_id': job['id']})
                assert job['state'] == 'succeeded', job
                return job, request
            async def run(operation, values):
                job, _ = await submit(operation, values)
                return job['result']
            await run('scene.inspect', {})
            await run('mesh.primitive', {'name': 'BB03Source', 'kind': 'cube'})
            await run('scene.identify', {'objects': ['BB03Source']})
            await run('camera.create', {'name': 'BB03Review', 'location': [-5, -4, 3], 'target': [0, 0, 0], 'orthographic_scale': 4})
            before = await run('preview.render', {'objects': ['BB03Source'], 'camera': 'BB03Review', 'path': 'before.png', 'width': 640, 'height': 480})
            await run('checkpoint.create', {'objects': ['BB03Source'], 'label': 'before-region-separate'})
            fingerprint = await run('scene.fingerprint', {'objects': ['BB03Source']})
            selection = await run('selection.query', {'objects': ['BB03Source'], 'box_min': [-2, -2, -2], 'box_max': [0, 2, 2], 'space': 'local'})
            job, request = await submit('object.separate', {'object': 'BB03Source', 'name': 'BB03Parts',
                                          'selection_id': selection['selection_id'], 'face_policy': 'all_vertices', 'keep_original': True})
            result = job['result']
            assert result['preservation']['state'] == 'passed'
            assert result['source']['faces'] == 5 and result['created'][0]['faces'] == 1
            assert await run('scene.fingerprint', {'objects': ['BB03Source']}) == fingerprint
            # Same logical request after intervening read operations must return its original job.
            repeated = await call('blender_execute', request)
            assert repeated['id'] == job['id'] and repeated['result'] == result
            objects = [item['name'] for item in [result['source'], *result['created']]]
            after = await run('preview.render', {'objects': objects, 'camera': 'BB03Review', 'path': 'after.png', 'width': 640, 'height': 480})
            for artifact in (before, after):
                received = await client.call_tool('blender_view_image', {'session': args.session, 'artifact_id': artifact['id']})
                assert not received.isError and any(block.type == 'image' for block in received.content)
            saved = await run('scene.save', {'path': 'mcp-separation.blend'})
            final = await health()
            record = {'state': 'passed', 'version': final['bridge_version'], 'pid': final['pid'], 'session': args.session,
                      'grouped_tools': len(listed.tools), 'python_fallback_enabled': final['allow_python'],
                      'separation': result, 'images': [before['path'], after['path']], 'saved': saved['path'],
                      'duplicate_request_replayed': False, 'final_snapshot': final['snapshot']}
            (output / 'mcp-smoke.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
            print('SEPARATION_MCP_PASS ' + str(output / 'mcp-smoke.json'), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
