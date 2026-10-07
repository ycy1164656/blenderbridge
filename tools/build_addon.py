"""Package first-party Python files only; never include references, secrets or venv."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import time
import zipfile

root = Path(__file__).resolve().parents[1]
source=root/'src'/'blender_bridge'
tree=ast.parse((source/'__init__.py').read_text(encoding='utf-8'))
version=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in n.targets))
out = root/'dist'/f'blender_bridge-{version}.zip'
out.parent.mkdir(exist_ok=True)
if out.exists():
    backup=root/'.tmp'/'codex-backups'/f'{time.time_ns()}-{out.name}';backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(out,backup)
files={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.rglob('*.py'))}
manifest={'version':version,'files':files,'schema':'blender-bridge-install-v1'}
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for name in files:z.write(source/name,'blender_bridge/'+name)
    z.writestr('blender_bridge/.blender-bridge-install.json',json.dumps(manifest,indent=2))
print(out)
