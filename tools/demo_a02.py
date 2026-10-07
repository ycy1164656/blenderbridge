"""Approved upper-body study; new native meshes, no changes to historical source art."""
import argparse
import json
import math
from pathlib import Path
import uuid
from blender_bridge.client import connect
from blender_bridge.host.gateway import Gateway
from blender_bridge.core import atomic_json

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/native-modeling';STATE=OUT/'a02/progress.json'
REF='C:/dev/ShooterRoyal_5_8_DirectUpgrade/SourceArt/AtlasV3_20261004/Revision02/COLOSSUS_R2B_HeadProportions.png'

def design():
    steps=[{'operation':'collection.create','args':{'name':'A02_NativeBust'}}];names=[]
    def op(n,**a):steps.append({'operation':n,'args':a})
    for name,color,metal,rough in [('Armor',[.085,.125,.16,1],.82,.38),('Edges',[.2,.23,.25,1],.75,.31),('Joint',[.025,.032,.038,1],.7,.34),('Gold',[.5,.32,.10,1],.68,.4),('Lens',[1,.38,.025,1],.25,.28)]:
        op('material.create',name='A02_'+name,color=color,metallic=metal,roughness=rough)
    def finish(name,mat='Armor',bevel=.018):
        names.append(name);op('material.assign',object=name,material='A02_'+mat)
        if bevel:op('modifier.add',object=name,name='MachinedEdge',kind='BEVEL',properties={'width':bevel,'segments':2})
    def mesh(name,verts,faces,mat='Armor',thickness=0,bevel=.018):
        name='A02_'+name;op('mesh.create',name=name,vertices=verts,faces=faces,collection='A02_NativeBust')
        if thickness:op('modifier.add',object=name,name='ArmorThickness',kind='SOLIDIFY',properties={'thickness':thickness,'offset':-1})
        finish(name,mat,bevel);return name
    def plate(name,outline,y,depth,mat='Armor',bevel=.018):
        name='A02_'+name;op('geometry.profile',name=name,points=[[x,y,z] for x,z in outline],depth=depth,direction=[0,1,0],collection='A02_NativeBust');finish(name,mat,bevel);return name
    def box(name,loc,scale,mat='Joint',rot=None):
        name='A02_'+name;op('mesh.primitive',name=name,kind='cube',location=loc,scale=scale,collection='A02_NativeBust');finish(name,mat)
        if rot:op('object.transform',object=name,rotation=rot)
        return name
    def cylinder(name,start,end,r,mat='Edges',segments=16):
        # Sweep explicit sections along mechanical connection, retained as editable recipe.
        name='A02_'+name;profile=[[r*math.cos(2*math.pi*i/segments),r*math.sin(2*math.pi*i/segments)] for i in range(segments)]
        op('geometry.sweep',name=name,profile=profile,path=[start,end],up=[0,0,1],collection='A02_NativeBust');finish(name,mat,.008);return name
    # Core, narrow waist and structural spine behind the face armor.
    plate('TorsoFrame',[(-1.35,2.9),(-.86,.5),(.86,.5),(1.35,2.9)],-.32,1.02,'Joint',.05)
    box('Spine',[0,.55,1.95],[.2,.22,1.55],'Joint')
    for side in [-1,1]:
        tag='L' if side<0 else 'R'
        # Convex pectoral: nested front ring produces thick turning planes, not flat octagons.
        outline=[(.20,2.94),(.65,3.24),(1.28,3.18),(1.76,2.82),(1.65,2.04),(1.04,1.62),(.34,1.88)]
        center=(.98,2.47);verts=[]
        for factor,y in [(1,-.63),(.83,-1.0),(.32,-1.12),(1,-.35)]:
            verts += [[side*(center[0]+(x-center[0])*factor),y,center[1]+(z-center[1])*factor] for x,z in outline]
        n=len(outline);faces=[]
        for a,b in [(0,1),(1,2),(3,0)]:
            faces += [[a*n+i,a*n+(i+1)%n,b*n+(i+1)%n,b*n+i] for i in range(n)]
        faces += [list(range(2*n,3*n)),list(reversed(range(3*n,4*n)))]
        if side<0:faces=[list(reversed(f)) for f in faces]
        mesh(tag+'Pectoral',verts,faces,bevel=.035)
        # Angular sloped shoulder shells, split into deliberate narrow seam strips.
        cross=[(1.13,3.5),(1.47,3.84),(2.05,3.9),(2.76,3.53),(3.24,3.05),(3.35,2.68)]
        for strip,(start,end) in enumerate([(0,2),(2,3),(3,5)]):
            verts=[]
            for y,drop,spread in [(-.85,.20,-.10),(-.15,0,0),(.64,.16,-.06)]:
                for j in range(start,end+1):
                    x,z=cross[j];x+=spread
                    if j==start and start>0:x+=.025
                    if j==end and end<5:x-=.025
                    verts.append([side*x,y,z-drop])
            w=end-start+1;faces=[[r*w+i,r*w+i+1,(r+1)*w+i+1,(r+1)*w+i] for r in range(2) for i in range(w-1)]
            if side<0:faces=[list(reversed(f)) for f in faces]
            mesh(tag+'ShoulderShell'+str(strip),verts,faces,thickness=.115,bevel=.025)
        skirt=[(1.52,3.36),(2.03,3.43),(2.71,3.10),(3.23,2.58),(3.12,2.37),(2.55,2.81),(1.59,3.07)]
        plate(tag+'ShoulderLayer',[(side*x,z) for x,z in skirt],-.98,.20,bevel=.027)
        # Gold inlay follows sloping shell, uses real surface geometry without glow.
        mesh(tag+'ShoulderStripe',[[side*x,y,z] for x,y,z in [(2.04,-.80,3.72),(2.24,-.77,3.65),(2.29,.55,3.71),(2.07,.55,3.80)]],[[0,1,2,3]],'Gold',.006,.004)
        # Rear upward fins and compact clavicle guards.
        plate(tag+'RearFin',[(side*x,z) for x,z in [(1.03,3.01),(1.14,4.06),(1.47,4.18),(1.7,3.85),(1.73,3.03)]],.38,.24,bevel=.025)
        plate(tag+'Collar',[(side*x,z) for x,z in [(.47,3.12),(.64,3.48),(.93,3.38),(1.25,3.13),(1.13,2.94)]],-.35,.48,'Edges')
        # Visible negative space and nested transverse bearing, pistons to upper-arm anchor.
        cylinder(tag+'Axle',[side*1.05,.02,2.79],[side*2.44,.02,2.79],.30,'Joint',24)
        for k,(x,r) in enumerate([(1.78,.40),(2.12,.34),(2.3,.37)]):
            cylinder(tag+'Bearing'+str(k),[side*(x-.06),.02,2.79],[side*(x+.06),.02,2.79],r,'Edges',24)
        for k,y in enumerate([-.44,.30]):
            cylinder(tag+'PistonSleeve'+str(k),[side*2.21,y,2.72],[side*2.44,y,2.11],.12,'Joint')
            cylinder(tag+'PistonRod'+str(k),[side*2.37,y,2.3],[side*2.62,y,1.73],.075,'Edges')
        plate(tag+'ArmGuard',[(side*x,z) for x,z in [(2.22,2.39),(2.5,2.4),(2.88,1.5),(2.53,1.36),(2.29,1.82)]],-.60,.52,bevel=.03)
        cylinder(tag+'ElbowPivot',[side*2.40,-.12,1.40],[side*2.84,-.12,1.40],.30,'Joint',24)
        cylinder(tag+'ElbowCap',[side*2.81,-.12,1.40],[side*2.91,-.12,1.40],.24,'Edges',24)
        for i,z in enumerate([1.94,1.6,1.27]):
            plate(tag+'Rib'+str(i),[(side*x,zz) for x,zz in [(.75,z+.12),(1.43,z+.29),(1.40,z+.02),(.78,z-.13)]],-.28,.56,'Joint',.025)
        # Fasteners are sparse and sit on actual shell surfaces.
        for i,(x,y,z) in enumerate([(1.52,-.99,3.30),(2.67,-.99,2.99),(3.04,-.99,2.61),(.44,-.85,2.85),(1.47,-.82,2.69),(1.34,-.84,2.03)]):
            cylinder(tag+'Fastener'+str(i),[side*x,y,z],[side*x,y-.025,z],.038,'Edges',8)
    # Chevron abdominal plates overlap with real thickness and seams.
    for i,(z,w) in enumerate([(1.64,.87),(1.19,.73),(.78,.58)]):
        plate('Abdominal'+str(i),[(-w,z+.15),(-w*.78,z-.22),(0,z-.43),(w*.78,z-.22),(w,z+.15),(0,z-.03)],-.57+i*.075,.24,bevel=.025)
    plate('ReactorRecess',[(-.20,2.78),(.20,2.78),(.22,2.08),(0,1.88),(-.22,2.08)],-1.00,.21,'Joint',.02)
    plate('ReactorFrame',[(-.11,2.67),(.11,2.67),(.11,2.14),(0,2.06),(-.11,2.14)],-1.08,.09,'Edges',.016)
    box('ReactorLens',[0,-1.095,2.39],[.045,.022,.215],'Lens')
    # Small recessed head and segmented brow, cheek/chin plates. No long exposed neck.
    cylinder('Neck',[0,.02,2.91],[0,.02,3.20],.28,'Joint')
    outline=[(-.38,3.94),(-.24,4.14),(.24,4.14),(.38,3.94),(.35,3.33),(.19,3.17),(-.19,3.17),(-.35,3.33)]
    plate('HelmetCore',outline,-.29,.64,'Joint',.04)
    plate('Brow',[(-.42,3.83),(-.39,4.00),(-.22,4.19),(.22,4.19),(.39,4.00),(.42,3.83),(0,3.78)],-.47,.43,bevel=.032)
    plate('CrownRidge',[(-.065,3.88),(-.10,4.19),(.10,4.19),(.065,3.88)],-.50,.49,'Edges',.012)
    plate('Visor',[(-.36,3.795),(.36,3.795),(.31,3.725),(-.31,3.725)],-.45,.08,'Lens',.006)
    for side in [-1,1]:
        tag='L' if side<0 else 'R'
        plate(tag+'Cheek',[(side*x,z) for x,z in [(.05,3.68),(.31,3.71),(.34,3.31),(.19,3.18),(.06,3.22)]],-.46,.19,bevel=.018)
        cylinder(tag+'EarBase',[side*.33,.05,3.71],[side*.46,.05,3.71],.26,'Joint',24)
        cylinder(tag+'EarRing',[side*.45,.05,3.71],[side*.51,.05,3.71],.20,'Edges',24)
        cylinder(tag+'EarHub',[side*.5,.05,3.71],[side*.53,.05,3.71],.11,'Joint',16)
    plate('Chin',[(-.19,3.23),(.19,3.23),(.14,3.15),(-.14,3.15)],-.49,.20,'Edges',.012)
    return steps,names

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['reference','plan','submit','inspect']);a=p.parse_args()
    state=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {};gw=Gateway();client=connect(state.get('session'));health=client.call('health');state.update(session=health['session'],revision=health['revision'])
    def native(operation,args):
        job=client.wait(client.submit(operation,args,state['revision'],str(uuid.uuid4()))['id'],60)
        if job['state']!='succeeded':raise RuntimeError(json.dumps(job))
        state['revision']=job['revision'];return job['result']
    def host(operation,args):
        job=gw.execute(operation,args,str(uuid.uuid4()),state['session'],state['revision'],60)
        if job['state']!='succeeded':raise RuntimeError(json.dumps(job))
        return job['result']
    if a.stage=='reference':
        r=host('reference.register',{'reference_id':'a02-approved-colossus','views':[{'label':'three_quarter','path':REF,'pose_id':'rest'}],'approval_status':'approved','approval_evidence':'Upgrade guide section 20.2 and historical approved R2B head-proportion concept; derived study is not user approved.','pose_id':'rest','unknown_regions':['exact orthographic side','back','absolute scale'],'asset_type':'mechanical_upper_body'})
        r=host('reference.crop',{'reference_id':r['reference_id'],'view':'three_quarter','rectangle':[45,0,690,405]})
        r=host('reference.freeze',{'reference_id':r['reference_id']});state['reference']=r
        print(json.dumps({'reference_id':r['reference_id'],'revision':r['revision'],'images':[v['artifact']['path'] for v in r['views']]}))
    elif a.stage=='plan':
        steps,names=design();state['objects']=names
        views=native('preview.camera_set',{'name':'A02Fixed','center':[0,0,2.37],'scale':8.1})['views']
        camera=native('camera.create',{'name':'A02ConceptView','location':[7,-16,7.0],'target':[0,0,2.37],'orthographic_scale':8.1})
        state['views']=views+[{'label':'concept_view','camera':'A02ConceptView'}]
        r=state['reference'];state['model']=host('modeling.plan',{'modeling_id':'a02-colossus-native','asset_id':'a02-colossus-bust','reference_id':r['reference_id'],'reference_revision':r['revision'],'reference_sha256':r['frozen_sha256'],'objects':names,'steps':steps,'views':state['views'],'directory':'a02/candidate','assumptions':['Only the left approved three-quarter reference is authoritative. Side/back and metric scale are engineering inferences.','New upperbody scope only. Historical R2/R3 retained.','Sloped layered shoulder shell, convex paired pectorals, recessed small helmet; no texture used to replace geometry.']})
        print(json.dumps({'objects':len(names),'steps':len(steps),'phase':state['model']['phase']}))
    elif a.stage=='submit':
        state['model']=host('modeling.submit',{'modeling_id':'a02-colossus-native'});state['revision']=state['model']['revision'];print(json.dumps({'phase':state['model']['phase'],'images':[v['path'] for v in state['model']['images']]}))
    else:print(json.dumps(host('modeling.inspect',{'modeling_id':'a02-colossus-native'})))
    atomic_json(STATE,state)

if __name__=='__main__':main()
