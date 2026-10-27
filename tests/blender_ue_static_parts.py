"""Real FBX local-pivot export and independent import, with source preservation assertions."""
from pathlib import Path
import json,sys
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'.tmp/artifacts/bridge-upgrade/static-parts-test-v2'
if '--verify' in sys.argv:
 data=json.loads((OUT/'package/delivery.json').read_text())
 originals={o['name']:o for o in data['objects']}
 rows=[]
 for part in data['ue_static_parts']['parts']:
  bpy.ops.wm.read_factory_settings(use_empty=True)
  bpy.ops.import_scene.fbx(filepath=part['artifact']['path'])
  meshes=[o for o in bpy.data.objects if o.type=='MESH'];assert len(meshes)==1
  mesh=meshes[0];expected=[v*data['scale_length'] for v in originals[part['source_object']]['dimensions']]
  assert max(abs(a-b) for a,b in zip(mesh.dimensions,expected))<1e-5
  assert max(abs(v) for v in mesh.location)<1e-6
  rows.append({'name':part['source_object'],'dimensions_m':list(mesh.dimensions),'local_pivot_at_origin':True})
 (OUT/'independent-readback.json').write_text(json.dumps({'passed':True,'parts':rows},indent=2))
 print('UE_STATIC_PARTS_INDEPENDENT_PASS')
else:
 from blender_bridge.core import RuntimeState
 from blender_bridge.operations import Operations
 from blender_bridge.operations_impl.common import fingerprint
 from blender_bridge.catalog import OPS,validate
 bpy.ops.wm.read_factory_settings(use_empty=True)
 bpy.context.scene.unit_settings.scale_length=.1
 bpy.ops.mesh.primitive_cube_add();a=bpy.context.object;a.name='Base';a.location=(2,3,4)
 bpy.ops.mesh.primitive_cube_add();b=bpy.context.object;b.name='Turret';b.parent=a;b.location=(0,0,2);b.rotation_euler.z=.4
 bpy.context.view_layer.update()
 before={o.name:(fingerprint(o),[list(r) for r in o.matrix_world],o.data.as_pointer()) for o in (a,b)}
 scenes=set(bpy.data.scenes.keys());meshes=set(bpy.data.meshes.keys());objects=set(bpy.data.objects.keys())
 state=RuntimeState(OUT);ops=Operations(state)
 args={'objects':['Base','Turret'],'directory':'package','formats':['fbx'],'ue_static_mesh_parts':True}
 validate(args,OPS['export.package']['inputSchema']);result=ops.execute('export.package',args)
 assert before=={o.name:(fingerprint(o),[list(r) for r in o.matrix_world],o.data.as_pointer()) for o in (a,b)}
 assert scenes==set(bpy.data.scenes.keys()) and meshes==set(bpy.data.meshes.keys()) and objects==set(bpy.data.objects.keys())
 assert abs(bpy.context.scene.unit_settings.scale_length-.1)<1e-7
 parts={p['source_object']:p for p in result['ue_static_parts']['parts']}
 assert parts['Turret']['parent']=='Base' and max(abs(a-b) for a,b in zip(parts['Turret']['location_cm'],[0.,0.,20.]))<1e-5
 assert result['semantic_forward']['basis']=='unknown'
 (OUT/'preservation.json').write_text(json.dumps({'passed':True,'source_geometry_transforms_and_datablocks_preserved':True,'delivery_id':result['delivery_id']},indent=2))
 print('UE_STATIC_PARTS_EXPORT_PASS')
