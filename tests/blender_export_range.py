"""Validate explicit FBX animation range and restoration using installed add-on code."""
from pathlib import Path
import json
import bpy
from blender_bridge.core import RuntimeState
from blender_bridge.operations import Operations

root = Path('C:/dev/BlenderBridge/.tmp/artifacts/bridge-validation/Blender-Win64-5.2/latest')
bpy.ops.wm.open_mainfile(filepath=str(root/'smoke'/'model.blend'))
scene = bpy.context.scene
original = (scene.frame_start,scene.frame_end,scene.frame_current)
ops = Operations(RuntimeState(root))
artifact = ops.execute('export.fbx',{'objects':['ArmorStudy','Mount','FixtureRig'],'path':'smoke/model-range24.fbx',
                'animation':True,'frame_start':1,'frame_end':24})
assert (scene.frame_start,scene.frame_end,scene.frame_current) == original
new = bpy.data.scenes.new('RangeReadback')
bpy.context.window.scene = new
bpy.ops.import_scene.fbx(filepath=artifact['path'],anim_offset=0.0)
rig = next(o for o in new.objects if o.type == 'ARMATURE')
assert list(rig.animation_data.action.frame_range) == [1.0,24.0]
report = {'explicit_export_range':[1,24],'import_range':list(rig.animation_data.action.frame_range),
          'original_scene_restored':True,'import_anim_offset':0,'artifact':artifact}
(root/'smoke'/'export-range.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('EXPORT_RANGE_PASS ' + json.dumps({k:v for k,v in report.items() if k != 'artifact'}))

