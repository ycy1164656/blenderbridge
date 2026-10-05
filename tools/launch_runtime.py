"""Blender --python entry point; no scene reset or deletion. Background pump stays alive."""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import bpy
from blender_bridge.runtime import start, stop

p = argparse.ArgumentParser()
p.add_argument('--output-root', required=True)
p.add_argument('--read-root', action='append', default=[])
p.add_argument('--sessions-dir')
p.add_argument('--port', type=int, default=0)
p.add_argument('--allow-python', action='store_true')
a = p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
r = start(a.output_root, a.read_root, a.port, a.allow_python, a.sessions_dir, timer=not bpy.app.background)
print('BLENDER_BRIDGE_READY ' + r.state.session, flush=True)
if bpy.app.background:
    try:
        while r.running:
            r.tick()
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        stop()

