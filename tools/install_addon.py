"""Run inside Blender --background WITHOUT --factory-startup to preserve user preferences."""
from pathlib import Path
import shutil
import time
import json
import sys
import zipfile
import hashlib
import ast
import bpy

root = Path(__file__).resolve().parents[1]
tree=ast.parse((root/'src'/'blender_bridge'/'__init__.py').read_text(encoding='utf-8'))
version=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in n.targets))
archive = root/'dist'/f'blender_bridge-{version}.zip'
destination = Path(bpy.utils.user_resource('SCRIPTS',path='addons',create=True))/'blender_bridge'
upgrading = destination.exists()
with zipfile.ZipFile(archive) as z:package=json.loads(z.read('blender_bridge/.blender-bridge-install.json'))
existing_prefs=bpy.context.preferences.addons.get('blender_bridge')
saved_prefs={key:getattr(existing_prefs.preferences,key) for key in ('output_root','read_roots','port','allow_python')} if existing_prefs else None
if upgrading:
    if '--upgrade' not in sys.argv:
        raise RuntimeError(f'Existing add-on preserved; review upgrade explicitly: {destination}')
    # The prior package proves ownership and detects local customization before replacement.
    ownership=destination/'.blender-bridge-install.json'
    if ownership.is_file():expected=json.loads(ownership.read_text(encoding='utf-8'))['files']
    else:
        previous = Path(sys.argv[sys.argv.index('--previous-archive')+1]).resolve() if '--previous-archive' in sys.argv else root/'.tmp'/'previous-addon.zip'
        if not previous.is_file(): raise RuntimeError('Verified previous package required for first managed upgrade')
        with zipfile.ZipFile(previous) as z:expected={n.removeprefix('blender_bridge/'):hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.endswith('.py')}
    actual={p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*.py')}
    if actual!=expected:raise RuntimeError('Installed code differs from ownership baseline; preserved for review')
    unknown=[p for p in destination.rglob('*') if p.is_file() and p.suffix not in ('.py','.pyc') and p.name!='.blender-bridge-install.json']
    if unknown:raise RuntimeError('Unmanaged files in addon directory; preserved: '+str(unknown))
plan={'archive':str(archive),'destination':str(destination),'version':version,'files':len(package['files']),'preserved_preferences':saved_prefs,'upgrade':upgrading}
print('ADDON_INSTALL_PLAN '+json.dumps(plan),flush=True)
if '--apply' not in sys.argv:raise SystemExit(0)
if upgrading:
    addon_backup = root/'.tmp'/'codex-backups'/f'{time.time_ns()}-blender-addon'
    shutil.copytree(destination,addon_backup)
    if existing_prefs:bpy.ops.preferences.addon_disable(module='blender_bridge')
    for key in list(sys.modules):
        if key=='blender_bridge' or key.startswith('blender_bridge.'):del sys.modules[key]
pref_file = Path(bpy.utils.user_resource('CONFIG'))/'userpref.blend'
backup = root/'.tmp'/'codex-backups'/f'{time.time_ns()}-blender-preferences'
if pref_file.exists():
    backup.mkdir(parents=True)
    shutil.copy2(pref_file,backup/'userpref.blend')
bpy.ops.preferences.addon_install(filepath=str(archive),overwrite=upgrading)
bpy.ops.preferences.addon_enable(module='blender_bridge')
prefs = bpy.context.preferences.addons['blender_bridge'].preferences
if saved_prefs:
    for key,value in saved_prefs.items():setattr(prefs,key,value)
else:
    prefs.output_root=str(root/'artifacts'/'native-modeling');prefs.allow_python=False
bpy.ops.wm.save_userpref()
assert destination.is_dir() and pref_file.is_file()
actual={p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*.py')}
assert actual==package['files'],'Installed code hash mismatch'
report = {'addon_path':str(destination),'enabled':True,'auto_start':False,'allow_python':prefs.allow_python,'version':version,'files_verified':len(actual),
          'output_root':prefs.output_root,'read_roots':prefs.read_roots,'port':prefs.port,'preferences_preserved':saved_prefs is not None,
          'addon_backup':str(addon_backup) if upgrading else None,
          'preferences':str(pref_file),'preferences_backup':str(backup) if backup.exists() else None,
          'blender':bpy.app.version_string}
out = root/'.tmp'/'installation.json'
if out.exists():
    report_backup=root/'.tmp'/'codex-backups'/f'{time.time_ns()}-installation.json';report_backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(out,report_backup)
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print('ADDON_INSTALL_PASS ' + json.dumps(report))

