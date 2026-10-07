import argparse,json,uuid
from pathlib import Path
from blender_bridge.client import connect
from blender_bridge.host.gateway import Gateway
from blender_bridge.core import atomic_json

OUT=Path('C:/dev/BlenderBridge/artifacts/native-modeling');STATE=OUT/'a02/refinement.json'
SOURCE='C:/dev/ShooterRoyal_5_8_DirectUpgrade/SourceArt/AtlasV3_20261004/Revision02/UpperBodyStudy/COLOSSUS_R3_UpperBody.blend'

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['reject','append','plan','submit','inspect']);a=p.parse_args();g=Gateway();c=connect();h=c.call('health');s=json.loads(STATE.read_text()) if STATE.exists() else {};s.update(session=h['session'],revision=h['revision'])
    def native(op,args):
        j=c.wait(c.submit(op,args,s['revision'],str(uuid.uuid4()))['id'],60)
        if j['state']!='succeeded':raise RuntimeError(json.dumps(j))
        s['revision']=j['revision'];return j['result']
    def host(op,args):
        j=g.execute(op,args,str(uuid.uuid4()),s['session'],s['revision'],60)
        if j['state']!='succeeded':raise RuntimeError(json.dumps(j))
        return j['result']
    if a.stage=='reject':
        m=host('modeling.inspect',{'modeling_id':'a02-colossus-native'})
        r=host('review.record',{'modeling_id':m['modeling_id'],'review_id':'a02-native-r1-needs-work','candidate_revision':1,'artifact_ids':[v['id'] for v in m['images']],'issues':[{'issue_id':'a02-shoulder-folds','observation':'Shoulder shells read as roof-like folded strips, lacking broad rounded transitions and mechanical density of the approved reference.','status':'open'},{'issue_id':'a02-neck-height','observation':'Helmet sits too high above chest, leaves visible slender neck.','status':'open'},{'issue_id':'a02-detail-loss','observation':'Independent 78-part reconstruction has less useful surface/connection detail than R3. Preserve failure and refine a separate copy of R3.','status':'open'}],'summary':'Actual six-view clay review failed this candidate. No visual pass; switch to independently appended R3 geometry for a bounded shape refinement, preserving this candidate and historical files.','decision':'needs_work','reviewer':'codex'})
        print(json.dumps({'review':r['review_id'],'decision':r['decision']}))
    elif a.stage=='append':
        old=json.loads((OUT/'a02/old-inspect-job.json').read_text())['result']['result'];names=[o['name'] for o in old['objects'] if o['type']=='MESH'];native('collection.create',{'name':'A02_R4_Refinement'})
        r=native('asset.append',{'path':SOURCE,'collection':'A02_R4_Refinement','objects':names,'prefix':'R4_'})
        s['objects']=[o['name'] for o in r['objects'] if o['type']=='MESH'];s['original_inspect']=r
        atomic_json(STATE,s)
        print(json.dumps({'count':len(s['objects']),'samples':[o for o in r['objects'] if any(k in o['name'] for k in ['Broad folded chest','Shoulder crown plate','Cranial','Helmet','Faceplate','Thoracic'])]},ensure_ascii=False))
    elif a.stage=='inspect':
        print(json.dumps(s,ensure_ascii=False))
    elif a.stage=='plan':
        # All original positions are retained; camera parameters come from actual bounds.
        names=s['objects'];r=json.loads((OUT/'a02/progress.json').read_text())['reference']
        views=native('preview.camera_set',{'name':'A02R4Fixed','center':[0,0,2.43],'scale':2.9})['views']
        native('camera.create',{'name':'A02R4Concept','location':[4,-9,4.7],'target':[0,0,2.43],'orthographic_scale':2.9})
        s['views']=views+[{'label':'concept_view','camera':'A02R4Concept'}]
        s['model']=host('modeling.plan',{'modeling_id':'a02-r3-refinement','asset_id':'a02-r4-bust','reference_id':r['reference_id'],'reference_revision':r['revision'],'reference_sha256':r['frozen_sha256'],'objects':names,'steps':[{'operation':'scene.identify','args':{'objects':names}}],'views':s['views'],'directory':'a02/r4-refinement','assumptions':['An independent append of R3 is the baseline. Original blend and screenshots are unchanged.','Only approved three-quarter image is authoritative; exact metric scale and back design remain inferred.','First image set is the unchanged R3 baseline, followed by local measured edits.']})
        print(json.dumps({'phase':s['model']['phase'],'objects':len(names)}))
    elif a.stage=='submit':
        s['model']=host('modeling.submit',{'modeling_id':'a02-r3-refinement'});s['revision']=s['model']['revision'];print(json.dumps({'phase':s['model']['phase'],'images':[x['path'] for x in s['model']['images']]}))
    atomic_json(STATE,s)

if __name__=='__main__':main()
