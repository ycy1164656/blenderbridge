"""Targeted final coverage in a separately owned factory-startup Blender."""
import json,sys,uuid,traceback
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
import bpy,bmesh
from blender_bridge.core import RuntimeState,atomic_json
from blender_bridge.operations import Operations
from blender_bridge.catalog import OPS,validate
OUT=REPO/'artifacts/native-modeling/delivery-fixture'/uuid.uuid4().hex[:12]
state=RuntimeState(OUT);ops=Operations(state);results=[];evidence={}
def run(op,args):
    validate(args,OPS[op]['inputSchema']);return ops.execute(op,args)
def record(label,fn):
    try:fn();results.append({'test':label,'state':'passed'})
    except Exception as exc:results.append({'test':label,'state':'failed','error':str(exc),'traceback':traceback.format_exc()})
def volume(name):
    bm=bmesh.new()
    try:bm.from_mesh(bpy.data.objects[name].data);return bm.calc_volume(signed=True)
    finally:bm.free()
def geometry():
    square=[[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]]
    run('geometry.profile',{'name':'Plate','points':square,'depth':.2})
    assert abs(volume('Plate')-.8)<1e-5
    run('geometry.sweep',{'name':'Sweep','profile':[[-.1,-.1],[.1,-.1],[.1,.1],[-.1,.1]],'path':[[0,0,0],[0,0,1],[.5,0,2]]})
    assert volume('Sweep')>0 and run('mesh.inspect',{'object':'Sweep'})['health']['non_manifold_edges']==0
    try:run('geometry.sweep',{'name':'BadSweep','profile':[[-1,-1],[1,-1],[1,1],[-1,1]],'path':[[0,0,0],[0,0,0]]})
    except ValueError:pass
    else:raise AssertionError('Degenerate sweep accepted')
    run('geometry.curve',{'name':'Cable','points':[[0,0,0],[0,0,1],[.5,0,2]],'kind':'BEZIER','radius':.05})
    ob=bpy.data.objects['Cable'].evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ob.to_mesh()
    try:assert len(mesh.polygons)>0
    finally:ob.to_mesh_clear()
    first=[[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]];second=[[x,y,1] for x,y,z in first]
    mesh=bpy.data.meshes.new('LoopMesh');mesh.from_pydata(first+second,[],[[3,2,1,0],[4,5,6,7]]);ob=bpy.data.objects.new('LoopBody',mesh);bpy.context.scene.collection.objects.link(ob)
    run('scene.identify',{'objects':[ob.name]});run('mesh.bridge_loops',{'object':ob.name,'first':[0,1,2,3],'second':[4,5,6,7],'closed':True})
    assert run('mesh.inspect',{'object':ob.name})['health']['non_manifold_edges']==0 and volume(ob.name)>0
    strip=run('retopo.strip',{'name':'QuadRail','first':[[0,0,0],[0,1,0],[0,2,0]],'second':[[1,0,0],[1,1,0],[1,2,0]]})
    assert strip['faces']==2
    evidence['geometry']={'profile_volume':volume('Plate'),'sweep_volume':volume('Sweep'),'bridge_volume':volume('LoopBody'),'curve_evaluated':True}
def uv_normal():
    mesh=bpy.data.meshes.new('TwoFaces');mesh.from_pydata([[0,0,0],[1,0,0],[1,1,0],[0,1,0],[2,0,0],[3,0,0],[3,1,0],[2,1,0]],[],[[0,1,2,3],[4,5,6,7]])
    ob=bpy.data.objects.new('Padding',mesh);bpy.context.scene.collection.objects.link(ob);run('scene.identify',{'objects':[ob.name]});uv=mesh.uv_layers.new()
    coords=[(.1,.1),(.4,.1),(.4,.4),(.1,.4),(.41,.1),(.71,.1),(.71,.4),(.41,.4)]
    for loop,co in zip(uv.data,coords):loop.uv=co
    no_padding=run('uv.validate',{'object':ob.name,'resolution':128,'padding_pixels':0});close=run('uv.validate',{'object':ob.name,'resolution':128,'padding_pixels':4})
    assert no_padding['state']=='passed' and close['padding_conflicts']>0
    for loop in list(uv.data)[4:]:loop.uv.x+=.12
    separated=run('uv.validate',{'object':ob.name,'resolution':128,'padding_pixels':4});assert separated['state']=='passed'
    run('material.create',{'name':'NormalMaterial'});im=bpy.data.images.new('NormalTest',width=16,height=16);im.colorspace_settings.name='Non-Color';im.pixels[:]=[.5,.7,1,1]*256
    path=OUT/'normal.png';path.parent.mkdir(parents=True,exist_ok=True);im.filepath_raw=str(path);im.file_format='PNG';im.save()
    for _ in range(2):run('material.relink',{'material':'NormalMaterial','channel':'Normal','path':str(path),'flip_normal_y':True})
    tree=bpy.data.materials['NormalMaterial'].node_tree
    assert sum(n.name=='BridgeNormalInvertY' for n in tree.nodes)==1
    assert tree.nodes['BridgeNormalMap'].inputs['Color'].links[0].from_node.name=='BridgeNormalCombine'
    run('material.relink',{'material':'NormalMaterial','channel':'Normal','path':str(path),'flip_normal_y':False})
    assert tree.nodes['BridgeNormalMap'].inputs['Color'].links[0].from_node.name=='Bridge_Normal'
    assert tree.nodes['Bridge_Normal'].image.colorspace_settings.name=='Non-Color'
    evidence['uv']={'near':close,'separated':separated,'normal_flip_idempotent':True}
def imports():
    run('uv.unwrap',{'object':'Plate'});package=run('export.package',{'objects':['Plate'],'directory':'imports-source','formats':['fbx','glb','obj']})
    records=[]
    for extension in ('glb','obj','fbx','blend'):
        path=next(a['path'] for a in package['artifacts'] if a['path'].endswith('.'+extension))
        before=set(bpy.data.objects)
        run('collection.create',{'name':'Imported_'+extension})
        result=run('asset.append' if extension=='blend' else 'asset.import',{'path':path,'collection':'Imported_'+extension,'prefix':extension+'_','scale':2,**({'objects':['Plate']} if extension=='blend' else {})})
        added=[o for o in set(bpy.data.objects)-before if o.type=='MESH'];assert len(added)==1
        bpy.context.view_layer.update();dimensions=list(added[0].dimensions);assert all(abs(a-b)<1e-4 for a,b in zip(dimensions,[4,4,.4])),(extension,dimensions)
        assert added[0].data.uv_layers.active;records.append({'format':extension,'dimensions':dimensions,'result':result})
    evidence['imports']=records
def recovery_images():
    run('mesh.primitive',{'name':'Recovery','kind':'cube'})
    views=run('preview.camera_set',{'name':'RecoveryCamera','center':[0,0,0],'scale':4})['views'][:1]
    before=run('preview.multiview',{'objects':['Recovery'],'views':views,'directory':'before','width':480,'height':360})
    cp=run('checkpoint.create',{'label':'visual_restore','objects':['Recovery']})
    run('mesh.region_transform',{'object':'Recovery','indices':[0,1],'delta':[0,0,.5]})
    edited=run('preview.multiview',{'objects':['Recovery'],'views':views,'directory':'edited','width':480,'height':360})
    restored=run('checkpoint.restore',{'checkpoint_id':cp['checkpoint_id'],'name':'Restored'})
    after=run('preview.multiview',{'objects':restored['objects'],'views':views,'directory':'restored','width':480,'height':360})
    def pixels(record):
        im=bpy.data.images.load(record['images'][0]['path'],check_existing=False)
        try:return tuple(im.pixels[:])
        finally:bpy.data.images.remove(im)
    assert pixels(before)==pixels(after) and pixels(before)!=pixels(edited)
    evidence['recovery']={'before':before,'edited':edited,'restored':after,'original_changed_scene_preserved':True,'restored_pixels_equal':True,'png_metadata_may_differ':True}
for label,fn in [('loft_sweep_curve_bridge_strip',geometry),('uv_padding_normal_direction',uv_normal),('native_import_scale_four_formats',imports),('checkpoint_visual_restore',recovery_images)]:record(label,fn)
atomic_json(OUT/'result.json',{'results':results,'evidence':evidence,'artifacts':state.artifacts});print('DELIVERY_FIXTURE_RESULT '+str(OUT/'result.json'),flush=True)
if any(r['state']=='failed' for r in results):raise RuntimeError(json.dumps(results))
