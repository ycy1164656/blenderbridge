"""Independently reopen the three final scoped modeling sources without saving."""
import json,sys,hashlib
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/native-modeling';results=[]
for label,file in [('A01','a01/evidence.json'),('A02','a02/final-evidence.json'),('A03','a03/evidence.json')]:
    evidence=json.loads((OUT/file).read_text());checkpoint=evidence['checkpoint'];source=checkpoint['source']
    assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()==source['sha256']
    bpy.ops.wm.open_mainfile(filepath=source['path'],load_ui=False)
    names={v['name'] for v in checkpoint['objects']};actual={v.name for v in bpy.context.scene.objects};assert names==actual,(label,len(names),len(actual))
    assert all(bpy.data.objects[n].get('bb_object_id')==v['object_id'] for v in checkpoint['objects'] for n in [v['name']])
    assert all(len(v.data.vertices)>0 for v in bpy.context.scene.objects if v.type=='MESH')
    results.append({'asset':label,'state':'passed','source':source['path'],'objects':len(names),'meshes':sum(v.type=='MESH' for v in bpy.context.scene.objects),'stable_ids_preserved':True,'source_sha256':source['sha256']})
(OUT/'saved-source-readback.json').write_text(json.dumps(results,indent=2));print('SAVED_SOURCES_PASS '+json.dumps(results),flush=True)
