"""Blender --python entry: execute one frozen typed request, publish terminal result."""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback


def main():
    specification=Path(sys.argv[sys.argv.index('--')+1]).resolve()
    request=json.loads(specification.read_text(encoding='utf-8'))
    sys.path.insert(0,request['package_parent'])
    import bpy
    from blender_bridge.catalog import OPS,validate
    from blender_bridge.core import RuntimeState,atomic_json
    from blender_bridge.operations import Operations,snapshot
    root=Path(request['output_root']);state=RuntimeState(root,request['read_roots']);result={'worker_id':request['worker_id'],'state':'running','started':time.time(),'code_origin':str(Path(sys.modules['blender_bridge'].__file__).resolve())}
    atomic_json(root/'worker-state.json',result)
    try:
        source=Path(request['blend'])
        if hashlib.sha256(source.read_bytes()).hexdigest()!=request['expected_sha256']:raise ValueError('Frozen blend hash mismatch')
        bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=False)
        operation=request['operation'];validate(request['args'],OPS[operation]['inputSchema'])
        operations=Operations(state);output=operations.execute(operation,request['args'])
        result.update(state='succeeded',result=output,artifacts=list(state.artifacts.values()),snapshot=snapshot(),finished=time.time())
    except BaseException as exc:
        result.update(state='failed',error={'code':getattr(exc,'code','WORKER_FAILED'),'message':str(exc),'traceback':traceback.format_exc()},artifacts=list(state.artifacts.values()),finished=time.time())
        raise
    finally:atomic_json(root/'worker-result.json',result)


if __name__=='__main__':main()
