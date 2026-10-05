"""Installed add-on validation, intentionally without source sys.path injection."""
import json
from pathlib import Path
import bpy
import blender_bridge
from blender_bridge import runtime

assert 'blender_bridge' in bpy.context.preferences.addons
assert runtime._runtime is None, 'Add-on must not auto-start'
assert bpy.ops.blender_bridge.start() == {'FINISHED'}
r = runtime._runtime
assert r and not r.state.allow_python
initial_session = r.state.session
initial_revision = r.state.revision
cube = bpy.data.objects.get('Cube')
assert cube
cube.location.x += .25
bpy.context.view_layer.update()
assert r.state.revision > initial_revision, 'External scene change did not update revision'
# Load a saved test source, verifying load handlers invalidate the previous session.
source = Path('C:/dev/BlenderBridge/.tmp/artifacts/bridge-validation/Blender-Win64-5.2/latest/smoke/model.blend')
bpy.ops.wm.open_mainfile(filepath=str(source))
assert r.state.session != initial_session, 'Loading another blend did not change session'
assert bpy.ops.blender_bridge.stop() == {'FINISHED'}
assert runtime._runtime is None
report = {'installed_module':blender_bridge.__file__,'enabled_after_restart':True,'default_no_listener':True,
          'start_stop':True,'external_revision':True,'load_invalidates_session':True,'python_disabled':True}
(source.parent/'addon-lifecycle.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('ADDON_LIFECYCLE_PASS ' + json.dumps(report))
