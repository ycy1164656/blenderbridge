"""Run inside Blender --background WITHOUT --factory-startup to preserve user preferences."""
from pathlib import Path
import shutil
import time
import json
import sys
import zipfile
import bpy

root = Path(__file__).resolve().parents[1]
archive = root/'dist'/'blender_bridge-0.1.0.zip'
destination = Path(bpy.utils.user_resource('SCRIPTS',path='addons',create=True))/'blender_bridge'
upgrading = destination.exists()
if upgrading:
    if '--upgrade' not in sys.argv:
        raise RuntimeError(f'Existing add-on preserved; review upgrade explicitly: {destination}')
    # The prior package proves ownership and detects local customization before replacement.
    previous = root/'.tmp'/'previous-addon.zip'
    if not previous.is_file(): raise RuntimeError('Verified previous package required for upgrade')
    with zipfile.ZipFile(previous) as z:
        members = [n for n in z.namelist() if n.endswith('.py')]
        if set(p.name for p in destination.glob('*.py')) != set(Path(n).name for n in members):
            raise RuntimeError('Installed file set differs; preserved')
        for member in members:
            if (destination/Path(member).name).read_bytes() != z.read(member):
                raise RuntimeError('Installed code modified; preserved')
    addon_backup = root/'.tmp'/'codex-backups'/f'{time.time_ns()}-blender-addon'
    shutil.copytree(destination,addon_backup)
    bpy.ops.preferences.addon_disable(module='blender_bridge')
pref_file = Path(bpy.utils.user_resource('CONFIG'))/'userpref.blend'
backup = root/'.tmp'/'codex-backups'/f'{time.time_ns()}-blender-preferences'
if pref_file.exists():
    backup.mkdir(parents=True)
    shutil.copy2(pref_file,backup/'userpref.blend')
bpy.ops.preferences.addon_install(filepath=str(archive),overwrite=upgrading)
bpy.ops.preferences.addon_enable(module='blender_bridge')
prefs = bpy.context.preferences.addons['blender_bridge'].preferences
prefs.output_root = str(root/'outputs')
prefs.allow_python = False
bpy.ops.wm.save_userpref()
assert destination.is_dir() and pref_file.is_file()
report = {'addon_path':str(destination),'enabled':True,'auto_start':False,'allow_python':False,
          'preferences':str(pref_file),'preferences_backup':str(backup) if backup.exists() else None,
          'blender':bpy.app.version_string}
out = root/'.tmp'/'installation.json'
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print('ADDON_INSTALL_PASS ' + json.dumps(report))

