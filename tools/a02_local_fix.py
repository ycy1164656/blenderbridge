import json,uuid
from pathlib import Path
from blender_bridge.client import connect
from blender_bridge.host.gateway import Gateway
from blender_bridge.core import atomic_json

OUT=Path('C:/dev/BlenderBridge/artifacts/native-modeling');s=json.loads((OUT/'a02/refinement.json').read_text());g=Gateway();c=connect(s['session']);h=c.call('health');revision=h['revision']
def native(op,args):
    global revision
    j=c.wait(c.submit(op,args,revision,str(uuid.uuid4()))['id'],60)
    if j['state']!='succeeded':raise RuntimeError(json.dumps(j))
    revision=j['revision'];return j['result']
def host(op,args):
    j=g.execute(op,args,str(uuid.uuid4()),s['session'],revision,60)
    if j['state']!='succeeded':raise RuntimeError(json.dumps(j))
    return j['result']

model=host('modeling.inspect',{'modeling_id':'a02-r3-refinement'})
checkpoint=native('checkpoint.create',{'label':'A02_R3_before_local_refinement','objects':s['objects']})
before=native('scene.fingerprint',{'objects':s['objects']})
head_prefixes=['Helmet','Mask','Chin','Crown','Ear cover','Solid center','Continuous amber','Visor']
shoulder_prefixes=['Shoulder crown','Shoulder frontal','Shoulder descending','Shoulder skirt','Shoulder ochre','Shoulder countersunk']
chest_prefixes=['Broad folded','Chest ','Pectoral perimeter']
steps=[];modified=[]
for ob in s['original_inspect']['objects']:
    name=ob['name'];base=name.removeprefix('R4_')
    category='head' if any(base.startswith(p) for p in head_prefixes) else 'shoulder' if any(base.startswith(p) for p in shoulder_prefixes) else 'chest' if any(base.startswith(p) for p in chest_prefixes) else None
    if not category:continue
    indices=list(range(ob['vertices']));modified.append(name)
    if category=='head':args={'center':[0,0,2.83],'scale':[.94,.97,.94],'delta':[0,0,-.105]}
    elif category=='shoulder':args={'center':[0,0,2.4],'scale':[1.035,1.04,.83],'delta':[0,0,.14]}
    else:
        sign=-1 if sum(v[0] for v in ob['bounds_world'])<0 else 1
        args={'center':[sign*.275,-.19,2.42],'scale':[1.14,1.30,1.08],'delta':[sign*.012,-.018,0]}
    steps.append({'operation':'mesh.region_transform','args':{'object':name,'indices':indices,'space':'world',**args}})
protected=[n for n in s['objects'] if n not in modified]
steps[0:0]=[{'operation':'part.register','args':{'part_id':'a02-preserved-mechanism','objects':protected,'role':'Existing arm mechanisms, sternum, reactor, back and floor preserved during local shell edits'}},{'operation':'part.lock','args':{'part_id':'a02-preserved-mechanism'}}]
review=host('review.record',{'modeling_id':model['modeling_id'],'review_id':'a02-r3-baseline-review','candidate_revision':1,'artifact_ids':[a['id'] for a in model['images']],
    'issues':[{'issue_id':'a02-r3-neck','category':'proportion','observation':'Baseline helmet and narrow visible neck sit noticeably above the heavy shoulders; approved concept recesses the head.','proposed_action':'Lower complete head by 0.105m, reduce head width/height 6%, preserve torso mechanism.','status':'open'},
              {'issue_id':'a02-r3-shell','category':'silhouette','observation':'Shoulder shells are very round domes. Flatten vertical shell curvature 17% and lift by 0.14m to form a broader sloping crown.','status':'open'},
              {'issue_id':'a02-r3-chest','category':'volume','observation':'Pectoral faces read as small inset badges. Increase their side width14%, forward thickness30% and height8% with attached seams/fasteners following.','status':'open'}],
    'summary':'Read all six actual baseline renders and approved crop. Planned affine region edits preserve every non-target mechanism. Side/back remain inferred. Surface wear and full production matching are outside this local geometry self-review.','decision':'needs_work','reviewer':'codex'})
atomic_json(OUT/'a02/local-fix-input.json',{'checkpoint':checkpoint,'before':before,'modified':modified,'protected':protected,'steps':steps,'review':review})
model=host('modeling.resume',{'modeling_id':model['modeling_id'],'review_id':review['review_id'],'steps':steps});revision=model['revision']
after=native('scene.fingerprint',{'objects':s['objects']})
prior={v['name']:v['sha256'] for v in before['objects'].values()};now={v['name']:v['sha256'] for v in after['objects'].values()}
changed=[n for n in prior if prior[n]!=now[n]];assert not set(changed)&set(protected)
atomic_json(OUT/'a02/local-fix-result.json',{'model':model,'before':before,'after':after,'changed':changed,'modified':modified,'protected':protected,'protected_unchanged':True})
print(json.dumps({'phase':model['phase'],'changed':len(changed),'protected_unchanged':len(protected),'images':[a['path'] for a in model['images']]}))
