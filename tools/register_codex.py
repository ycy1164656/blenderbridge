"""Narrow MCP registration with config backup and unrelated-settings verification."""
from pathlib import Path
import os
import shutil
import subprocess
import time
import tomllib

root = Path(__file__).resolve().parents[1]
config = Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'config.toml'
before = tomllib.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
python = root/'.venv'/'Scripts'/'python.exe' if os.name == 'nt' else root/'.venv'/'bin'/'python'
codex = shutil.which('codex')
if not python.exists() or not codex: raise SystemExit('Run uv sync and install Codex CLI first')
expected = {'command':str(python),'args':['-m','blender_bridge.mcp_server']}
existing = before.get('mcp_servers',{}).get('blender_bridge')
if existing:
    if all(existing.get(k) == v for k,v in expected.items()):
        print('MCP_ALREADY_REGISTERED blender_bridge')
        raise SystemExit(0)
    raise SystemExit('Existing blender_bridge config differs; preserved for explicit review')
backup = root/'.tmp'/'codex-backups'/f'{time.time_ns()}-codex-config.toml'
backup.parent.mkdir(parents=True,exist_ok=True)
if config.exists(): shutil.copy2(config,backup)
subprocess.run([codex,'mcp','add','blender_bridge','--',str(python),'-m','blender_bridge.mcp_server'],check=True)
after = tomllib.loads(config.read_text(encoding='utf-8'))
added = after.get('mcp_servers',{}).pop('blender_bridge',None)
if 'mcp_servers' not in before and not after.get('mcp_servers'): after.pop('mcp_servers',None)
# Codex serializes empty stdio args as an omitted key. Compare their semantics.
for parsed in (before,after):
    for server in parsed.get('mcp_servers',{}).values():
        if 'command' in server: server.setdefault('args',[])
assert after == before, 'Unrelated configuration changed; inspect backup, do not auto-restore'
assert all(added.get(k)==v for k,v in expected.items()), 'Registration readback mismatch'
print(f'MCP_REGISTRATION_PASS blender_bridge; backup={backup}')

