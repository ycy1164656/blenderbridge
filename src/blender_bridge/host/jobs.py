"""Durable Host request IDs; detached runners survive CLI/MCP disconnection."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from .storage import Store, process_identity, matches_process
from ..catalog import OPS, validate
from ..core import BridgeError


class HostJobs:
    def __init__(self,store):self.store=store

    def submit(self,operation,args,request_id,session=None,revision=None):
        if not isinstance(request_id,str) or not 8<=len(request_id)<=128:raise BridgeError('INVALID_REQUEST','Stable request_id of 8..128 characters required')
        if operation not in OPS or OPS[operation]['execution_domain']!='host_cpu':raise BridgeError('WRONG_EXECUTION_DOMAIN',operation)
        validate(args,OPS[operation]['inputSchema'])
        request={'operation':operation,'args':args,'session':session,'revision':revision,'request_id':request_id}
        digest=hashlib.sha256(json.dumps(request,sort_keys=True,allow_nan=False).encode()).hexdigest()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT fingerprint,value FROM jobs WHERE id=?',(request_id,)).fetchone()
            if row:
                if row[0]!=digest:raise BridgeError('REQUEST_ID_CONFLICT','Host ID already belongs to different request')
                return json.loads(row[1])
            job={'id':request_id,'operation':operation,'state':'queued','submitted':time.time(),'session':session,'before_revision':revision}
            db.execute('INSERT INTO jobs VALUES(?,?,?,?)',(request_id,digest,json.dumps(request),json.dumps(job)))
        if OPS[operation]['long_running']:
            from ..core import atomic_json
            payload=self.store.internal/'requests'/(hashlib.sha256(request_id.encode()).hexdigest()+'.json')
            atomic_json(payload,{'root':str(self.store.root),'config':self.store.config,'id':request_id})
            from .broker import broker_ready
            self.update(request_id,payload=str(payload),wait_reason=None if broker_ready(self.store) else 'host_broker_not_running; start tools/start_host.ps1 outside the MCP process')
        else:self.run(request_id)
        return self.get(request_id)

    def update(self,request_id,**values):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT value FROM jobs WHERE id=?',(request_id,)).fetchone()
            if not row:raise BridgeError('JOB_NOT_FOUND',request_id)
            job=json.loads(row[0]);job.update(values);db.execute('UPDATE jobs SET value=? WHERE id=?',(json.dumps(job,ensure_ascii=False),request_id))
        return job

    def get(self,request_id):
        with self.store.db() as db:row=db.execute('SELECT value FROM jobs WHERE id=?',(request_id,)).fetchone()
        if not row:raise BridgeError('JOB_NOT_FOUND',request_id)
        job=json.loads(row[0])
        if job['state'] in ('queued','running') and job.get('runner') and not matches_process(job['runner']):
            job=self.update(request_id,state='interrupted',error={'code':'RESULT_UNKNOWN','message':'Owned runner exited before terminal record. Query linked native/worker job; no automatic replay.'})
        return job

    def cancel(self,request_id):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT value FROM jobs WHERE id=?',(request_id,)).fetchone()
            if not row:raise BridgeError('JOB_NOT_FOUND',request_id)
            job=json.loads(row[0])
            if job['state']!='queued':raise BridgeError('CANNOT_CANCEL','Only queued Host jobs can be cancelled; use worker.cancel for an exact owned Blender')
            job.update(state='cancelled',finished=time.time());db.execute('UPDATE jobs SET value=? WHERE id=?',(json.dumps(job),request_id))
        return job

    def recover_before_start(self,request_id):
        job=self.get(request_id)
        if job['state']!='interrupted' or 'started' in job or job.get('runner') and matches_process(job['runner']):
            raise BridgeError('RECOVERY_UNSAFE','Only an interrupted Host request whose durable execution never started may be requeued under its original ID')
        payload=self.store.internal/'requests'/(hashlib.sha256(request_id.encode()).hexdigest()+'.json')
        if not payload.is_file():raise BridgeError('PAYLOAD_MISSING','Frozen request payload is missing')
        return self.update(request_id,state='queued',runner=None,dispatch_owner=None,payload=str(payload),error=None,
                           recovery={'type':'before_start_same_id','at':time.time(),'previous_state':job['state'],'native_execution_started':False})

    def run(self,request_id):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT request,value FROM jobs WHERE id=?',(request_id,)).fetchone()
            if not row:raise BridgeError('JOB_NOT_FOUND',request_id)
            request,job=map(json.loads,row)
            if job['state']!='queued':return job
            job.update(state='running',started=time.time());db.execute('UPDATE jobs SET value=? WHERE id=?',(json.dumps(job),request_id))
        try:
            from .operations import HostOperations
            result=HostOperations(self.store,request).execute(request['operation'],request['args']);json.dumps(result,allow_nan=False)
            return self.update(request_id,state='succeeded',result=result,finished=time.time())
        except Exception as exc:
            error={'code':getattr(exc,'code','HOST_OPERATION_FAILED'),'message':str(exc)}
            if hasattr(exc,'details'):error['details']=exc.details
            return self.update(request_id,state='cancelled' if error['code']=='WORKER_CANCELLED' else 'failed',error=error,finished=time.time())

    def wait(self,request_id,timeout=30):
        deadline=time.monotonic()+timeout
        while True:
            job=self.get(request_id)
            if job['state'] not in ('queued','running') or time.monotonic()>=deadline:return job
            time.sleep(.1)
