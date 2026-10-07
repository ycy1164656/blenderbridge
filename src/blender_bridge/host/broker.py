"""Persistent owned Host broker, launched outside an MCP client's process lifetime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from .storage import Store,configuration,process_identity,matches_process
from ..core import atomic_json


def broker_ready(store):
    path=store.internal/'broker.json'
    try:
        record=json.loads(path.read_text(encoding='utf-8'))
        return record if time.time()-record.get('heartbeat',0)<15 and matches_process(record) else None
    except (OSError,ValueError):return None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root');parser.add_argument('--config');args=parser.parse_args()
    store=Store(args.root,configuration(args.config));path=store.internal/'broker.json'
    if broker_ready(store):raise SystemExit('A matching Host broker is already running')
    identity=process_identity(os.getpid());children={}
    while True:
        atomic_json(path,{**identity,'heartbeat':time.time(),'root':str(store.root),'role':'blender_bridge_host_broker'})
        for rid,process in list(children.items()):
            if process.poll() is not None:children.pop(rid)
        claimed=[]
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE');rows=db.execute('SELECT id,value FROM jobs').fetchall()
            for rid,value in rows:
                job=json.loads(value)
                if job['state']!='queued' or job.get('runner') or job.get('dispatch_owner') or not job.get('payload'):continue
                if len(children)+len(claimed)>=2:break
                job['dispatch_owner']={'pid':identity['pid'],'create_time':identity['create_time']};job.pop('wait_reason',None)
                db.execute('UPDATE jobs SET value=? WHERE id=?',(json.dumps(job),rid));claimed.append((rid,job))
        for rid,job in claimed:
            payload=Path(job['payload']).resolve()
            if not payload.is_relative_to(store.internal/'requests'):
                from .jobs import HostJobs
                HostJobs(store).update(rid,state='failed',error={'code':'PAYLOAD_PATH_DENIED','message':'Invalid internal payload path'});continue
            log=store.internal/'logs'/(hashlib.sha256(rid.encode()).hexdigest()+'.log');log.parent.mkdir(exist_ok=True)
            with log.open('ab') as output:
                process=subprocess.Popen([sys.executable,'-m','blender_bridge.host.runner',str(payload)],stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,start_new_session=os.name!='nt')
            from .jobs import HostJobs
            HostJobs(store).update(rid,runner=process_identity(process.pid),log=str(log));children[rid]=process
        time.sleep(.25)


if __name__=='__main__':main()
