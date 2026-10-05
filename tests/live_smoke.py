"""Integration scenario through the public client; run against an owned fresh runtime."""
import json
from pathlib import Path
import sys
import uuid
from blender_bridge.client import connect

c = connect()
results = []


def run(name, args, timeout=60):
    health = c.call('health')
    job = c.submit(name,args,health['revision'],str(uuid.uuid4()))
    job = c.wait(job['id'],timeout)
    if job['state'] != 'succeeded': raise RuntimeError(json.dumps(job))
    results.append({'operation':name,'job':job['id'],'state':job['state']})
    print(f"PASS {name}",flush=True)
    return job['result']


run('collection.create',{'name':'BridgeSmoke'})
# An angular, editable plate. No hidden Python generator: each edit uses public operations.
plate = run('mesh.create',{'name':'ArmorStudy','collection':'BridgeSmoke',
    'vertices':[[-1,-.4,0],[1,-.4,0],[.8,.4,0],[-.8,.4,0],[-.9,-.35,.35],[.9,-.35,.35],[.65,.35,.45],[-.65,.35,.45]],
    'faces':[[0,3,2,1],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7],[4,5,6,7]]})
run('mesh.vertices',{'object':'ArmorStudy','indices':[6,7],'delta':[0,0,.2]})
run('mesh.edit',{'object':'ArmorStudy','action':'inset_faces','indices':[5],'amount':.12})
mesh = run('mesh.inspect',{'object':'ArmorStudy'})
top = max(mesh['face_data'],key=lambda f:sum(mesh['vertex_data'][i]['co'][2] for i in f['vertices'])/len(f['vertices']))['index']
run('mesh.edit',{'object':'ArmorStudy','action':'extrude_faces','indices':[top],'offset':[0,0,.13]})
run('modifier.add',{'object':'ArmorStudy','name':'EdgeBevel','kind':'BEVEL','width':.035,'segments':3})
run('modifier.apply',{'object':'ArmorStudy','name':'EdgeBevel'})
run('uv.unwrap',{'object':'ArmorStudy'})
run('material.create',{'name':'ArmorOchre','color':[.5,.23,.04,1],'metallic':.7,'roughness':.32})
run('material.assign',{'object':'ArmorStudy','material':'ArmorOchre'})
run('mesh.primitive',{'name':'Mount','kind':'cylinder','scale':[.25,.25,.2],'location':[0,0,-.22],'collection':'BridgeSmoke'})
run('object.transform',{'object':'Mount','rotation':[0,0,.25],'apply':True})
run('mesh.edit',{'object':'Mount','action':'bevel_edges','indices':[0,1,2],'amount':.015,'segments':2})
run('mesh.edit',{'object':'Mount','action':'subdivide_edges','indices':[3],'segments':1})
run('mesh.edit',{'object':'Mount','action':'recalc_normals'})
run('rig.create',{'name':'FixtureRig','bones':[{'name':'root','head':[0,0,-.2],'tail':[0,0,.3]},{'name':'plate','head':[0,0,.3],'tail':[0,0,1],'parent':'root'}]})
count = run('object.inspect',{'object':'ArmorStudy'})['vertices']
bound = run('rig.bind',{'object':'ArmorStudy','armature':'FixtureRig','weights':[{'bone':'plate','indices':list(range(count)),'weight':1}]})
assert bound['weights'] == {'unweighted':0,'non_normalized':0}
run('animation.keyframe',{'object':'FixtureRig','bone':'plate','frame':1,'rotation':[0,0,0]})
run('animation.keyframe',{'object':'FixtureRig','bone':'plate','frame':12,'rotation':[0,.3,0]})
run('animation.keyframe',{'object':'FixtureRig','bone':'plate','frame':24,'rotation':[0,0,0]})
run('animation.frame',{'frame':1})
run('camera.create',{'name':'ReviewCamera','location':[3,-4,3],'target':[0,0,.2],'orthographic_scale':3.4})
run('light.create',{'name':'ReviewKey','location':[1,-3,5],'target':[0,0,0],'energy':1200,'size':4})
run('object.select',{'objects':['ArmorStudy']})
image = run('preview.render',{'camera':'ReviewCamera','path':'smoke/clay.png','objects':['ArmorStudy','Mount'],'width':960,'height':540,'style':'clay'})
run('preview.render',{'camera':'ReviewCamera','path':'smoke/material.png','objects':['ArmorStudy','Mount'],'width':960,'height':540,'style':'material'},180)
run('reference.add',{'name':'SmokeReference','path':image['path'],'location':[0,2,0],'rotation':[1.570796,0,0]})
run('scene.save',{'path':'smoke/model.blend','copy':False})
run('export.fbx',{'objects':['ArmorStudy','Mount','FixtureRig'],'path':'smoke/model.fbx','animation':True})
final = run('mesh.inspect',{'object':'ArmorStudy','limit':1})
assert final['health']['zero_area_faces'] == 0 and final['health']['non_manifold_edges'] == 0, final
report = {'health':c.call('health'),'operations':results,'mesh_health':final['health'], 'artifacts':c.call('artifacts')}
path = Path(c.call('health')['output_root'])/'smoke'/'integration.json'
path.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'passed':len(results),'report':str(path)}))
