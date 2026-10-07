"""Game asset preparation and owned worker baking for the reviewed engineering pylon."""
import argparse,json,uuid
from pathlib import Path
from blender_bridge.client import connect
from blender_bridge.host.gateway import Gateway
from blender_bridge.core import atomic_json
OUT=Path('C:/dev/BlenderBridge/artifacts/native-modeling');STATE=OUT/'a04/progress.json'

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','bake','inspect','finish']);a=p.parse_args();g=Gateway();c=connect();h=c.call('health');s=json.loads(STATE.read_text()) if STATE.exists() else {};s.update(session=h['session'],revision=h['revision'])
    def native(op,args):
        j=c.wait(c.submit(op,args,s['revision'],str(uuid.uuid4()))['id'],60)
        if j['state']!='succeeded':raise RuntimeError(json.dumps(j))
        s['revision']=j['revision'];return j['result']
    def host(op,args,wait=60):
        return g.execute(op,args,str(uuid.uuid4()),s['session'],s['revision'],wait)
    if a.stage=='prepare':
        prior=json.loads((OUT/'a03/evidence.json').read_text());native('collection.create',{'name':'A04_GamePylon'});names=[]
        for old in prior['objects']:
            if old=='A03_Body':continue
            name=old.replace('A03_','A04_');native('object.duplicate',{'object':old,'name':name,'collection':'A04_GamePylon'});native('object.transform',{'object':name,'apply_scale':True});names.append(name)
        native('object.duplicate',{'object':'A03_Body','name':'A04_HighBody','collection':'A04_GamePylon'})
        for modifier in ['Edge','ServiceRecess']:native('modifier.apply',{'object':'A04_HighBody','name':modifier})
        native('material.copy',{'material':'A03_Steel','name':'A04_HighMaterial'});native('material.assign',{'object':'A04_HighBody','material':'A04_HighMaterial'})
        native('material.update',{'material':'A04_HighMaterial','noise_scale':18,'bump_strength':.035})
        native('retopo.prepare',{'source':'A04_HighBody','name':'A04_Body','collection':'A04_GamePylon'})
        native('retopo.remesh',{'object':'A04_Body','method':'decimate','ratio':.78,'allow_data_loss':True});names.append('A04_Body')
        native('material.create',{'name':'A04_BodyMaterial','color':[.065,.12,.18,1],'metallic':.65,'roughness':.32});native('material.assign',{'object':'A04_Body','material':'A04_BodyMaterial'})
        for name in names:native('uv.unwrap',{'object':name,'margin':.035})
        native('object.duplicate',{'object':'A04_Body','name':'A04_Cage','collection':'A04_GamePylon'})
        info=native('mesh.inspect',{'object':'A04_Cage','limit':1})
        native('mesh.region_transform',{'object':'A04_Cage','indices':list(range(info['vertices'])),'center':[0,0,1.6],'scale':[1.15,1.35,1.12]})
        plan=native('bake.prepare',{'low':'A04_Body','high':['A04_HighBody'],'cage':'A04_Cage','channels':['Normal','AO','BaseColor','Roughness','Metallic'],'resolution':512,'margin':8,'ray_distance':.3,'directory':'textures'})
        checkpoint=native('checkpoint.create',{'label':'A04_frozen_high_low_cage','objects':['A04_HighBody','A04_Body','A04_Cage']})
        s.update(objects=names,views=prior['views'],bake_plan=plan,bake_checkpoint=checkpoint)
        print(json.dumps({'phase':'prepared','source':checkpoint['source']['path'],'plan':plan['plan_id']}))
    elif a.stage=='bake':
        job=host('worker.submit',{'blend':s['bake_checkpoint']['source']['path'],'expected_sha256':s['bake_checkpoint']['source']['sha256'],'operation':'bake.execute','args':{'plan_id':s['bake_plan']['plan_id']},'bake_plan':s['bake_plan']['manifest']['path'],'directory':'a04/worker-bake-'+uuid.uuid4().hex[:8]},0)
        s['bake_job']=job['id'];print(json.dumps(job))
    elif a.stage=='inspect':
        job=g.job(s['bake_job']);s['bake_result']=job
        print(json.dumps({'id':job['id'],'state':job['state'],'error':job.get('error'),'images':[v['path'] for v in job.get('result',{}).get('result',{}).get('artifacts',[])]}))
    elif a.stage=='finish':
        job=g.job(s['bake_job']);assert job['state']=='succeeded',job;s['bake_result']=job
        bake=job['result']['result'];assert bake['state']=='completed'
        for image in bake['artifacts']:
            native('material.relink',{'material':'A04_BodyMaterial','channel':image['provenance']['channel'],'path':image['path']})
        rig='A04_Rig';native('rig.create',{'name':rig,'bones':[{'name':'Root','head':[0,0,0],'tail':[0,0,1]},{'name':'Swivel','head':[0,0,2.85],'tail':[0,0,3.7],'parent':'Root'},{'name':'Actuator','head':[-.7,0,1.9],'tail':[-1.4,0,1.9],'parent':'Root'}]})
        native('rig.bind_rigid',{'armature':rig,'bindings':[{'object':n,'bone':'Swivel' if n in ('A04_Cap','A04_Antenna','A04_Joint') else 'Actuator' if n=='A04_LeftArm' else 'Root'} for n in s['objects']]})
        camera=next(v['camera'] for v in s['views'] if v['label']=='three_quarter')
        poses=native('animation.pose_test',{'armature':rig,'objects':s['objects'],'poses':[{'label':'rest','bones':{}},{'label':'sweep','bones':{'Swivel':{'rotation':[0,.65,0]},'Actuator':{'rotation':[0,0,.40]}}},{'label':'return_rest','bones':{}}],'camera':camera,'directory':'a04/poses','width':960,'height':540})
        assert poses['restored'];assert max(m['max_edge_length_change'] for p in poses['poses'] for m in p['measurements'])<1e-4
        native('light.create',{'name':'A04_Key','location':[3,-4,6],'target':[0,0,1.8],'energy':1600,'size':4})
        native('light.create',{'name':'A04_Fill','location':[-3,-1,4],'target':[0,0,1.8],'energy':900,'size':3})
        native('light.create',{'name':'A04_Rim','location':[1,4,5],'target':[0,0,1.8],'energy':2000,'size':3})
        material=native('preview.render',{'camera':camera,'objects':s['objects'],'path':'a04/material.png','width':960,'height':540,'style':'material'})
        wire=native('preview.multiview',{'objects':s['objects'],'views':[{'label':'final','camera':camera}],'directory':'a04/wire','width':960,'height':540,'style':'wireframe'})
        for frame,rotation in [(1,0),(13,.65),(25,0)]:native('animation.keyframe',{'object':rig,'bone':'Swivel','frame':frame,'rotation':[0,rotation,0]})
        native('animation.frame',{'frame':1})
        validation=native('game.validate',{'objects':s['objects']+[rig],'profile':{'max_triangles':20000,'require_uv':True,'max_influences':1}})
        package=native('export.package',{'objects':s['objects']+[rig],'directory':'a04/export','formats':['fbx','glb','obj'],'animation':True,'frame_start':1,'frame_end':25,'profile':{'max_triangles':20000,'require_uv':True,'max_influences':1}})
        s.update(poses=poses,material=material,wireframe=wire,validation=validation,package=package)
        atomic_json(STATE,s)
        verify=host('delivery.verify',{'manifest':package['manifest']['path']},0);s['verify_job']=verify['id']
        print(json.dumps({'validation':validation['state'],'issues':validation['issues'],'manifest':package['manifest']['path'],'verify_job':verify['id']}))
    atomic_json(STATE,s)

if __name__=='__main__':main()
