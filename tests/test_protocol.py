import json
import threading
import uuid
import urllib.request
import urllib.error
import pytest
from blender_bridge.core import RuntimeState, BridgeError
from blender_bridge.client import Client
from blender_bridge.transport import start_http
from blender_bridge.catalog import validate, OPS


def request(state, **values):
    return {"operation":"mesh.primitive", "args":{"name":"A","kind":"cube"},
            "session":state.session, "revision":state.revision, "request_id":str(uuid.uuid4()), **values}


def test_duplicate_is_once_and_conflicting_reuse_rejected(tmp_path):
    s = RuntimeState(tmp_path)
    q = request(s)
    s.submit(q)
    s.submit(q)
    calls = []
    s.execute_one(lambda n,a: calls.append(n) or {}, lambda:{})
    s.execute_one(lambda n,a: calls.append(n) or {}, lambda:{})
    assert calls == ['mesh.primitive']
    assert s.submit(q)['state'] == 'succeeded'
    with pytest.raises(BridgeError, match='different arguments'): s.submit({**q,'args':{'name':'B','kind':'cube'}})


def test_stale_session_and_queued_revision(tmp_path):
    s = RuntimeState(tmp_path)
    with pytest.raises(BridgeError, match='Re-discover'): s.submit(request(s,session='old'))
    a,b = request(s),request(s)
    s.submit(a); s.submit(b)
    s.execute_one(lambda n,a:{}, lambda:{})
    s.execute_one(lambda n,a:pytest.fail('stale write executed'), lambda:{})
    assert s.job(b['request_id'])['error']['code'] == 'STALE_REVISION'
    assert s.revision == 1


def test_partial_failure_and_cancel(tmp_path):
    s = RuntimeState(tmp_path)
    q = request(s)
    s.submit(q)
    def fail(n,a): raise RuntimeError('real failure')
    s.execute_one(fail,lambda:{})
    assert s.job(q['request_id'])['error']['partial_changes_possible']
    assert s.revision == 1
    q = request(s)
    s.submit(q); s.cancel(q['request_id'])
    s.execute_one(lambda n,a:pytest.fail('cancelled job executed'),lambda:{})


def test_schema_and_paths(tmp_path):
    s = RuntimeState(tmp_path/'out')
    for values in ({'name':'X','kind':'sphere','scale':[1,float('nan'),1]},
                   {'name':'X','kind':'cube','unknown':1}, {'name':'X','kind':'cube','segments':True}):
        with pytest.raises(ValueError): validate(values,OPS['mesh.primitive']['inputSchema'])
    for path in ('../escape.blend','x.fbx'):
        with pytest.raises(BridgeError): s.output_path(path,'.blend')
    path = s.output_path('a.blend','.blend'); path.write_bytes(b'original')
    with pytest.raises(BridgeError): s.output_path('a.blend','.blend')
    s.output_path('a.blend','.blend',True)
    assert next((s.output_root/'.backups').iterdir()).read_bytes() == b'original'
    with pytest.raises(BridgeError): s.submit(request(s,operation='python.execute',args={'code':'pass'}))


def test_output_requires_revision_and_capacity_retains_identity(tmp_path):
    s = RuntimeState(tmp_path,max_jobs=1)
    q = request(s,operation='scene.save',args={'path':'test.blend'})
    q.pop('revision')
    with pytest.raises(BridgeError,match='revision'): s.submit(q)
    q['revision'] = 0
    s.submit(q)
    s.execute_one(lambda n,a:{},lambda:{})
    assert s.submit(q)['state'] == 'succeeded'
    with pytest.raises(BridgeError,match='history is full'): s.submit(request(s))


def test_changed_session_invalidates_queued_work(tmp_path):
    s = RuntimeState(tmp_path)
    q = request(s)
    s.submit(q)
    s.session = str(uuid.uuid4())
    s.execute_one(lambda n,a:pytest.fail('old scene write executed'),lambda:{})
    assert s.job(q['request_id'])['error']['code'] == 'STALE_SESSION'


def test_http_auth_large_body_and_detached_job(tmp_path):
    s = RuntimeState(tmp_path)
    server = start_http(s)
    descriptor = {'session':s.session,'pid':0,'endpoint':f'http://127.0.0.1:{server.server_port}','token':s.token}
    client = Client(descriptor)
    try:
        assert client.call('health')['session'] == s.session
        bad = Client({**descriptor,'token':'wrong'})
        with pytest.raises(BridgeError,match='Authentication'): bad.call('health')
        q = request(s, operation='mesh.create',args={'name':'large','vertices':[[i,0,0] for i in range(3000)],'faces':[[0,1,2]]})
        job = client.call('submit',q)
        assert job['state'] == 'queued'
        s.execute_one(lambda n,a:{'count':len(a['vertices'])},lambda:{})
        assert client.call('job',{'id':job['id']})['result']['count'] == 3000
    finally:
        server.shutdown(); server.server_close()


def test_restart_keeps_original_ids_but_interrupts_unfinished_work(tmp_path):
    first=RuntimeState(tmp_path,max_jobs=1);queued=request(first);first.submit(queued)
    restarted=RuntimeState(tmp_path,max_jobs=1)
    assert restarted.job(queued['request_id'])['state']=='interrupted'
    assert restarted.job(queued['request_id'])['error']['code']=='RESULT_UNKNOWN'
    # Reconnection must never queue/replay the original old-session write.
    assert restarted.submit(queued)['state']=='interrupted'
    current=request(restarted);assert restarted.submit(current)['state']=='queued'
    calls=[];restarted.execute_one(lambda n,a:calls.append(n) or {},lambda:{})
    assert calls==['mesh.primitive']


def test_memory_failure_reports_partial_scope_and_never_retries(tmp_path):
    state=RuntimeState(tmp_path);q=request(state);state.submit(q);calls=[]
    def controlled_failure(name,args):
        calls.append(name);raise MemoryError('controlled allocation failure; no actual memory exhaustion')
    state.execute_one(controlled_failure,lambda:{})
    assert state.job(q['request_id'])['state']=='failed'
    assert state.job(q['request_id'])['error']['partial_changes_possible']
    assert state.submit(q)['state']=='failed'
    state.execute_one(controlled_failure,lambda:{})
    assert len(calls)==1

