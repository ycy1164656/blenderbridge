"""Recipe-driven hard-surface engineering asset, independent of approved game content."""
import json,math,uuid
from pathlib import Path
from blender_bridge.client import connect
from blender_bridge.core import atomic_json
OUT=Path('C:/dev/BlenderBridge/artifacts/native-modeling');c=connect();h=c.call('health');revision=h['revision'];records=[]
def run(op,args):
    global revision
    j=c.wait(c.submit(op,args,revision,str(uuid.uuid4()))['id'],60)
    if j['state']!='succeeded':raise RuntimeError(json.dumps(j))
    revision=j['revision'];records.append({'operation':op,'args':args,'id':j['id']});return j['result']
run('collection.create',{'name':'A03_ParametricPylon'})
source=['A01_'+n for n in ['Base','Body','Cap','LeftArm','RightPanel','Antenna','Reactor']];names=[]
for old in source:
    new=old.replace('A01_','A03_');run('object.duplicate',{'object':old,'name':new,'collection':'A03_ParametricPylon'});names.append(new)
run('material.create',{'name':'A03_Steel','color':[.065,.12,.18,1],'metallic':.65,'roughness':.32})
run('material.create',{'name':'A03_Brass','color':[.62,.35,.065,1],'metallic':.55,'roughness':.36})
for name in names:run('material.assign',{'object':name,'material':'A03_Brass' if name.endswith(('LeftArm','Reactor')) else 'A03_Steel'})
run('mesh.primitive',{'name':'A03_ServiceGrooveOperand','kind':'cube','location':[.42,-.47,1.45],'scale':[.09,.16,.72],'collection':'A03_ParametricPylon'})
run('modifier.add',{'object':'A03_Body','name':'ServiceRecess','kind':'BOOLEAN','properties':{'object':'A03_ServiceGrooveOperand','operation':'DIFFERENCE','solver':'EXACT'}})
run('object.visibility',{'objects':['A03_ServiceGrooveOperand'],'render':False})
run('geometry.sweep',{'name':'A03_Joint','profile':[[.22*math.cos(j*math.tau/24),.22*math.sin(j*math.tau/24)] for j in range(24)],'path':[[-.43,0,2.89],[.43,0,2.89]],'up':[0,0,1],'collection':'A03_ParametricPylon'})
run('material.assign',{'object':'A03_Joint','material':'A03_Brass'});names.append('A03_Joint')
run('geometry.sweep',{'name':'A03_Conduit','profile':[[.045*math.cos(j*math.tau/12),.045*math.sin(j*math.tau/12)] for j in range(12)],'path':[[.46,.32,2.55],[.8,.32,2.55],[1.03,.32,2.26],[1.03,.32,1.62]],'up':[0,1,0],'collection':'A03_ParametricPylon'})
run('material.assign',{'object':'A03_Conduit','material':'A03_Brass'});names.append('A03_Conduit')
views=run('preview.camera_set',{'name':'A03Camera','center':[0,0,1.8],'scale':7.7})['views'];view=[v for v in views if v['label']=='three_quarter']
initial=run('preview.multiview',{'objects':names,'views':view,'directory':'a03/original','width':960,'height':540,'style':'parts'})
recipe=run('recipe.inspect',{'object':'A03_Base'});sections=recipe['recipe']['args']['sections'];changed=[[[x*1.24,y*1.12,z*1.22] for x,y,z in ring] for ring in sections]
variant=run('recipe.replay',{'object':'A03_Base','name':'A03_BaseWide','parameters':{'sections':changed},'collection':'A03_ParametricPylon'})
run('modifier.add',{'object':'A03_BaseWide','name':'Edge','kind':'BEVEL','properties':{'width':.035,'segments':2}})
run('material.assign',{'object':'A03_BaseWide','material':'A03_Steel'})
final_names=['A03_BaseWide' if n=='A03_Base' else n for n in names]
final=run('preview.multiview',{'objects':final_names,'views':view,'directory':'a03/variant','width':960,'height':540,'style':'parts'})
wire=run('preview.multiview',{'objects':final_names,'views':view,'directory':'a03/wire','width':960,'height':540,'style':'wireframe'})
checkpoint=run('checkpoint.create',{'label':'A03_parameter_variant','objects':final_names+[v['camera'] for v in views]})
atomic_json(OUT/'a03/evidence.json',{'session':h['session'],'revision':revision,'objects':final_names,'views':views,'initial':initial,'final':final,'wire':wire,'recipe':recipe,'changed_parameters':{'sections':changed},'variant':variant,'checkpoint':checkpoint,'operations':records,'user_visual_acceptance':'not_requested_engineering_fixture','ue_validation':'not_run'})
print(json.dumps({'objects':final_names,'images':[a['path'] for a in final['images']],'source':checkpoint['source']['path']}))
