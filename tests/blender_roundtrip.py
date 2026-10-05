"""Run in a separate Blender background process; inspect saved source and imported FBX."""
import json
from pathlib import Path
import sys
import bpy

root = Path(sys.argv[sys.argv.index('--')+1])
source = root/'smoke'/'model.blend'
bpy.ops.wm.open_mainfile(filepath=str(source))
ob = bpy.data.objects['ArmorStudy']
source_count = len(ob.data.vertices)
assert source_count > 8 and len(ob.data.uv_layers) >= 1
assert 'FixtureRig' in bpy.data.objects and len(bpy.data.objects['FixtureRig'].data.bones) == 2
scene = bpy.context.scene
scene.frame_set(1)
source_dimensions = list(ob.dimensions)
v1 = [tuple(v.co) for v in ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
scene.frame_set(12)
v2 = [tuple(v.co) for v in ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
assert max(sum((a-b)**2 for a,b in zip(p,q))**.5 for p,q in zip(v1,v2)) > .1
# New scene in this disposable verification process; preserve source data.
new_scene = bpy.data.scenes.new('FBX_Roundtrip')
bpy.context.window.scene = new_scene
bpy.ops.import_scene.fbx(filepath=str(root/'smoke'/'model.fbx'),anim_offset=0.0)
imported = [o for o in new_scene.objects]
rig = next(o for o in imported if o.type == 'ARMATURE')
mesh = next(o for o in imported if o.type == 'MESH' and 'ArmorStudy' in o.name)
assert len(rig.data.bones) == 2 and len(mesh.data.uv_layers) >= 1
assert rig.animation_data and rig.animation_data.action
assert all(abs(sum(g.weight for g in v.groups)-1) < .0001 for v in mesh.data.vertices)
new_scene.frame_set(1)
import_dimensions = list(mesh.dimensions)
assert max(abs(a-b) for a,b in zip(source_dimensions,import_dimensions)) < .0001, (source_dimensions,import_dimensions)
def evaluated_coords():
    return [tuple(v.co) for v in mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
fbx1 = evaluated_coords()
new_scene.frame_set(12)
fbx2 = evaluated_coords()
assert max(sum((a-b)**2 for a,b in zip(p,q))**.5 for p,q in zip(fbx1,fbx2)) > .1
new_scene.frame_set(24)
fbx24 = evaluated_coords()
return_error = max(sum((a-b)**2 for a,b in zip(p,q))**.5 for p,q in zip(fbx1,fbx24))
assert return_error < .0001, {'return_error':return_error,'source_fps':scene.render.fps,'import_fps':new_scene.render.fps,
                            'action_range':list(rig.animation_data.action.frame_range),'anim_offset':bpy.ops.import_scene.fbx.get_rna_type().properties['anim_offset'].default}
report = {'source_vertices':source_count,'fbx_vertices':len(mesh.data.vertices), 'bones':len(rig.data.bones),
          'animation_deformation':True,'fbx_action':rig.animation_data.action.name,'normalized_weights':True,
          'fbx_animation_deforms_and_returns':True,'source_dimensions':source_dimensions,'fbx_dimensions':import_dimensions,
          'uv_layers':len(mesh.data.uv_layers),'scene_objects':[o.name for o in imported]}
(root/'smoke'/'roundtrip.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('ROUNDTRIP_PASS ' + json.dumps(report))
