"""Thin grouped MCP adapter. All Blender writes go through the same live catalog."""
import asyncio
import hashlib
from pathlib import Path
from mcp.server.fastmcp import FastMCP, Image
from .client import connect, discover
from .core import BridgeError
from .host.gateway import Gateway

mcp = FastMCP('BlenderBridge', instructions='Discover exact session, inspect live catalog, use revision on writes. Submit once; poll job after timeout. Render success is not art acceptance.')


@mcp.tool()
async def blender_discover() -> list[dict]:
    """Find live local Blender sessions without exposing authentication tokens."""
    return await asyncio.to_thread(lambda: [h for c,h in discover()])


@mcp.tool()
async def blender_catalog(session: str | None = None, query: str = '', describe: str = '') -> dict:
    """Search operation names/descriptions, or describe exact operation input schema."""
    def run():
        result=Gateway().catalog(session,query,describe)
        if describe:return result
        return {'operations':[{k:o[k] for k in ('name','description','mutates','execution_domain','requires_session','requires_revision','writes_artifacts','long_running','availability')} for o in result['operations']]}
    return await asyncio.to_thread(run)


@mcp.tool()
async def blender_health(session: str) -> dict:
    """Read current revision, dirty/file state and active job. Snapshot is last main-thread observation."""
    return await asyncio.to_thread(lambda: connect(session).call('health'))


@mcp.tool()
async def blender_execute(operation: str, args: dict, request_id: str, session: str | None = None, revision: int | None = None, wait_seconds: float = 1) -> dict:
    """Submit exact catalog operation with a stable unique request ID. Never auto-refresh revision or retry with a new ID."""
    def run():
        return Gateway().execute(operation,args,request_id,session,revision,min(30,max(0,wait_seconds)))
    return await asyncio.to_thread(run)


@mcp.tool()
async def blender_job(job_id: str, session: str | None = None, cancel_queued: bool = False) -> dict:
    """Query accepted work after disconnect/timeout, or cancel a queued job. Running calls cannot be cancelled."""
    return await asyncio.to_thread(lambda: Gateway().job(job_id,session,cancel_queued))


@mcp.tool()
async def blender_artifacts(session: str | None = None) -> dict:
    """List generated files, hashes and source revisions."""
    return await asyncio.to_thread(lambda: Gateway().artifacts(session))


@mcp.tool()
async def blender_view_image(artifact_id: str, session: str | None = None) -> Image:
    """Return a registered hash-verified image inline and record delivery. Image delivery alone never grants review or acceptance."""
    def run():
        artifact,data=Gateway().image(artifact_id,session)
        return Image(data=data,format=artifact['kind'].split('/')[1])
    return await asyncio.to_thread(run)


def main():
    mcp.run(transport='stdio')


if __name__ == '__main__': main()

