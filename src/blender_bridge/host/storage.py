"""Durable jobs and records with root-contained immutable artifact publication."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid
import psutil
from ..core import BridgeError, atomic_json


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):digest.update(data)
    return digest.hexdigest()


def config_path():
    return Path(os.environ.get('BLENDER_BRIDGE_CONFIG',Path.home()/'.blender-bridge'/'config.json'))


def configuration(override=None):
    path=Path(override) if override else config_path()
    if path.is_file():data=json.loads(path.read_text(encoding='utf-8-sig'))
    else:data={}
    data.setdefault('output_root',str(Path.home()/'BlenderBridgeOutput'))
    data.setdefault('read_roots',[])
    data.setdefault('blender',r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' if os.name=='nt' else 'blender')
    data.setdefault('allow_external_3d_inference',False)
    data.setdefault('schema_version',1)
    return data


class Store:
    def __init__(self,root=None,config=None):
        self.config=config or configuration()
        self.root=Path(root or self.config['output_root']).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.internal=self.root/'.bridge'/'host';self.internal.mkdir(parents=True,exist_ok=True)
        self.database=self.internal/'state.sqlite3'
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS records(kind TEXT NOT NULL,id TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,request TEXT NOT NULL,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts(id TEXT NOT NULL,sha TEXT NOT NULL,read_at REAL NOT NULL,PRIMARY KEY(id,sha));
            ''')

    @contextmanager
    def db(self):
        con=sqlite3.connect(self.database,timeout=30)
        try:
            con.execute('PRAGMA journal_mode=WAL');con.execute('PRAGMA busy_timeout=30000')
            yield con;con.commit()
        except Exception:con.rollback();raise
        finally:con.close()

    def put(self,kind,identity,value,create=False):
        with self.db() as db:
            if create:
                try:db.execute('INSERT INTO records VALUES(?,?,?)',(kind,identity,json.dumps(value,ensure_ascii=False)))
                except sqlite3.IntegrityError as exc:raise BridgeError('ID_CONFLICT',kind+':'+identity) from exc
            else:db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?)',(kind,identity,json.dumps(value,ensure_ascii=False)))
        return value

    def get(self,kind,identity):
        with self.db() as db:row=db.execute('SELECT value FROM records WHERE kind=? AND id=?',(kind,identity)).fetchone()
        if not row:raise BridgeError('RECORD_NOT_FOUND',kind+':'+identity)
        return json.loads(row[0])

    def records(self,kind):
        with self.db() as db:rows=db.execute('SELECT value FROM records WHERE kind=? ORDER BY id',(kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def input(self,name):
        path=Path(name).resolve();roots=[self.root]+[Path(p).resolve() for p in self.config['read_roots']]
        if not path.is_file() or not any(path.is_relative_to(r) for r in roots):raise BridgeError('PATH_DENIED','Input must exist within configured read roots')
        return path

    def output(self,name,suffix=None):
        path=Path(name);path=(path if path.is_absolute() else self.root/path).resolve()
        if path==self.root or not path.is_relative_to(self.root) or suffix and path.suffix.lower()!=suffix:raise BridgeError('PATH_DENIED','Output must be a matching file under output_root')
        if path.exists():raise BridgeError('FILE_EXISTS','Immutable output already exists: '+str(path))
        path.parent.mkdir(parents=True,exist_ok=True);return path

    def artifact(self,path,kind,provenance=None,**extra):
        path=Path(path).resolve()
        if not path.is_relative_to(self.root) or not path.is_file() or not path.stat().st_size:raise BridgeError('ARTIFACT_MISSING','Artifact must be nonempty within output root')
        data={'id':str(uuid.uuid4()),'path':str(path),'kind':kind,'sha256':sha(path),'bytes':path.stat().st_size,'created':time.time(),'provenance':provenance or {},**extra}
        with self.db() as db:db.execute('INSERT INTO artifacts VALUES(?,?)',(data['id'],json.dumps(data,ensure_ascii=False)))
        return data

    def import_artifacts(self,entries,root):
        allowed=Path(root).resolve()
        for entry in entries:
            path=Path(entry['path']).resolve()
            if not path.is_relative_to(allowed) or not path.is_file() or sha(path)!=entry['sha256']:raise BridgeError('ARTIFACT_INVALID','Runtime artifact failed root/hash verification')
            record={**entry,'registered_root':str(allowed)}
            with self.db() as db:db.execute('INSERT OR REPLACE INTO artifacts VALUES(?,?)',(entry['id'],json.dumps(record,ensure_ascii=False)))

    def artifacts(self):
        with self.db() as db:rows=db.execute('SELECT value FROM artifacts ORDER BY id').fetchall()
        return [json.loads(r[0]) for r in rows]

    def get_artifact(self,identity):
        with self.db() as db:row=db.execute('SELECT value FROM artifacts WHERE id=?',(identity,)).fetchone()
        if not row:raise BridgeError('ARTIFACT_NOT_FOUND',identity)
        artifact=json.loads(row[0]);path=Path(artifact['path']).resolve();root=Path(artifact.get('registered_root',self.root)).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha(path)!=artifact['sha256']:raise BridgeError('ARTIFACT_CHANGED','Registered artifact file/hash changed')
        return artifact

    def read_image(self,identity):
        artifact=self.get_artifact(identity);path=Path(artifact['path'])
        if artifact['kind'] not in ('image/png','image/jpeg','image/webp') or path.stat().st_size>16*1024*1024:raise BridgeError('IMAGE_DENIED','Registered image under 16 MiB required')
        data=path.read_bytes()
        with self.db() as db:db.execute('INSERT OR REPLACE INTO receipts VALUES(?,?,?)',(identity,artifact['sha256'],time.time()))
        return artifact,data

    def was_read(self,identity,digest):
        with self.db() as db:row=db.execute('SELECT read_at FROM receipts WHERE id=? AND sha=?',(identity,digest)).fetchone()
        return bool(row)

    def json_artifact(self,name,data,provenance=None):
        path=self.output(name,'.json');atomic_json(path,data)
        return self.artifact(path,'application/json',provenance)


def process_identity(pid):
    try:
        p=psutil.Process(pid)
        return {'pid':pid,'create_time':p.create_time(),'exe':str(Path(p.exe()).resolve()),'cmdline':p.cmdline()}
    except (psutil.NoSuchProcess,psutil.AccessDenied):return None


def matches_process(record):
    identity=process_identity(record['pid']) if record.get('pid') else None
    return bool(identity and all(identity.get(k)==record.get(k) for k in ('pid','create_time','exe','cmdline')))
