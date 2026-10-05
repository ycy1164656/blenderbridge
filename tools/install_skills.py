"""Install tiny canonical skill routers. Preserve customized installed files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--apply', action='store_true')
p.add_argument('--skills-dir', type=Path, default=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'skills')
a = p.parse_args()
for name in ('blender-bridge','blender-reference-modeling'):
    source = root/'skills'/name/'SKILL.md'
    text = source.read_text(encoding='utf-8')
    front = text.split('---',2)[1]
    body = f'---{front}---\n\n# Canonical skill router\n\nRead and follow [{name} canonical skill](<{source.as_posix()}>) before doing work. Its relative references resolve under `{source.parent.as_posix()}`. This file is managed by `{root.as_posix()}/tools/install_skills.py`.\n'
    dest = a.skills_dir/name
    metadata = dest/'.blender-bridge-owner.json'
    target = dest/'SKILL.md'
    digest = hashlib.sha256(body.encode()).hexdigest()
    if dest.is_symlink() or (dest.exists() and getattr(dest,'is_junction',lambda:False)()): raise SystemExit(f'Refusing linked destination: {dest}')
    if target.is_symlink(): raise SystemExit(f'Refusing linked file: {target}')
    if target.exists():
        # Text written on Windows may use CRLF; line-ending normalization is not customization.
        current = hashlib.sha256(target.read_text(encoding='utf-8').encode()).hexdigest()
        owner = json.loads(metadata.read_text()) if metadata.exists() else {}
        if current != digest and owner.get('sha256') != current:
            raise SystemExit(f'Existing unmanaged or modified skill preserved: {target}')
        if current == digest:
            print(f'UNCHANGED {name}')
            continue
    print(('INSTALL ' if a.apply else 'PREVIEW ') + str(target))
    if a.apply:
        if dest.exists():
            shutil.copytree(dest,root/'.tmp'/'codex-backups'/f'{time.time_ns()}-{name}')
        dest.mkdir(parents=True,exist_ok=True)
        target.write_text(body,encoding='utf-8')
        (dest/'agents').mkdir(exist_ok=True)
        shutil.copy2(source.parent/'agents'/'openai.yaml',dest/'agents'/'openai.yaml')
        metadata.write_text(json.dumps({'canonical':str(source),'sha256':digest},indent=2),encoding='utf-8')

