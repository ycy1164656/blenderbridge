"""Real Blender graph transactions, protected owners, and saved-file readback fixture."""
from pathlib import Path
import hashlib
import json
import sys
import uuid
import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from blender_bridge.core import RuntimeState, BridgeError
from blender_bridge.operations import Operations, snapshot
from blender_bridge.operations_impl.common import node_tree_state
from blender_bridge.catalog import OPS, validate

OUT=ROOT/'.tmp/artifacts/bridge-upgrade/latest'
OUT.mkdir(parents=True,exist_ok=True)
state=RuntimeState(OUT)
ops=Operations(state)
evidence=[]

def run(name,args):
    validate(args,OPS[name]['inputSchema'])
    return ops.execute(name,args)

def fingerprint(tree):
    return hashlib.sha256(json.dumps(node_tree_state(tree),sort_keys=True).encode()).hexdigest()

def patch(owner,actions):
    before=run('node_graph.inspect',{'owner':owner})
    result=run('node_graph.patch',{'owner':owner,'graph_token':before['graph_token'],'actions':actions})
    evidence.append(result)
    return result

def socket(node,name,output=False):
    return (node.outputs if output else node.inputs)[name].identifier

cube=bpy.data.objects['Cube'];peer=cube.copy();peer.data=cube.data.copy();peer.name='ProtectedPeer';bpy.context.scene.collection.objects.link(peer)
peer.location.x=4
tree=bpy.data.node_groups.new('SharedGeometry','GeometryNodeTree')
tree.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
gin=tree.nodes.new('NodeGroupInput');gout=tree.nodes.new('NodeGroupOutput');transform=tree.nodes.new('GeometryNodeTransform');transform.name='Transform'
tree.links.new(gin.outputs['Geometry'],transform.inputs['Geometry']);tree.links.new(transform.outputs['Geometry'],gout.inputs['Geometry'])
for obj in (cube,peer):obj.modifiers.new('ExactGeometry','NODES').node_group=tree
owner={'kind':'geometry','object':cube.name,'modifier':'ExactGeometry'}
before=fingerprint(tree)
result=patch(owner,[{'action':'set_input','node':'Transform','socket':socket(transform,'Translation'),'value':[0.5,0,0]}])
assert result['status']=='applied',result
assert result['evaluation']['vertices']==8,result
assert fingerprint(tree)==before and peer.modifiers['ExactGeometry'].node_group==tree
assert cube.modifiers['ExactGeometry'].node_group!=tree
bpy.context.view_layer.update();ev=cube.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
assert abs(sum(v.co.x for v in mesh.vertices)/len(mesh.vertices)-.5)<1e-6
ev.to_mesh_clear()

# A partial candidate mutation must never become visible after a later failure.
bound=cube.modifiers['ExactGeometry'].node_group
result=patch(owner,[{'action':'add_node','node':'Temporary','node_type':'ShaderNodeMath'},
                    {'action':'set_property','node':'Temporary','property':'operation','value':'INVALID_ENUM'}])
assert result['status']=='rolled_back',result
assert cube.modifiers['ExactGeometry'].node_group==bound and 'Temporary' not in bound.nodes
result=patch(owner,[{'action':'set_input','node':'WrongEmitterEquivalent','socket':'Translation','value':[0,0,0]}])
assert result['status']=='rolled_back',result
stale=run('node_graph.inspect',{'owner':owner})['graph_token'];bound.nodes['Transform'].inputs['Translation'].default_value.x=.75
try:run('node_graph.patch',{'owner':owner,'graph_token':stale,'actions':[{'action':'add_node','node':'NoReplay','node_type':'ShaderNodeMath'}]})
except BridgeError as exc:assert exc.code=='STALE_GRAPH'
else:raise AssertionError('Stale graph accepted')

mat=bpy.data.materials.new('SharedMaterial');mat.use_nodes=True
cube.data.materials.clear();cube.data.materials.append(mat);peer.data.materials.clear();peer.data.materials.append(mat)
group=bpy.data.node_groups.new('SharedShaderGroup','ShaderNodeTree')
group.interface.new_socket(name='Roughness',in_out='OUTPUT',socket_type='NodeSocketFloat')
math_node=group.nodes.new('ShaderNodeMath');math_node.name='Math';math_node.operation='MULTIPLY';math_node.inputs[0].default_value=.2;math_node.inputs[1].default_value=1
out=group.nodes.new('NodeGroupOutput');group.links.new(math_node.outputs[0],out.inputs[0])
node=mat.node_tree.nodes.new('ShaderNodeGroup');node.name='SharedGroup';node.node_tree=group
bsdf=mat.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=(.1,.3,.8,1)
mat.node_tree.links.new(node.outputs[0],bsdf.inputs['Roughness'])
image=bpy.data.images.new('ProtectedImage',width=4,height=4);image.generated_color=(.2,.4,.6,1);image.filepath=str(OUT/'external-texture.png');image.file_format='PNG';image.save()
tex=mat.node_tree.nodes.new('ShaderNodeTexImage');tex.image=image
image_hash=hashlib.sha256(Path(image.filepath).read_bytes()).hexdigest();mat_before=fingerprint(mat.node_tree);group_before=fingerprint(group)
shader_owner={'kind':'shader','object':cube.name,'material_slot':0,'group_path':['SharedGroup']}
inspected=run('node_graph.inspect',{'owner':shader_owner,'nodes':['Math']})
assert 'MULTIPLY' in inspected['nodes'][0]['properties']['operation']['enum']
assert inspected['nodes'][0]['inputs'][0]['identifier']!=inspected['nodes'][0]['inputs'][1]['identifier']
result=patch(shader_owner,[{'action':'set_input','node':'Math','socket':math_node.inputs[0].identifier,'value':.65}])
assert result['status']=='applied',result
assert peer.material_slots[0].material==mat and cube.material_slots[0].material!=mat
assert fingerprint(mat.node_tree)==mat_before and fingerprint(group)==group_before
assert hashlib.sha256(Path(image.filepath).read_bytes()).hexdigest()==image_hash
root_owner={'kind':'shader','object':cube.name,'material_slot':0}
result=patch(root_owner,[{'action':'set_input','node':'Principled BSDF','socket':socket(bsdf,'Roughness'),'value':.1}])
assert result['status']=='rolled_back' and 'Linked input' in result['error'],result

comp=bpy.data.node_groups.new('SharedCompositor','CompositorNodeTree')
comp.interface.new_socket(name='Image',in_out='OUTPUT',socket_type='NodeSocketColor')
color=comp.nodes.new('CompositorNodeRGB');color.name='Color';color.outputs[0].default_value=(.2,.4,.6,1)
exposure=comp.nodes.new('CompositorNodeExposure');exposure.name='Exposure'
output=comp.nodes.new('NodeGroupOutput');comp.links.new(color.outputs[0],exposure.inputs['Image']);comp.links.new(exposure.outputs[0],output.inputs[0])
scene=bpy.context.scene;protected_scene=bpy.data.scenes.new('ProtectedScene');scene.compositing_node_group=comp;protected_scene.compositing_node_group=comp
comp_before=fingerprint(comp)
comp_owner={'kind':'compositor','scene':scene.name}
result=patch(comp_owner,[{'action':'set_input','node':'Exposure','socket':socket(exposure,'Exposure'),'value':.5}])
assert result['status']=='applied',result
assert protected_scene.compositing_node_group==comp and scene.compositing_node_group!=comp and fingerprint(comp)==comp_before
assert not any(s.name.startswith('BridgeGraphEvaluation_') for s in bpy.data.scenes)

# Runtime protocol: exact session/revision, duplicate request id, no write replay.
request={'operation':'node_graph.patch','args':{'owner':owner,'graph_token':run('node_graph.inspect',{'owner':owner})['graph_token'],
    'actions':[{'action':'add_node','node':'ProtocolNode','node_type':'ShaderNodeMath'}]},'session':state.session,'revision':state.revision,'request_id':str(uuid.uuid4())}
for field,value,code in [('session','wrong','STALE_SESSION'),('revision',state.revision+1,'STALE_REVISION')]:
    try:state.submit({**request,field:value})
    except BridgeError as exc:assert exc.code==code,(field,exc.code)
    else:raise AssertionError('Invalid context accepted')
first=state.submit(request);again=state.submit(request);assert first['id']==again['id']
state.execute_one(ops.execute,snapshot)
assert state.jobs[request['request_id']]['result']['status']=='applied'
assert state.submit(request)['state']=='succeeded'
assert len([n for n in cube.modifiers['ExactGeometry'].node_group.nodes if n.name=='ProtocolNode'])==1

# Export semantics: unknown remains unknown; a supplied measurement is preserved exactly.
package=run('export.package',{'objects':[cube.name],'directory':'handoff-unknown','formats':['fbx'],'profile':{'require_uv':False}})
assert package['schema_version']==2 and package['semantic_forward']['basis']=='unknown'
declared={'axis':'+X','basis':'measured','evidence':'fixture translation axis in evaluated mesh'}
package2=run('export.package',{'objects':[cube.name],'directory':'handoff-measured','formats':['fbx'],'profile':{'require_uv':False},'semantic_forward':declared})
assert package2['semantic_forward']==declared and package2['export_axes']['fbx']['forward']=='-Y'
plan=run('export.prepare_ue',{'manifest':package2['manifest']['path']})
assert json.loads(Path(plan['path']).read_text())['semantic_forward']==declared
scene.compositing_node_group=None
scene.render.engine='BLENDER_EEVEE';scene.render.resolution_x=256;scene.render.resolution_y=256;scene.render.resolution_percentage=100
scene.render.filepath=str(OUT/'graph-result.png');bpy.ops.render.render(write_still=True)
scene.compositing_node_group=bpy.data.node_groups[result['root']]
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'graph-result.blend'))
(OUT/'node-graph-evidence.json').write_text(json.dumps({'state':'passed','blender':bpy.app.version_string,'cases':evidence,'protected_texture_sha256':image_hash,'artifact':'graph-result.blend'},indent=2))
print('NODE_GRAPH_REAL_PASS',len(evidence))
