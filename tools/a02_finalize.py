import json,uuid
from pathlib import Path
from blender_bridge.client import connect
from blender_bridge.host.gateway import Gateway
from blender_bridge.core import atomic_json
OUT=Path('C:/dev/BlenderBridge/artifacts/native-modeling');g=Gateway();c=connect();h=c.call('health');revision=h['revision'];s=json.loads((OUT/'a02/refinement.json').read_text())
def host(op,args):
    j=g.execute(op,args,str(uuid.uuid4()),h['session'],revision,60)
    if j['state']!='succeeded':raise RuntimeError(json.dumps(j))
    return j['result']
def native(op,args):
    global revision
    j=c.wait(c.submit(op,args,revision,str(uuid.uuid4()))['id'],60)
    if j['state']!='succeeded':raise RuntimeError(json.dumps(j))
    revision=j['revision'];return j['result']
m=host('modeling.inspect',{'modeling_id':'a02-r3-refinement'})
issues=[{'issue_id':'a02-r3-neck','observation':'Six-view recheck: head is now recessed between the shoulder crown and chest, without elongated visible neck. Local proportion goal resolved.','status':'resolved'},
        {'issue_id':'a02-r3-shell','observation':'Shoulder crown visibly broader/flatter with lower curvature. Original R3 dome design remains distinguishable from the approved faceted concept; this is a local improvement demonstration, not production fidelity acceptance.','status':'resolved'},
        {'issue_id':'a02-r3-chest','observation':'Pectoral width and side depth visibly increased. Fasteners/seams follow the deformation; abdomen/reactor/arm mechanism hashes unchanged. Fine surface wear and exact panel contour remain outside local self-review.','status':'resolved'}]
r=host('review.record',{'modeling_id':m['modeling_id'],'review_id':'a02-r4-local-review','candidate_revision':2,'artifact_ids':[v['id'] for v in m['images']],'issues':issues,'summary':'Actual six-image review confirms bounded local proportion/thickness improvement over the matching R3 baseline. Self-review scope is this tool acceptance demonstration. Full approved-concept art matching remains pending user review, with rounded shoulder contour, sparse surface breakup and inferred back geometry explicitly retained as limitations.','decision':'self_review_passed','reviewer':'codex'})
m=host('modeling.resume',{'modeling_id':m['modeling_id'],'review_id':r['review_id']})
checkpoint=native('checkpoint.create',{'label':'A02_R4_local_refinement_final','objects':s['objects']})
views=[v for v in s['views'] if v['label'] in ('concept_view','front','left')]
images=native('preview.multiview',{'objects':s['objects'],'views':views,'directory':'a02/final','width':1920,'height':1080,'style':'clay'})
wire=native('preview.multiview',{'objects':[n for n in s['objects'] if n!='R4_PreviewFloor'],'views':[s['views'][-1]],'directory':'a02/final-wire','width':1920,'height':1080,'style':'wireframe'})
g.artifacts(h['session']);old=[v for v in json.loads((OUT/'a02/local-fix-input.json').read_text())['review']['artifact_ids']]
baseline=[g.store.get_artifact(a) for a in old];b=next(v for v in baseline if v['path'].endswith('concept_view_clay.png'));f=next(v for v in images['images'] if v['path'].endswith('concept_view_clay.png'))
comparison=host('compare.views',{'reference_artifacts':[b['id']],'candidate_artifacts':[f['id']],'path':'a02/final/R3-R4-same-camera.png'})
atomic_json(OUT/'a02/final-evidence.json',{'model':m,'checkpoint':checkpoint,'images':images,'wireframe':wire,'comparison':comparison,'limitations':['Local proportion improvement only, not full production art fidelity.','Shoulder surfaces remain rounded relative to approved faceted reference.','Back view and absolute metric scale are inferred.','No UE import or acceptance.']})
print(json.dumps({'phase':m['phase'],'checkpoint':checkpoint,'comparison':comparison},ensure_ascii=False))
