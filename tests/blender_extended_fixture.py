"""Boundary and flexible-joint tests on a separate, owned factory Blender process."""
import json,math,sys,traceback,uuid
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
import bpy
from blender_bridge.core import RuntimeState,atomic_json
from blender_bridge.operations import Operations
from blender_bridge.catalog import OPS,validate
from blender_bridge.operations_impl.common import fingerprint
from blender_bridge.operations_impl.textures import save_raw_image
OUT=REPO/'artifacts/native-modeling/extended-fixture'/uuid.uuid4().hex[:12]
state=RuntimeState(OUT);ops=Operations(state);results=[];evidence={}
bpy.context.window.scene=bpy.data.scenes.new('OwnedExtendedFixture')

def run(op,args):validate(args,OPS[op]['inputSchema']);return ops.execute(op,args)
def rejects(op,args,code=None):
    try:run(op,args)
    except Exception as exc:
        if code:assert getattr(exc,'code',None)==code,(code,type(exc).__name__,str(exc))
        return str(exc)
    raise AssertionError('Expected rejection: '+op)
def record(label,fn):
    print('TEST_START '+label,flush=True)
    try:fn();results.append({'test':label,'state':'passed'});print('TEST_PASS '+label,flush=True)
    except Exception as exc:results.append({'test':label,'state':'failed','error':str(exc),'traceback':traceback.format_exc()});print('TEST_FAIL '+label+' '+str(exc),flush=True)

def identity():
    original=run('mesh.primitive',{'name':'IdentityCube','kind':'cube'})
    rejects('mesh.primitive',{'name':'IdentityCube','kind':'cube'})
    run('object.duplicate',{'object':'IdentityCube','name':'LinkedCube','linked':True})
    rejects('mesh.region_transform',{'object':'LinkedCube','indices':[0],'delta':[0,0,.1]},'SHARED_MESH')
    run('object.make_single_user',{'object':'LinkedCube'})
    before=fingerprint(bpy.data.objects['IdentityCube']);run('mesh.region_transform',{'object':'LinkedCube','indices':[0],'delta':[0,0,.1]});assert before==fingerprint(bpy.data.objects['IdentityCube'])
    renamed=run('object.rename',{'object':original['object_id'],'name':'IdentityRenamed'});assert renamed['object_id']==original['object_id']
    run('part.register',{'part_id':'join-source','objects':['IdentityRenamed']})
    run('object.join',{'objects':['IdentityRenamed','LinkedCube'],'name':'Joined'})
    separated=run('object.separate',{'object':'Joined','name':'Pieces','mode':'loose'});assert len(separated['created'])==1,separated
    evidence['identity']=separated

def modifiers():
    run('mesh.primitive',{'name':'ModHull','kind':'cube','location':[4,0,0]})
    run('modifier.add',{'object':'ModHull','name':'Round','kind':'BEVEL','properties':{'width':.10,'segments':2}})
    run('modifier.add',{'object':'ModHull','name':'Tri','kind':'TRIANGULATE'})
    first=run('mesh.inspect',{'object':'ModHull','mode':'evaluated'})
    run('modifier.update',{'object':'ModHull','name':'Round','properties':{'segments':4}})
    second=run('mesh.inspect',{'object':'ModHull','mode':'evaluated'});assert second['vertices']>first['vertices']
    run('modifier.reorder',{'object':'ModHull','name':'Round','index':1})
    assert run('modifier.inspect',{'object':'ModHull'})['modifiers'][1]['name']=='Round'
    rejects('modifier.update',{'object':'ModHull','name':'Round','properties':{'invented_option':True}},'UNSUPPORTED_CAPABILITY')
    count=len(bpy.data.meshes)
    for _ in range(3):run('mesh.inspect',{'object':'ModHull','mode':'evaluated'})
    assert len(bpy.data.meshes)==count

def picking():
    run('mesh.primitive',{'name':'PickNear','kind':'cube','location':[10,-.3,0],'scale':[.4,.3,.5]})
    run('mesh.primitive',{'name':'PickFar','kind':'cube','location':[10,.6,0],'scale':[.4,.3,.5]})
    for kind in ('ortho','perspective'):
        args={'name':'PickCamera_'+kind,'location':[10,-5,0],'target':[10,0,0]}
        if kind=='ortho':args['orthographic_scale']=3
        run('camera.create',args)
        image=run('preview.render',{'camera':args['name'],'path':'picking/'+kind+'.png','width':320,'height':240,'objects':['PickNear','PickFar']})
        hit=run('selection.pick',{'artifact_id':image['id'],'objects':['PickNear','PickFar'],'pixel':[159.5,119.5],'radius':2})
        assert hit['hits'][0]['object']=='PickNear' and len(hit['hits'])==1
        assert not hit['evaluated_indices_are_editable']
        crop=run('selection.pick',{'artifact_id':image['id'],'objects':['PickNear','PickFar'],'pixel':[79.5,59.5],'radius':2,'image_transform':{'source_rectangle':[80,60,240,180],'display_size':[160,120]}})
        assert max(abs(a-b) for a,b in zip(hit['hits'][0]['world'],crop['hits'][0]['world']))<1e-6
        rectangle=run('selection.pick',{'artifact_id':image['id'],'objects':['PickNear','PickFar'],'rectangle':[0,0,320,240],'visible_only':False})
        assert all(s['count']>=8 for s in rectangle['selections'])
        selection=hit['selections'][0]
        run('mesh.edit',{'object':'PickNear','action':'subdivide_edges','indices':list(range(len(bpy.data.objects['PickNear'].data.edges))),'segments':1})
        rejects('mesh.region_transform',{'object':'PickNear','selection_id':selection['selection_id'],'delta':[0,0,.1]},'STALE_SELECTION')
        rejects('preview.validate',{'artifact_ids':[image['id']]},'REVIEW_STALE')
    evidence['picking']='orthographic/perspective, source crop-resize mapping, nearest occlusion, base mapping/staleness verified'

def uv_projection():
    run('mesh.create',{'name':'ProjectionTarget','vertices':[[19,-1,0],[21,-1,0],[21,1,0],[19,1,0]],'faces':[[0,1,2,3]]})
    run('uv.unwrap',{'object':'ProjectionTarget'})
    inspect=run('uv.inspect',{'object':'ProjectionTarget','resolution':128});density=inspect['pixels_per_meter']
    run('uv.set_density',{'object':'ProjectionTarget','pixels_per_meter':density*.8,'resolution':128});after=run('uv.inspect',{'object':'ProjectionTarget','resolution':128})
    assert abs(after['pixels_per_meter']/density-.8)<.001
    run('camera.create',{'name':'ProjectionFront','location':[20,0,5],'target':[20,0,0],'orthographic_scale':2.1})
    run('camera.create',{'name':'ProjectionBack','location':[20,0,-5],'target':[20,0,0],'orthographic_scale':2.1})
    img=bpy.data.images.new('InputChecker',64,64,alpha=True);pixels=[]
    for y in range(64):
        for x in range(64):pixels.extend((1,.1,.05,1) if x<32 else (.05,.1,1,1))
    img.pixels.foreach_set(pixels);source=OUT/'projection/input.png';source.parent.mkdir(parents=True);save_raw_image(img,source);bpy.data.images.remove(img)
    a=run('texture.project',{'object':'ProjectionTarget','views':[{'camera':'ProjectionFront','image':str(source)}],'path':'projection/front.png','resolution':64})
    b=run('texture.project',{'object':'ProjectionTarget','views':[{'camera':'ProjectionBack','image':str(source)}],'path':'projection/back.png','resolution':64})
    assert a['coverage_fraction']>.98 and b['coverage_fraction']==0,(a,b)
    run('mesh.primitive',{'name':'ProjectionBlocker','kind':'cube','location':[19.5,0,1],'scale':[.5,1,.1]})
    blocked=run('texture.project',{'object':'ProjectionTarget','views':[{'camera':'ProjectionFront','image':str(source)}],'path':'projection/blocked.png','resolution':64})
    assert .30<blocked['coverage_fraction']<.70,blocked
    evidence['projection']={'front':a,'back':b,'occluded':blocked}
    run('mesh.primitive',{'name':'OverlapCube','kind':'cube','location':[24,0,0]});run('uv.unwrap',{'object':'OverlapCube'})
    ob=bpy.data.objects['OverlapCube'];uv=ob.data.uv_layers.active
    for polygon in ob.data.polygons:
        for index,loop in enumerate(polygon.loop_indices):uv.data[loop].uv=[(.1,.1),(.4,.1),(.4,.4),(.1,.4)][index]
    accidental=run('uv.validate',{'object':ob.name,'resolution':64});intentional=run('uv.validate',{'object':ob.name,'resolution':64,'allow_overlap':True})
    assert accidental['overlap_pixels']>0 and intentional['overlap_pixels']==accidental['overlap_pixels']
    evidence['uv_overlap']={'accidental':accidental,'intentional':intentional}

def flexible():
    vertices=[];faces=[];rings=9;n=12
    for ring in range(rings):
        for j in range(n):vertices.append([30+.22*math.cos(j*2*math.pi/n),.22*math.sin(j*2*math.pi/n),ring*.25])
    for ring in range(rings-1):
        for j in range(n):faces.append([ring*n+j,ring*n+(j+1)%n,(ring+1)*n+(j+1)%n,(ring+1)*n+j])
    faces += [list(reversed(range(n))),list(range((rings-1)*n,rings*n))]
    run('mesh.create',{'name':'FlexibleJoint','vertices':vertices,'faces':faces})
    run('rig.create',{'name':'FlexRig','bones':[{'name':'Lower','head':[30,0,0],'tail':[30,0,1]},{'name':'Upper','head':[30,0,1],'tail':[30,0,2],'parent':'Lower'}]})
    weights=[]
    for ring in range(rings):
        mix=max(0,min(1,(ring*.25-.55)/.90));indices=list(range(ring*n,(ring+1)*n))
        weights.extend([{'bone':'Lower','indices':indices,'weight':1-mix},{'bone':'Upper','indices':indices,'weight':mix}])
    run('rig.bind',{'object':'FlexibleJoint','armature':'FlexRig','weights':weights})
    run('rig.weights_edit',{'object':'FlexibleJoint','armature':'FlexRig','action':'smooth','indices':list(range(3*n,6*n)),'iterations':1})
    assert run('rig.weights_normalize',{'object':'FlexibleJoint','armature':'FlexRig','max_influences':2})['state']=='passed'
    mask=bpy.data.objects['FlexibleJoint'].vertex_groups.new(name='MaskNotBone');mask.add(list(range(rings*n)),1,'REPLACE')
    validation=run('rig.validate',{'object':'FlexibleJoint','armature':'FlexRig'});assert validation['state']=='passed'
    run('uv.unwrap',{'object':'FlexibleJoint'})
    run('camera.create',{'name':'FlexCamera','location':[30,-5,1.1],'target':[30,0,1.1],'orthographic_scale':3.2})
    poses=run('animation.pose_test',{'armature':'FlexRig','objects':['FlexibleJoint'],'poses':[{'label':'rest','bones':{}},{'label':'bend45','bones':{'Upper':{'rotation':[0,0,-.785]}}},{'label':'bend90','bones':{'Upper':{'rotation':[0,0,-1.57]}}}],'camera':'FlexCamera','directory':'flexible','width':640,'height':480})
    assert poses['restored'];evidence['flexible']={'poses':poses,'validation':validation}
    run('object.duplicate',{'object':'FlexibleJoint','name':'TransferJoint'})
    assert run('rig.weights_transfer',{'object':'TransferJoint','source':'FlexibleJoint','armature':'FlexRig','max_distance':.01})['unmatched_count']==0
    run('rig.weights_edit',{'object':'TransferJoint','armature':'FlexRig','action':'clear','indices':[0,1]})
    assert run('rig.validate',{'object':'TransferJoint','armature':'FlexRig'})['state']=='failed'
    run('rig.weights_normalize',{'object':'TransferJoint','armature':'FlexRig','fallback_bone':'Lower'})

def batch_restore():
    run('mesh.primitive',{'name':'RecoveryCube','kind':'cube','location':[40,0,0]})
    selection=run('selection.query',{'objects':['RecoveryCube'],'box_min':[39,-2,-2],'box_max':[41,2,2],'space':'world'})
    checkpoint=run('checkpoint.create',{'label':'before_measured_edit','objects':['RecoveryCube']});before=[list(v.co) for v in bpy.data.objects['RecoveryCube'].data.vertices]
    try:run('batch.execute',{'steps':[{'operation':'mesh.region_transform','args':{'object':'RecoveryCube','indices':[0,1],'delta':[0,0,.4]}},{'operation':'object.inspect','args':{'object':'missing-exact-object'}}]})
    except Exception as exc:
        assert len(exc.details['completed'])==1 and exc.details['failed_step']==1 and not exc.details['rollback_performed'];evidence['partial_batch']=exc.details
    else:raise AssertionError('Batch expected to fail')
    changed=[list(v.co) for v in bpy.data.objects['RecoveryCube'].data.vertices];assert changed!=before
    old_session=state.session;restored=run('checkpoint.restore',{'checkpoint_id':checkpoint['checkpoint_id'],'name':'RecoveredCandidate'})
    assert state.session!=old_session and [list(v.co) for v in bpy.data.objects[restored['objects'][0]].data.vertices]==before
    assert [list(v.co) for v in bpy.data.objects['RecoveryCube'].data.vertices]==changed
    rejects('mesh.region_transform',{'object':'RecoveryCube','selection_id':selection['selection_id'],'delta':[0,0,.1]},'STALE_SELECTION')
    evidence['restore']=restored

def sculpt_nodes_and_context():
    run('mesh.primitive',{'name':'SculptRegion','kind':'cube','location':[50,0,0]})
    ob=bpy.data.objects['SculptRegion'];before=[list(v.co) for v in ob.data.vertices]
    run('sculpt.mask',{'object':ob.name,'name':'AllowedRegion','indices':[0,1],'weight':1})
    run('sculpt.grab',{'object':ob.name,'indices':list(range(8)),'delta':[0,0,.2],'mask_group':'AllowedRegion'})
    assert all(list(ob.data.vertices[i].co)==before[i] for i in range(2,8))
    run('sculpt.inflate',{'object':ob.name,'indices':[0,1],'strength':.02,'mask_group':'AllowedRegion'})
    run('sculpt.smooth',{'object':ob.name,'indices':[0,1],'strength':.1,'iterations':2,'mask_group':'AllowedRegion'})
    run('sculpt.flatten',{'object':ob.name,'indices':[0,1],'normal':[0,0,1],'strength':.3})
    assert all(list(ob.data.vertices[i].co)==before[i] for i in range(2,8))
    run('sculpt.symmetrize',{'object':ob.name,'axis':'X','tolerance':.5})
    run('retopo.prepare',{'source':ob.name,'name':'VoxelCandidate'});run('uv.unwrap',{'object':'VoxelCandidate'})
    rejects('retopo.remesh',{'object':'VoxelCandidate','method':'voxel','voxel_size':.3},'DATA_LOSS_CONFIRMATION_REQUIRED')
    result=run('retopo.remesh',{'object':'VoxelCandidate','method':'voxel','voxel_size':.3,'allow_data_loss':True});assert result['invalidated']
    from blender_bridge.operations_impl.surface import uv_context
    try:
        with uv_context(ob):raise RuntimeError('controlled UV context failure')
    except RuntimeError:pass
    assert bpy.context.mode=='OBJECT'
    # Authored test node group: exposed scalar controls actual geometry scale.
    run('mesh.primitive',{'name':'NodeCube','kind':'cube','location':[55,0,0]});node_ob=bpy.data.objects['NodeCube']
    tree=bpy.data.node_groups.new('FixtureGeometryScale','GeometryNodeTree');tree['source']='authored_test_fixture';tree['version']=1
    tree.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    scalar=tree.interface.new_socket(name='Scale',in_out='INPUT',socket_type='NodeSocketFloat');scalar.default_value=1;scalar.min_value=.1;scalar.max_value=4
    tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    a=tree.nodes.new('NodeGroupInput');b=tree.nodes.new('GeometryNodeTransform');z=tree.nodes.new('NodeGroupOutput');tree.links.new(a.outputs['Geometry'],b.inputs['Geometry']);tree.links.new(a.outputs['Scale'],b.inputs['Scale']);tree.links.new(b.outputs['Geometry'],z.inputs['Geometry'])
    modifier=node_ob.modifiers.new('ParametricGeometry','NODES');modifier.node_group=tree;node_ob.update_tag();bpy.context.view_layer.update()
    original=fingerprint(node_ob);initial=list(node_ob.dimensions)
    run('geometry_nodes.set_input',{'object':node_ob.name,'modifier':modifier.name,'identifier':scalar.identifier,'value':1.5})
    assert abs(node_ob.dimensions.x/initial[0]-1.5)<.001 and fingerprint(node_ob)!=original
    rejects('geometry_nodes.set_input',{'object':node_ob.name,'modifier':modifier.name,'identifier':scalar.identifier,'value':'wrong-type'})
    original=fingerprint(node_ob);b.inputs['Translation'].default_value=(0,0,.2);assert fingerprint(node_ob)!=original
    evidence['sculpt_nodes']={'mask_scope_preserved':True,'voxel_invalidations':result['invalidated'],'failed_uv_context_restored':True,'geometry_node_input_changes_actual_geometry':True,'node_group_change_invalidates_hash':True}

try:
    for label,fn in [('identity_shared_join_separate',identity),('modifier_order_and_no_leak',modifiers),('perspective_crop_occlusion_stale',picking),('uv_density_overlap_projection',uv_projection),('flexible_weights_pose_transfer',flexible),('partial_batch_checkpoint_restore',batch_restore),('sculpt_voxel_nodes_context',sculpt_nodes_and_context)]:record(label,fn)
finally:
    atomic_json(OUT/'result.json',{'results':results,'evidence':evidence,'artifacts':state.artifacts});print('EXTENDED_FIXTURE_RESULT '+str(OUT/'result.json'),flush=True)
if any(r['state']=='failed' for r in results):raise RuntimeError('Extended fixture failures')
