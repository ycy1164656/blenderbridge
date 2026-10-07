"""Finish A01 evidence through the public protocol after actual image review."""
import json
from pathlib import Path
import uuid
from blender_bridge.client import connect
from blender_bridge.host.storage import Store
from blender_bridge.host.gateway import Gateway
from blender_bridge.core import atomic_json

store=Store();model=store.get('modeling','a01-native-loop');c=connect(model['session']);revision=c.call('health')['revision'];record={}
def native(name,args):
    global revision
    job=c.submit(name,args,revision,str(uuid.uuid4()));job=c.wait(job['id'],60)
    if job['state']!='succeeded':raise RuntimeError(json.dumps(job))
    revision=job['revision'];return job['result']

progress=json.loads((store.root/'a01'/'progress.json').read_text(encoding='utf-8'))
for tag,names in [('reference',progress['reference_objects']),('final',model['objects'])]:
    record[tag]=native('preview.multiview',{'objects':names,'views':model['views'],'directory':'a01/evidence/'+tag,'style':'clay','width':1920,'height':1080})
record['wireframe']=native('preview.multiview',{'objects':model['objects'],'views':[model['views'][0],model['views'][4]],'directory':'a01/evidence/wireframe','style':'wireframe','width':1920,'height':1080})
native('camera.create',{'name':'A01_Holdout_LeftFront','location':[-6,-8,5.5],'target':[0,0,1.8],'orthographic_scale':8})
record['holdout']=native('preview.render',{'objects':model['objects'],'camera':'A01_Holdout_LeftFront','path':'a01/evidence/holdout_left_front.png','width':1920,'height':1080,'style':'clay'})
record['checkpoint']=native('checkpoint.create',{'label':'A01 reviewed corrected editable candidate','objects':model['objects']+[v['camera'] for v in model['views']]+['A01_Holdout_LeftFront']})
gateway=Gateway();gateway.artifacts(model['session']);result=gateway.execute('compare.views',{'reference_artifacts':[a['id'] for a in record['reference']['images']],'candidate_artifacts':[a['id'] for a in record['final']['images']],'path':'a01/evidence/reference-final-comparison.png'},str(uuid.uuid4()),wait_seconds=30)
record['comparison']=result;atomic_json(store.root/'a01'/'evidence.json',record)
print(json.dumps({'source':record['checkpoint']['source']['path'],'comparison':result.get('result',{}).get('image',{}).get('path'),'holdout':record['holdout']['path'],'wireframe':[a['path'] for a in record['wireframe']['images']]}))
