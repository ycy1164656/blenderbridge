"""Shared MCP/CLI routing with exact session and artifact read semantics."""
import uuid
from .storage import Store
from .jobs import HostJobs
from ..catalog import OPS,validate
from ..client import connect,discover
from ..core import BridgeError


class Gateway:
    def __init__(self,root=None,config=None,sessions_dir=None):
        self.store=Store(root,config);self.sessions_dir=sessions_dir or self.store.config.get('sessions_dir');self.jobs=HostJobs(self.store)

    def client(self,session):
        if not session:raise BridgeError('SESSION_REQUIRED','Discover and select an exact Blender session')
        return connect(session,self.sessions_dir)

    def catalog(self,session=None,query='',describe=''):
        entries={name:{**spec,'availability':'host' if spec['execution_domain']=='host_cpu' else 'requires_live_session'} for name,spec in OPS.items()}
        if session:
            live=self.client(session).call('catalog')['operations']
            for spec in live:entries[spec['name']]={**spec,'availability':'runtime_advertised'}
        if describe:
            if describe not in entries:raise BridgeError('UNKNOWN_OPERATION',describe)
            return entries[describe]
        return {'operations':[v for n,v in entries.items() if query.lower() in (n+' '+v['description']).lower()]}

    def execute(self,operation,args,request_id,session=None,revision=None,wait_seconds=1):
        if operation not in OPS:raise BridgeError('UNKNOWN_OPERATION',operation)
        spec=OPS[operation];validate(args,spec['inputSchema'])
        if spec['requires_session'] and not session:raise BridgeError('SESSION_REQUIRED','Exact session required')
        if spec['requires_revision'] and type(revision) is not int:raise BridgeError('REVISION_REQUIRED','Explicit observed revision required')
        if spec['execution_domain']=='host_cpu':
            job=self.jobs.submit(operation,args,request_id,session,revision)
            return self.jobs.wait(job['id'],min(60,max(0,wait_seconds))) if wait_seconds else job
        client=self.client(session);job=client.submit(operation,args,revision,request_id)
        if wait_seconds:job=client.wait(job['id'],min(60,max(0,wait_seconds)))
        return job

    def job(self,identity,session=None,cancel=False):
        if session:return self.client(session).call('cancel' if cancel else 'job',{'id':identity})
        return self.jobs.cancel(identity) if cancel else self.jobs.get(identity)

    def artifacts(self,session=None):
        if session:
            client=self.client(session);health=client.call('health');entries=client.call('artifacts')['artifacts']
            self.store.import_artifacts(entries,health['output_root'])
        return {'artifacts':self.store.artifacts()}

    def image(self,identity,session=None):
        if session:self.artifacts(session)
        return self.store.read_image(identity)
