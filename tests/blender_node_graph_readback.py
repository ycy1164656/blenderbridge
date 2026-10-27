"""Run in an independent Blender process against the saved graph transaction result."""
from pathlib import Path
import hashlib
import json
import bpy

root=Path(__file__).resolve().parents[1]/'.tmp/artifacts/bridge-upgrade/latest'
cube=bpy.data.objects['Cube'];peer=bpy.data.objects['ProtectedPeer']
assert cube.modifiers['ExactGeometry'].node_group != peer.modifiers['ExactGeometry'].node_group
assert 'ProtocolNode' in cube.modifiers['ExactGeometry'].node_group.nodes
assert cube.material_slots[0].material != peer.material_slots[0].material
assert abs(cube.material_slots[0].material.node_tree.nodes['SharedGroup'].node_tree.nodes['Math'].inputs[0].default_value-.65)<1e-6
assert abs(peer.material_slots[0].material.node_tree.nodes['SharedGroup'].node_tree.nodes['Math'].inputs[0].default_value-.2)<1e-6
assert bpy.context.scene.compositing_node_group != bpy.data.scenes['ProtectedScene'].compositing_node_group
assert abs(bpy.context.scene.compositing_node_group.nodes['Exposure'].inputs['Exposure'].default_value-.5)<1e-6
assert abs(bpy.data.scenes['ProtectedScene'].compositing_node_group.nodes['Exposure'].inputs['Exposure'].default_value)<1e-6
evidence=json.loads((root/'node-graph-evidence.json').read_text())
assert hashlib.sha256((root/'external-texture.png').read_bytes()).hexdigest()==evidence['protected_texture_sha256']
(root/'node-graph-independent-readback.json').write_text(json.dumps({'state':'passed','blender':bpy.app.version_string,'file':bpy.data.filepath,'sha256':hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),'graph_kinds':['geometry','shader','compositor'],'human_visual_acceptance':'pending'},indent=2))
print('NODE_GRAPH_INDEPENDENT_READBACK_PASS')
