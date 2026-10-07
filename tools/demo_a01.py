"""A01 authored fixture stages. Uses only the public typed protocol, no bpy/code fallback."""
import argparse
import json
from pathlib import Path
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from blender_bridge.client import connect
from blender_bridge.host.gateway import Gateway
from blender_bridge.core import atomic_json

OUTPUT=ROOT/'artifacts'/'native-modeling'
STATE=OUTPUT/'a01'/'progress.json'


def octagon(width,depth,z,corner=.18):
    x=width/2;y=depth/2;c=min(corner,x/2,y/2)
    return [[-x+c,-y,z],[x-c,-y,z],[x,-y+c,z],[x,y-c,z],[x-c,y,z],[-x+c,y,z],[-x,y-c,z],[-x,-y+c,z]]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['reference','refit','register','plan','submit','inspect']);parser.add_argument('--session');args=parser.parse_args()
    state=json.loads(STATE.read_text(encoding='utf-8')) if STATE.is_file() else {}
    client=connect(args.session or state.get('session'));health=client.call('health');state.update(session=health['session'],revision=health['revision'])
    gateway=Gateway()
    def native(name,values):
        job=client.submit(name,values,state['revision'],str(uuid.uuid4()));job=client.wait(job['id'],60)
        if job['state']!='succeeded':raise RuntimeError(json.dumps(job,ensure_ascii=False))
        state['revision']=job['revision'];return job['result']
    def host(name,values):
        job=gateway.execute(name,values,str(uuid.uuid4()),state['session'],state['revision'],60)
        if job['state']!='succeeded':raise RuntimeError(json.dumps(job,ensure_ascii=False))
        return job['result']
    if args.stage=='reference':
        steps=[{'operation':'collection.create','args':{'name':'A01_Reference'}}]
        pieces=[('Base',[octagon(2.5,1.6,0),octagon(2.5,1.6,.28),octagon(2.2,1.4,.42)]),('Body',[octagon(1.45,.95,.4),octagon(1.45,.95,2.5),octagon(.95,.7,2.85)]),('Cap',[octagon(1.2,.95,2.8),octagon(1.2,.95,3.05)])]
        for name,sections in pieces:
            steps.append({'operation':'geometry.loft','args':{'name':'A01Ref_'+name,'sections':sections,'collection':'A01_Reference'}})
            steps.append({'operation':'modifier.add','args':{'object':'A01Ref_'+name,'name':'Edge','kind':'BEVEL','properties':{'width':.035,'segments':2}}})
        pieces_extra=[('LeftArm',[[-.7,-.4,1.6],[-1.2,-.4,1.6],[-1.45,-.4,1.9],[-1.45,-.4,2.35],[-1.12,-.4,2.35],[-1.0,-.4,1.98],[-.7,-.4,1.9]]),('RightPanel',[[.65,-.4,.75],[1.15,-.4,.9],[1.15,-.4,1.6],[.65,-.4,1.6]])]
        for name,points in pieces_extra:steps.append({'operation':'geometry.profile','args':{'name':'A01Ref_'+name,'points':points,'depth':.65,'direction':[0,1,0],'collection':'A01_Reference'}})
        steps += [{'operation':'mesh.primitive','args':{'name':'A01Ref_Antenna','kind':'cylinder','location':[.27,.1,3.32],'scale':[.07,.07,.35],'segments':16,'collection':'A01_Reference'}},
                  {'operation':'mesh.primitive','args':{'name':'A01Ref_Reactor','kind':'cube','location':[0,-.49,1.55],'scale':[.12,.055,.85],'collection':'A01_Reference'}},
                  {'operation':'material.create','args':{'name':'A01RefSteel','color':[.12,.23,.34,1],'metallic':.7,'roughness':.35}},
                  {'operation':'material.create','args':{'name':'A01RefAmber','color':[1,.4,.04,1],'metallic':.3,'roughness':.35}}]
        names=['A01Ref_'+n for n in ['Base','Body','Cap','LeftArm','RightPanel','Antenna','Reactor']]
        for name in names:steps.append({'operation':'material.assign','args':{'object':name,'material':'A01RefAmber' if name.endswith(('Reactor','LeftArm')) else 'A01RefSteel'}})
        native('batch.execute',{'steps':steps});cameras=native('preview.camera_set',{'name':'A01Review','center':[0,0,1.75],'scale':5.2})['views']
        result=native('preview.multiview',{'objects':names,'views':cameras,'directory':'a01/reference-images','width':960,'height':540,'style':'parts'})
        state.update(reference_images=result['images'],views=cameras,reference_objects=names)
        native('object.visibility',{'objects':names,'render':False})
        print(json.dumps({'images':[{k:a[k] for k in ('id','path','label')} for a in result['images']]},ensure_ascii=False))
    elif args.stage=='refit':
        cameras=native('preview.camera_set',{'name':'A01FullReview','center':[0,0,1.8],'scale':8.0})['views']
        result=native('preview.multiview',{'objects':state['reference_objects'],'views':cameras,'directory':'a01/reference-full','width':960,'height':540,'style':'parts'})
        state.update(reference_images=result['images'],views=cameras,reference_id='a01-asymmetric-pylon-full')
        print(json.dumps({'images':[a['path'] for a in result['images']]}))
    elif args.stage=='register':
        result=host('reference.register',{'reference_id':state.get('reference_id','a01-asymmetric-pylon'),'views':[{'label':a['label'],'path':a['path'],'pose_id':'rest','camera':a['provenance']['camera_state']} for a in state['reference_images']],
                                           'approval_status':'fixture_only','pose_id':'rest','height_m':3.67,'unknown_regions':[],'asset_type':'asymmetric_hard_surface_calibration'})
        state['reference']=host('reference.freeze',{'reference_id':result['reference_id']})
        print(json.dumps({'reference_id':state['reference']['reference_id'],'revision':state['reference']['revision'],'hash':state['reference']['frozen_sha256'],'images':[v['artifact'] for v in state['reference']['views']]},ensure_ascii=False))
    elif args.stage=='plan':
        # Candidate geometry is independently authored from viewed images. No source duplicate/mesh reads.
        steps=[{'operation':'collection.create','args':{'name':'A01_Candidate'}}]
        for name,sections in [('Base',[octagon(2.5,1.6,0),octagon(2.5,1.6,.28),octagon(2.2,1.4,.42)]),('Body',[octagon(1.45,.95,.4),octagon(1.45,.95,2.5),octagon(.95,.7,2.85)]),('Cap',[octagon(1.2,.95,2.8),octagon(1.2,.95,3.05)])]:
            steps += [{'operation':'geometry.loft','args':{'name':'A01_'+name,'sections':sections,'collection':'A01_Candidate'}},{'operation':'modifier.add','args':{'object':'A01_'+name,'name':'Edge','kind':'BEVEL','properties':{'width':.035,'segments':2}}}]
        # Declared controlled fault: upper left outrigger is 0.30 m too tall, localized fix required.
        steps += [{'operation':'geometry.profile','args':{'name':'A01_LeftArm','points':[[-.7,-.4,1.6],[-1.2,-.4,1.6],[-1.45,-.4,1.9],[-1.45,-.4,2.65],[-1.12,-.4,2.65],[-1.0,-.4,1.98],[-.7,-.4,1.9]],'depth':.65,'direction':[0,1,0],'collection':'A01_Candidate'}},
                  {'operation':'geometry.profile','args':{'name':'A01_RightPanel','points':[[.65,-.4,.75],[1.15,-.4,.9],[1.15,-.4,1.6],[.65,-.4,1.6]],'depth':.65,'direction':[0,1,0],'collection':'A01_Candidate'}},
                  {'operation':'mesh.primitive','args':{'name':'A01_Antenna','kind':'cylinder','location':[.27,.1,3.32],'scale':[.07,.07,.35],'segments':16,'collection':'A01_Candidate'}},
                  {'operation':'mesh.primitive','args':{'name':'A01_Reactor','kind':'cube','location':[0,-.49,1.55],'scale':[.12,.055,.85],'collection':'A01_Candidate'}},
                  {'operation':'part.register','args':{'part_id':'a01-base-protected','objects':['A01_Base'],'role':'base must retain proportions'}},
                  {'operation':'part.lock','args':{'part_id':'a01-base-protected'}},
                  {'operation':'part.register','args':{'part_id':'a01-left-arm','objects':['A01_LeftArm'],'role':'asymmetric outrigger'}}]
        names=['A01_'+n for n in ['Base','Body','Cap','LeftArm','RightPanel','Antenna','Reactor']];ref=state['reference']
        state['model']=host('modeling.plan',{'modeling_id':'a01-native-loop','asset_id':'a01-pylon','reference_id':ref['reference_id'],'reference_revision':ref['revision'],'reference_sha256':ref['frozen_sha256'],
                                         'objects':names,'steps':steps,'views':state['views'],'directory':'a01/candidate','width':960,'height':540,
                                         'assumptions':['Synthetic fixture only; original geometry not duplicated into candidate.','Controlled injected error: left outrigger top +0.30m; must inspect images and fix locally.']})
        print(json.dumps({'phase':state['model']['phase'],'modeling_id':state['model']['modeling_id'],'revision':state['model']['revision']}))
    elif args.stage=='submit':
        state['model']=host('modeling.submit',{'modeling_id':state['model']['modeling_id']});state['revision']=state['model']['revision']
        print(json.dumps({'phase':state['model']['phase'],'images':state['model']['images']},ensure_ascii=False))
    else:
        state['model']=host('modeling.inspect',{'modeling_id':'a01-native-loop'});print(json.dumps(state['model'],ensure_ascii=False))
    atomic_json(STATE,state)


if __name__=='__main__':main()
