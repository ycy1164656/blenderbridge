"""Lifecycle and Blender main-thread pump, usable in GUI and background."""
import json
from pathlib import Path
import threading
import uuid
import bpy
from bpy.app.handlers import persistent
from .core import RuntimeState, atomic_json, default_sessions
from .operations import Operations, snapshot
from .transport import start_http

_runtime = None


class Runtime:
    def __init__(self, output_root, read_roots=(), port=0, allow_python=False, sessions_dir=None):
        self.state = RuntimeState(output_root, read_roots, allow_python)
        self.operations = Operations(self.state)
        self.server = start_http(self.state, port)
        self.running = True
        self.main_thread = threading.get_ident()
        self.discovery = Path(sessions_dir or default_sessions()) / f"{self.state.session}.json"
        self.state.snapshot = snapshot()
        self.publish()

    def publish(self):
        atomic_json(self.discovery, {"session": self.state.session, "pid": self.state.health()['pid'],
                    "endpoint": f"http://127.0.0.1:{self.server.server_port}", "token": self.state.token,
                    "started": self.state.started, "output_root": str(self.state.output_root)})

    def tick(self):
        if not self.running: return None
        if threading.get_ident() != self.main_thread: raise RuntimeError("bpy main-thread contract violated")
        self.state.execute_one(self.operations.execute, snapshot)
        return 0.03

    def stop(self):
        self.running = False
        self.server.shutdown()
        self.server.server_close()
        if self.discovery.exists(): self.discovery.unlink()


@persistent
def changed(scene, depsgraph):
    if _runtime and not _runtime.state.active_job and depsgraph.updates:
        with _runtime.state.lock:
            _runtime.state.revision += 1
            _runtime.state.snapshot = snapshot()


@persistent
def loaded(_):
    # Loading another blend invalidates all cached scene/object identities.
    if _runtime:
        with _runtime.state.lock:
            old = _runtime.discovery
            _runtime.state.session = str(uuid.uuid4())
            _runtime.state.revision += 1
            _runtime.discovery = old.with_name(_runtime.state.session + '.json')
            _runtime.state.snapshot = snapshot()
            _runtime.publish()
            if old.exists(): old.unlink()


def start(output_root, read_roots=(), port=0, allow_python=False, sessions_dir=None, timer=True):
    global _runtime
    if _runtime: raise RuntimeError("Bridge already running; stop it explicitly before reconfiguring")
    _runtime = Runtime(output_root, read_roots, port, allow_python, sessions_dir)
    bpy.app.handlers.depsgraph_update_post.append(changed)
    bpy.app.handlers.load_post.append(loaded)
    if timer: bpy.app.timers.register(_runtime.tick, first_interval=0.1, persistent=True)
    return _runtime


def stop():
    global _runtime
    if not _runtime: return
    if bpy.app.timers.is_registered(_runtime.tick): bpy.app.timers.unregister(_runtime.tick)
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, changed), (bpy.app.handlers.load_post, loaded)):
        if callback in handlers: handlers.remove(callback)
    _runtime.stop()
    _runtime = None

