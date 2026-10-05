"""Thin grouped MCP adapter. All Blender writes go through the same live catalog."""
import asyncio
import hashlib
from pathlib import Path
from mcp.server.fastmcp import FastMCP, Image
from .client import connect, discover
from .core import BridgeError

mcp = FastMCP('BlenderBridge', instructions='Discover exact session, inspect live catalog, use revision on writes. Submit once; poll job after timeout. Render success is not art acceptance.')


@mcp.tool()
async def blender_discover() -> list[dict]:
    """Find live local Blender sessions without exposing authentication tokens."""
    return await asyncio.to_thread(lambda: [h for c,h in discover()])


@mcp.tool()
async def blender_catalog(session: str, query: str = '', describe: str = '') -> dict:
    """Search operation names/descriptions, or describe exact operation input schema."""
    def run():
        ops = connect(session).call('catalog')['operations']
        if describe:
            for op in ops:
                if op['name'] == describe: return op
            raise ValueError('Unknown operation')
        return {'operations':[{k:o[k] for k in ('name','description','mutates')} for o in ops
                              if query.lower() in (o['name'] + ' ' + o['description']).lower()]}
    return await asyncio.to_thread(run)


@mcp.tool()
async def blender_health(session: str) -> dict:
    """Read current revision, dirty/file state and active job. Snapshot is last main-thread observation."""
    return await asyncio.to_thread(lambda: connect(session).call('health'))


@mcp.tool()
async def blender_execute(session: str, operation: str, args: dict, request_id: str, revision: int | None = None, wait_seconds: float = 1) -> dict:
    """Submit exact catalog operation with a stable unique request ID. Never auto-refresh revision or retry with a new ID."""
    def run():
        c = connect(session)
        job = c.submit(operation, args, revision, request_id)
        return c.wait(job['id'], min(30,max(0,wait_seconds))) if wait_seconds else job
    return await asyncio.to_thread(run)


@mcp.tool()
async def blender_job(session: str, job_id: str, cancel_queued: bool = False) -> dict:
    """Query accepted work after disconnect/timeout, or cancel a queued job. Running calls cannot be cancelled."""
    return await asyncio.to_thread(lambda: connect(session).call('cancel' if cancel_queued else 'job', {'id':job_id}))


@mcp.tool()
async def blender_artifacts(session: str) -> dict:
    """List generated files, hashes and source revisions."""
    return await asyncio.to_thread(lambda: connect(session).call('artifacts'))


@mcp.tool()
async def blender_view_image(session: str, artifact_id: str) -> Image:
    """Return a verified rendered image inline. Only runtime-produced PNG artifacts are readable."""
    def run():
        c = connect(session)
        entries = c.call('artifacts')['artifacts']
        artifact = next((a for a in entries if a['id'] == artifact_id), None)
        if not artifact or artifact['kind'] != 'image/png': raise ValueError('PNG artifact not found')
        path = Path(artifact['path']).resolve()
        root = Path(c.call('health')['output_root']).resolve()
        if not path.is_relative_to(root) or path.stat().st_size > 16 * 1024 * 1024:
            raise BridgeError('PATH_DENIED','Artifact outside root or too large')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != artifact['sha256']: raise ValueError('Artifact changed since render')
        return Image(data=data, format='png')
    return await asyncio.to_thread(run)


def main():
    mcp.run(transport='stdio')


if __name__ == '__main__': main()

