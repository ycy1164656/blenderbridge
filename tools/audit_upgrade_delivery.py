"""Final read-only document/config/source audit; records evidence without changing preferences."""
import datetime,hashlib,json,os,re,shutil,time,tomllib,urllib.parse
from pathlib import Path
from blender_bridge.core import atomic_json
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/native-modeling'
config=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'config.toml'
prior=ROOT/'.tmp/codex-backups/1791163566887711300-codex-config.toml'
a=tomllib.loads(prior.read_text());b=tomllib.loads(config.read_text())
for data in (a,b):
    data.get('mcp_servers',{}).pop('blender_bridge',None)
    for server in data.get('mcp_servers',{}).values():
        if 'command' in server:server.setdefault('args',[])
differences=[]
def compare(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        for key in sorted(set(a)|set(b)):
            if key not in a or key not in b:differences.append(path+key)
            else:compare(a[key],b[key],path+key+'.')
    elif a!=b:differences.append(path.rstrip('.'))
compare(a,b)
assert a.get('mcp_servers',{})==b.get('mcp_servers',{})
stamp=datetime.datetime.fromtimestamp(config.stat().st_mtime).isoformat()
assert config.stat().st_mtime<datetime.datetime(2026,10,5,14,55,31).timestamp()
evidence_path=OUT/'final-verification.json';evidence=json.loads(evidence_path.read_text())
backup=ROOT/'.tmp/codex-backups'/f'{time.time_ns()}-final-verification.json';backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(evidence_path,backup)
evidence.update(other_mcp_configuration_semantics_unchanged=True,codex_config_comparison={'historical_baseline':str(prior),'different_keys':differences,'current_last_write_local':stamp,'last_write_precedes_upgrade_start':True,'configuration_written_by_this_upgrade':False,'note':'Only historical model_reasoning_effort differs; all unrelated MCP servers equal. Do not restore user setting.'})
atomic_json(evidence_path,evidence)
documents=list((ROOT/'docs').rglob('*.md'));numbered={};missing=[]
for path in documents:
    match=re.match(r'([0-9]{3})_',path.name)
    if match:numbered.setdefault(int(match[1]),[]).append(path.name)
# Balanced parentheses are legal in our report filenames.
for path in [ROOT/'README.md',*documents,*((ROOT/'skills').rglob('*.md'))]:
    source=path.read_text(encoding='utf-8')
    for match in re.finditer(r'\]\(',source):
        start=match.end();depth=1;end=start
        while end<len(source) and depth:
            depth += (source[end]=='(')-(source[end]==')');end+=1
        target=source[start:end-1].strip().strip('<>')
        if not target or re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:',target) or target.startswith('#'):continue
        target=urllib.parse.unquote(target.split('#')[0])
        if target and not (path.parent/target).exists():missing.append({'document':str(path.relative_to(ROOT)),'target':target})
report={'documents':len(documents),'max_number':max(numbered),'duplicates':{str(n):p for n,p in numbered.items() if len(p)>1},'gaps':[n for n in range(min(numbered),max(numbered)+1) if n not in numbered],'missing_links':missing,'other_mcp_equal':True,'historical_config_differences':differences,'config_last_write':stamp}
atomic_json(OUT/'document-audit.json',report);print(json.dumps(report,ensure_ascii=False))
