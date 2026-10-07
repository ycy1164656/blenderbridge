import ast
from pathlib import Path
import pytest
from blender_bridge.catalog import OPS,validate
from blender_bridge.geometry_algorithms import loft,validate_ring


def test_every_catalog_operation_has_a_real_handler_with_compatible_parameters():
    root=Path(__file__).resolve().parents[1]/'src'/'blender_bridge'
    for domain,files in [('blender_main_thread',[root/'operations.py',*sorted((root/'operations_impl').glob('*.py'))]),('host_cpu',sorted((root/'host').glob('*.py')))]:
        methods={}
        for file in files:
            for node in ast.walk(ast.parse(file.read_text(encoding='utf-8'))):
                if isinstance(node,ast.FunctionDef):methods[node.name]=node
        for name,spec in OPS.items():
            if spec['execution_domain']!=domain:continue
            method=methods.get(name.replace('.','_'))
            assert method is not None,name
            if method.args.kwarg is None:
                parameters={arg.arg for arg in method.args.args[1:]+method.args.kwonlyargs}
                assert set(spec['inputSchema']['properties'])<=parameters,(name,set(spec['inputSchema']['properties'])-parameters)


def test_catalog_domain_guards():
    assert OPS['modeling.resume']['requires_session'] and OPS['modeling.resume']['requires_revision']
    assert OPS['preview.multiview']['writes_artifacts'] and OPS['preview.multiview']['requires_revision']
    assert not OPS['reference.crop']['mutates_scene']
    assert OPS['worker.submit']['long_running']
    assert OPS['preview.validate']['execution_domain']=='blender_main_thread'


def test_loft_rejects_self_intersection_and_degeneracy():
    with pytest.raises(ValueError):validate_ring([[0,0,0],[1,1,0],[0,1,0],[1,0,0]])
    with pytest.raises(ValueError):validate_ring([[0,0,0],[1,0,0],[2,0,0]])
    with pytest.raises(ValueError):validate_ring([[0,0,0],[1,0,0],[1,1,1],[0,1,0]])


def test_loft_cap_and_cyclic_alignment():
    lower=[[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]]
    upper=[[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]]
    vertices,faces=loft([lower,upper[2:]+upper[:2]],cap=True,align=True)
    assert len(vertices)==8 and len(faces)==6
    assert all(abs(vertices[i][0]-vertices[i+4][0])<1e-8 and abs(vertices[i][1]-vertices[i+4][1])<1e-8 for i in range(4))
