import pytest
from blender_bridge.catalog import OPS, validate


def test_graph_contract_is_guarded_and_bounded():
    spec = OPS['node_graph.patch']
    assert spec['requires_session'] and spec['requires_revision']
    assert spec['cancellation'] == 'queued_only'
    assert not OPS['node_graph.inspect']['mutates_scene']
    args = {'owner':{'kind':'geometry','object':'A','modifier':'Nodes'},'graph_token':'current',
            'actions':[{'action':'set_input','node':'Transform','socket':'Translation','value':[1,2,3]}]}
    validate(args,spec['inputSchema'])
    with pytest.raises(ValueError):validate({**args,'actions':args['actions']*65},spec['inputSchema'])
    with pytest.raises(ValueError):validate({**args,'actions':[{'action':'python','code':'pass'}]},spec['inputSchema'])
    with pytest.raises(ValueError):validate({**args,'actions':[{'action':'set_property','node':'A','property':'operation','value':{'bad':'pointer'}}]},spec['inputSchema'])


def test_semantic_forward_requires_evidence_and_is_not_export_axis():
    spec = OPS['export.package']['inputSchema']
    args = {'objects':['A'],'directory':'package','semantic_forward':{'axis':'+X','basis':'measured','evidence':'Measured muzzle axis'}}
    validate(args,spec)
    with pytest.raises(ValueError):validate({**args,'semantic_forward':{'axis':'-Y','basis':'exporter'}},spec)
    with pytest.raises(ValueError):validate({**args,'semantic_forward':{'axis':'+X','basis':'measured'}},spec)
