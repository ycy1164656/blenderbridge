"""Read-only installation audit, actual catalog parity, final source and evidence index."""
import asyncio,hashlib,json,os,subprocess,sys,tomllib,uuid
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from blender_bridge.client import connect
from blender_bridge.host.gateway import Gateway
from blender_bridge.host.storage import configuration,sha
from blender_bridge.catalog import OPS
from blender_bridge.core import atomic_json
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/native-modeling';g=Gateway();c=connect();h=c.call('health')
def native(op,args):
    current=c.call('health');j=c.wait(c.submit(op,args,current['revision'],str(uuid.uuid4()))['id'],60)
    assert j['state']=='succeeded',j
    return j['result']
async def catalogs():
    async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','blender_bridge.mcp_server'])) as (r,w):
      async with ClientSession(r,w) as client:
        await client.initialize();response=await client.call_tool('blender_catalog',{'session':h['session']})
        assert not response.isError;catalog=json.loads(next(v.text for v in response.content if v.type=='text'))
        cli=json.loads(subprocess.check_output([sys.executable,'-m','blender_bridge.cli','--session',h['session'],'catalog'],text=True,encoding='utf-8'))
        assert cli==g.catalog(h['session'])
        keys=tuple(catalog['operations'][0]);assert catalog=={'operations':[{k:v[k] for k in keys} for v in cli['operations']]}
        async def described(entry):
            response=await client.call_tool('blender_catalog',{'session':h['session'],'describe':entry['name']})
            assert not response.isError
            full=json.loads(next(v.text for v in response.content if v.type=='text'));assert full==entry,entry['name']
        for offset in range(0,len(cli['operations']),12):await asyncio.gather(*(described(v) for v in cli['operations'][offset:offset+12]))
        return {'operations':len(catalog['operations']),'mcp_cli_live_equal':True,'full_schemas_compared':len(cli['operations']),'sha256':hashlib.sha256(json.dumps(cli,sort_keys=True).encode()).hexdigest()}
def main():
    parity=asyncio.run(catalogs());conf=configuration();installed=Path(conf['addon_parent'])/'blender_bridge'
    source={str(p.relative_to(ROOT/'src/blender_bridge')).replace('\\','/'):sha(p) for p in (ROOT/'src/blender_bridge').rglob('*.py')}
    actual={str(p.relative_to(installed)).replace('\\','/'):sha(p) for p in installed.rglob('*.py')};assert source==actual
    baseline=tomllib.loads((ROOT/'.tmp/codex-backups/1791163566887711300-codex-config.toml').read_text(encoding='utf-8'))
    current=tomllib.loads((Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'config.toml').read_text(encoding='utf-8'))
    for record in (baseline,current):
        record.get('mcp_servers',{}).pop('blender_bridge',None)
        for server in record.get('mcp_servers',{}).values():
            if 'command' in server:server.setdefault('args',[])
    config_equal=baseline==current
    other_mcp_equal=baseline.get('mcp_servers',{})==current.get('mcp_servers',{})
    a02=json.loads((OUT/'a02/final-evidence.json').read_text());before=json.loads((OUT/'a02/local-fix-input.json').read_text())['review']['artifact_ids']
    old=next(g.store.get_artifact(v)['path'] for v in before if g.store.get_artifact(v)['path'].endswith('concept_view_clay.png'))
    panels=[('APPROVED CONCEPT - cropped single view',OUT/'references/a02-approved-colossus/r0002/frozen/three_quarter.png'),('R3 - SAME CAMERA BASELINE',Path(old)),('R4 - LOCAL PROPORTION REFINEMENT',OUT/'a02/final/concept_view_clay.png')]
    montage=Image.new('RGB',(1920,540),(35,38,43));font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
    for index,(label,path) in enumerate(panels):
        with Image.open(path) as src:im=src.convert('RGB');im.thumbnail((640,465),Image.Resampling.LANCZOS)
        montage.paste(im,(index*640+(640-im.width)//2,46+(465-im.height)//2));ImageDraw.Draw(montage).text((index*640+12,14),label,font=font,fill='white')
    ImageDraw.Draw(montage).text((12,518),'Concept view is approximate. R3/R4 share exact camera. Art acceptance pending; no UE import.',font=font,fill=(200,200,200))
    montage_path=OUT/'a02/final/approved-R3-R4.png';montage.save(montage_path)
    saved=native('scene.save',{'path':'session/native-upgrade-final.blend','copy':True})
    readback=g.execute('delivery.verify',{'manifest':str(OUT/'native-fixture/1a7106d4dd0d/export/delivery.json')},str(uuid.uuid4()),wait_seconds=60)
    while readback['state'] in ('running','queued'):readback=g.jobs.wait(readback['id'],30)
    assert readback['state']=='succeeded' and readback['result']['state']=='passed',readback
    evidence={'version':'0.2.0','session':h['session'],'pid':h.get('pid'),'installed_parent':str(installed),'installed_python_files':len(actual),'installed_hashes_match':True,'catalog':parity,'other_codex_configuration_semantics_unchanged':config_equal,'other_mcp_configuration_semantics_unchanged':other_mcp_equal,'final_scene':saved,'native_readback':readback,'a02_comparison':str(montage_path),'a02_scope':'bounded local improvement; full art fidelity pending','source_tree_sha256':hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()}
    atomic_json(OUT/'final-verification.json',evidence)
    print(json.dumps({'evidence':str(OUT/'final-verification.json'),'catalog':parity,'installed_files':len(actual),'other_config_equal':config_equal,'readback':readback['result']['state']}))
if __name__=='__main__':main()
