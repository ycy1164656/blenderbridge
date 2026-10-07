"""Real Blender tests, intended ONLY for a factory-startup owned background process."""
import json
from pathlib import Path
import sys
import traceback
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'src'))
import bpy
from blender_bridge.core import RuntimeState
from blender_bridge.operations import Operations
from blender_bridge.catalog import OPS,validate

OUT=REPO/'artifacts'/'native-modeling'/'native-fixture'/uuid.uuid4().hex[:12]
state=RuntimeState(OUT)
ops=Operations(state)
results=[]

def run(name,args):
    validate(args,OPS[name]['inputSchema'])
    return ops.execute(name,args)

def test(label,fn):
    print('TEST_START '+label,flush=True)
    try:
        fn();results.append({'test':label,'state':'passed'});print('TEST_PASS '+label,flush=True)
    except Exception as exc:
        results.append({'test':label,'state':'failed','error':str(exc),'traceback':traceback.format_exc()})
        raise

def geometry():
    r=run('geometry.loft',{'name':'FixtureHull','sections':[[[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],[[-.8,-.8,2],[.8,-.8,2],[.8,.8,2],[-.8,.8,2]]]})
    assert run('mesh.inspect',{'object':'FixtureHull'})['health']['non_manifold_edges']==0
    run('modifier.add',{'object':'FixtureHull','name':'Round','kind':'BEVEL','properties':{'width':.05,'segments':2}})
    base=run('mesh.inspect',{'object':'FixtureHull','mode':'base'})
    evaluated=run('mesh.inspect',{'object':'FixtureHull','mode':'evaluated'})
    assert evaluated['vertices']>base['vertices']
    run('scene.identify',{'objects':['FixtureHull']})
    run('part.register',{'part_id':'protected_low','objects':['FixtureHull'],'indices':[0,1,2,3]})
    run('part.lock',{'part_id':'protected_low'})
    before=[list(v.co) for v in bpy.data.objects['FixtureHull'].data.vertices[:4]]
    run('mesh.region_transform',{'object':'FixtureHull','indices':[4,5,6,7],'delta':[0,0,.1]})
    assert before==[list(v.co) for v in bpy.data.objects['FixtureHull'].data.vertices[:4]]
    try:run('mesh.region_transform',{'object':'FixtureHull','indices':[0],'delta':[0,0,.1]})
    except Exception as exc:assert getattr(exc,'code',None)=='PROTECTED_REGION_TOUCHED'
    else:raise AssertionError('Protected part edit succeeded')
    run('part.unlock',{'part_id':'protected_low'})

def surface():
    run('uv.unwrap',{'object':'FixtureHull'})
    r=run('uv.inspect',{'object':'FixtureHull'})
    assert r['pixels_per_meter']>0
    uv=run('uv.validate',{'object':'FixtureHull','resolution':128,'padding_pixels':0})
    assert uv['overlap_pixels']==0,uv
    run('material.create',{'name':'FixtureSteel'})
    run('material.assign',{'object':'FixtureHull','material':'FixtureSteel'})
    before=run('scene.fingerprint',{'objects':['FixtureHull']})
    run('material.update',{'material':'FixtureSteel','roughness':.7,'noise_scale':10})
    assert before!=run('scene.fingerprint',{'objects':['FixtureHull']})

def preview():
    cameras=run('preview.camera_set',{'name':'FixtureCamera','center':[0,0,1],'scale':4})
    r=run('preview.multiview',{'objects':['FixtureHull'],'views':cameras['views'][:1],'directory':'views','width':320,'height':240})
    assert r['images'][0]['bytes']>1000
    record=r['images'][0]
    run('selection.pick',{'artifact_id':record['id'],'pixel':[160,120],'objects':['FixtureHull'],'radius':2})
    run('preview.multiview',{'objects':['FixtureHull'],'views':cameras['views'][:1],'directory':'parts','width':320,'height':240,'style':'parts'})

def rig():
    run('rig.create',{'name':'FixtureRig','bones':[{'name':'Root','head':[0,0,0],'tail':[0,0,1]}]})
    run('rig.bind_rigid',{'armature':'FixtureRig','bindings':[{'object':'FixtureHull','bone':'Root'}]})
    group=bpy.data.objects['FixtureHull'].vertex_groups.new(name='NonBoneMask');group.add(list(range(8)),.7,'REPLACE')
    assert run('rig.validate',{'object':'FixtureHull','armature':'FixtureRig'})['state']=='passed'
    result=run('animation.pose_test',{'armature':'FixtureRig','objects':['FixtureHull'],'poses':[{'label':'Rotate','bones':{'Root':{'rotation':[0,.3,0]}}}],'directory':'pose'})
    assert result['restored']
    assert result['poses'][0]['measurements'][0]['max_edge_length_change']<1e-5

def checkpoint():
    old_session=state.session
    checkpoint=run('checkpoint.create',{'label':'fixture','objects':['FixtureHull','FixtureRig']})
    print('CHECKPOINT_WRITTEN '+checkpoint['source']['path'],flush=True)
    result=run('checkpoint.restore',{'checkpoint_id':checkpoint['checkpoint_id'],'name':'Restored'})
    assert state.session!=old_session
    assert 'FixtureHull' in bpy.context.scene.objects
    assert len(result['objects'])==2

def retopo():
    run('mesh.primitive',{'name':'HighSurface','kind':'sphere','location':[5,0,1],'segments':24})
    before=run('scene.fingerprint',{'objects':['HighSurface']})
    run('retopo.prepare',{'source':'HighSurface','name':'LowSurface'})
    run('retopo.remesh',{'object':'LowSurface','method':'decimate','ratio':.5,'allow_data_loss':True})
    assert before==run('scene.fingerprint',{'objects':['HighSurface']})
    check=run('retopo.validate',{'object':'LowSurface','source':'HighSurface','max_distance':.2})
    assert check['max_deviation']<.2,check
    run('uv.unwrap',{'object':'LowSurface'})
    run('game.collision',{'object':'LowSurface','name':'UCX_LowSurface_00','kind':'convex'})
    lod=run('game.lod',{'object':'LowSurface','ratios':[.5]})
    assert lod['lods'][0]['object']['triangles']<run('mesh.inspect',{'object':'LowSurface'})['triangles']

def bake():
    run('material.create',{'name':'BakeCopper','color':[.5,.15,.035,1],'metallic':.7,'roughness':.4})
    run('material.assign',{'object':'HighSurface','material':'BakeCopper'})
    run('material.assign',{'object':'LowSurface','material':'BakeCopper'})
    plan=run('bake.prepare',{'high':['HighSurface'],'low':'LowSurface','channels':['Normal','AO','BaseColor','Roughness','Metallic'],'resolution':64,'margin':2,'ray_distance':.25,'directory':'bake'})
    before=run('scene.fingerprint',{'objects':['HighSurface','LowSurface']})
    result=run('bake.execute',{'plan_id':plan['plan_id']})
    assert result['state']=='completed'
    assert len(result['artifacts'])==5
    assert before==run('scene.fingerprint',{'objects':['HighSurface','LowSurface']})
    assert run('bake.inspect',{'plan_id':plan['plan_id']})['usable']
    normal=next(a for a in result['artifacts'] if a['provenance']['channel']=='Normal')
    run('material.relink',{'material':'BakeCopper','channel':'Normal','path':normal['path']})
    assert run('bake.inspect',{'plan_id':plan['plan_id']})['stale_sources']

def export():
    run('animation.keyframe',{'object':'FixtureRig','bone':'Root','frame':1,'rotation':[0,0,0]})
    run('animation.keyframe',{'object':'FixtureRig','bone':'Root','frame':10,'rotation':[0,.25,0]})
    run('animation.frame',{'frame':1})
    result=run('export.package',{'objects':['FixtureHull','FixtureRig'],'directory':'export','formats':['fbx','glb','obj'],'animation':True,'frame_start':1,'frame_end':10})
    assert len(result['artifacts'])==5
    print('DELIVERY_MANIFEST '+result['manifest']['path'],flush=True)

try:
    for name,fn in [('geometry_protection_evaluated',geometry),('uv_pbr_hash',surface),('fixed_render_ray',preview),('rig_deform_pose',rig),('checkpoint_new_candidate',checkpoint),('retopo_collision_lod',retopo),('bake_actual_channels',bake),('export_package',export)]:test(name,fn)
finally:
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'result.json').write_text(json.dumps({'results':results,'artifacts':state.artifacts},indent=2),encoding='utf-8')
    print('NATIVE_FIXTURE_RESULT '+str(OUT/'result.json'),flush=True)
