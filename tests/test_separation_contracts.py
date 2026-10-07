import uuid
import pytest
from blender_bridge.catalog import OPS, validate
from blender_bridge.core import RuntimeState, BridgeError


def separation_request(state):
    return {'operation': 'object.separate', 'args': {'object': 'Mesh', 'name': 'Parts',
            'selection_id': 'region-id', 'face_policy': 'all_vertices', 'keep_original': True},
            'session': state.session, 'revision': state.revision, 'request_id': str(uuid.uuid4())}


def test_selection_contract_rejects_untyped_policy_and_requires_revision(tmp_path):
    state = RuntimeState(tmp_path)
    request = separation_request(state)
    validate(request['args'], OPS['object.separate']['inputSchema'])
    with pytest.raises(ValueError):
        validate({**request['args'], 'face_policy': 'guess'}, OPS['object.separate']['inputSchema'])
    with pytest.raises(BridgeError, match='revision'):
        state.submit({key: value for key, value in request.items() if key != 'revision'})
    with pytest.raises(BridgeError, match='Re-discover'):
        state.submit({**request, 'session': 'another-session'})


def test_separation_retry_cancel_and_stale_queue(tmp_path):
    state = RuntimeState(tmp_path)
    first, stale, cancelled = (separation_request(state) for _ in range(3))
    for request in (first, stale, cancelled):
        state.submit(request)
    state.cancel(cancelled['request_id'])
    calls = []
    def execute(operation, args):
        calls.append((operation, args))
        return {'created': ['Part']}
    for _ in range(3):
        state.execute_one(execute, lambda: {})
    assert len(calls) == 1
    assert state.submit(first)['state'] == 'succeeded'
    assert state.job(stale['request_id'])['error']['code'] == 'STALE_REVISION'
    assert state.job(cancelled['request_id'])['state'] == 'cancelled'
    with pytest.raises(BridgeError, match='different arguments'):
        state.submit({**first, 'args': {**first['args'], 'name': 'DifferentParts'}})
