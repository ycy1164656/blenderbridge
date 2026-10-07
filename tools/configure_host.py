"""Preview/apply narrow Host settings with backup and unrelated-key preservation."""
import argparse
import json
from pathlib import Path
import shutil
import time
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from blender_bridge.host.storage import config_path
from blender_bridge.core import atomic_json

p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--output-root',default=str(ROOT/'artifacts'/'native-modeling'));p.add_argument('--read-root',action='append',default=[]);p.add_argument('--blender',default=r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe');p.add_argument('--addon-parent')
a=p.parse_args();path=config_path();before=json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
after=dict(before);after.update(schema_version=1,output_root=str(Path(a.output_root).resolve()),blender=str(Path(a.blender).resolve()),allow_external_3d_inference=False)
after['read_roots']=list(dict.fromkeys(before.get('read_roots',[])+[str(Path(r).resolve()) for r in a.read_root]))
if a.addon_parent:after['addon_parent']=str(Path(a.addon_parent).resolve())
print(json.dumps({'config':str(path),'changes':{k:{'before':before.get(k),'after':v} for k,v in after.items() if before.get(k)!=v},'apply':a.apply},indent=2))
if a.apply:
    if path.is_file() and before!=after:
        backup=ROOT/'.tmp'/'codex-backups'/f'{time.time_ns()}-host-config.json';backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup)
    atomic_json(path,after)
    current=json.loads(path.read_text(encoding='utf-8'));assert current==after
    assert all(current[k]==v for k,v in before.items() if k not in {'schema_version','output_root','blender','allow_external_3d_inference','read_roots','addon_parent'})
