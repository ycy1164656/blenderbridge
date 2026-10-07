"""0.3.0 separation tests in an owned factory-startup Blender, never a user scene.

Use --python-exit-code 1. --readback <manifest> runs in a second process.
--installed verifies the installed add-on rather than the source checkout.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import uuid

import bpy
from mathutils import Matrix

REPO = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--installed', action='store_true')
parser.add_argument('--readback')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
OUT = Path(args.output).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(bpy.utils.user_resource('SCRIPTS', path='addons')) if args.installed else REPO / 'src'))
from blender_bridge import __version__
from blender_bridge.catalog import OPS, validate
from blender_bridge.core import RuntimeState
from blender_bridge.operations import Operations

assert __version__ == '0.3.0', __version__
state = RuntimeState(OUT)
ops = Operations(state)
results = []


def run(operation, values):
    validate(values, OPS[operation]['inputSchema'])
    return ops.execute(operation, values)


def reject(values, code=None):
    objects = set(bpy.data.objects)
    try:
        run('object.separate', values)
    except Exception as exc:
        if code:
            assert getattr(exc, 'code', None) == code, (code, str(exc))
        assert set(bpy.data.objects) == objects, 'Preflight failure created objects'
        return
    raise AssertionError('Expected rejection: ' + str(values))


def record(name, fn):
    fn()
    results.append(name)
    print('TEST_PASS ' + name, flush=True)


def rounded(value):
    return tuple(round(float(x), 6) for x in value)


def independent_snapshot(objects):
    """Face/loose-vertex bags, independent of production index attributes and hashes."""
    faces = Counter()
    vertices = set()
    materials = {}
    for ob in objects:
        for v in ob.data.vertices:
            vertices.add((rounded(ob.matrix_world @ v.co), tuple(sorted((ob.vertex_groups[g.group].name, round(g.weight, 6)) for g in v.groups))))
        for face in ob.data.polygons:
            corners = []
            for i in face.loop_indices:
                v = ob.data.vertices[ob.data.loops[i].vertex_index]
                corners.append((rounded(ob.matrix_world @ v.co), tuple((uv.name, rounded(uv.data[i].uv)) for uv in ob.data.uv_layers)))
            start = min(range(len(corners)), key=lambda i: corners[i])
            material = ob.material_slots[face.material_index].material
            faces[repr((material.name, corners[start:] + corners[:start]))] += 1
        for slot in ob.material_slots:
            if not slot.material:
                continue
            material = slot.material
            materials[material.name] = [(node.name, node.image.name, node.image.filepath,
                                       hashlib.sha256(node.image.packed_file.data).hexdigest() if node.image.packed_file else None,
                                       list(node.image.size), node.image.colorspace_settings.name)
                                      for node in material.node_tree.nodes if node.type == 'TEX_IMAGE' and node.image]
    return {'faces': sorted(faces.items()), 'vertices': sorted(vertices), 'materials': materials}


def fixture(name, loose=False):
    vertices = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0)]
    faces = [(0, 1, 4, 3), (1, 2, 5, 4)]
    edges = []
    if loose:
        vertices = [(0,0,0), (1,0,0), (1,1,0), (0,1,0), (3,0,0), (4,0,0), (4,1,0), (3,1,0), (6,0,0), (7,0,0), (9,0,0)]
        faces = [(0,1,2,3), (4,5,6,7)]
        edges = [(8,9)]
    mesh = bpy.data.meshes.new(name + 'Mesh')
    mesh.from_pydata(vertices, edges, faces)
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    parent = bpy.data.objects.new(name + 'Parent', None)
    bpy.context.scene.collection.objects.link(parent)
    parent.location = (3, -2, 1)
    ob.parent = parent
    ob.matrix_basis = Matrix.Translation((.25, .5, .75)) @ Matrix.Rotation(.3, 4, 'Z')
    for layer_index, layer_name in enumerate(('MainUV', 'Lightmap')):
        layer = mesh.uv_layers.new(name=layer_name)
        for i, uv in enumerate(layer.data):
            uv.uv = ((i % 4) / 4 + layer_index * .01, (i // 4) * .4 + layer_index * .02)
    mesh.uv_layers.active_index = 1
    for i in range(2):
        material = bpy.data.materials.new(name + 'Material' + str(i))
        material.use_nodes = True
        texture = material.node_tree.nodes.new('ShaderNodeTexImage')
        image = bpy.data.images.new(name + 'Texture' + str(i), width=2, height=2)
        image.generated_color = (.2 + .3 * i, .15, .8 - .3 * i, 1)
        image.pack()
        texture.image = image
        shader = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        material.node_tree.links.new(texture.outputs['Color'], shader.inputs['Base Color'])
        mesh.materials.append(material)
    ob.material_slots[1].link = 'OBJECT'
    override = mesh.materials[1].copy()
    override.name = name + 'ObjectOverride'
    ob.material_slots[1].material = override
    for face in mesh.polygons:
        face.material_index = face.index % 2
    for group_name in ('Root', 'Tip'):
        group = ob.vertex_groups.new(name=group_name)
        for vertex in mesh.vertices:
            weight = .2 + .6 * (vertex.index % 2)
            group.add([vertex.index], weight if group_name == 'Root' else 1 - weight, 'REPLACE')
    armature = bpy.data.armatures.new(name + 'RigData')
    rig = bpy.data.objects.new(name + 'Rig', armature)
    bpy.context.scene.collection.objects.link(rig)
    modifier = ob.modifiers.new('Deformation', 'ARMATURE')
    modifier.object = rig
    modifier.use_deform_preserve_volume = True
    bpy.context.view_layer.update()
    run('scene.identify', {'objects': [ob.name]})
    return ob


def pieces(result):
    return [bpy.data.objects[item['name']] for item in [result['source'], *result['created']]]


def no_temporary_attributes():
    assert not [(mesh.name, attribute.name) for mesh in bpy.data.meshes for attribute in mesh.attributes if attribute.name.startswith('.bb_sep_')]


def explicit_faces():
    ob = fixture('Explicit')
    before = independent_snapshot([ob])
    for element in [*ob.data.vertices, *ob.data.edges, *ob.data.polygons]:
        element.select = True
    sentinel = bpy.data.objects['ExplicitParent']
    bpy.context.view_layer.objects.active = sentinel
    sentinel.select_set(True)
    bpy.context.scene.tool_settings.mesh_select_mode = (True, False, False)
    selected = {item.name for item in bpy.context.selected_objects}
    try:
        result = run('object.separate', {'object': ob.name, 'faces': [0], 'name': 'Exact'})
    except Exception:
        print('SEPARATION_DIAGNOSTIC ' + repr({o.name: [(s.link, s.material.name if s.material else None) for s in o.material_slots]
                                              for o in bpy.data.objects if o.type == 'MESH'}), flush=True)
        raise
    assert len(result['created']) == 1 and result['created'][0]['faces'] == 1
    assert ob.data.polygons[0].material_index == 1
    assert before == independent_snapshot(pieces(result))
    assert result['preservation']['boundary_vertex_duplicates'] == 2
    assert bpy.context.view_layer.objects.active == sentinel
    assert {item.name for item in bpy.context.selected_objects} == selected
    assert tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (True, False, False)
    no_temporary_attributes()


def region_copy():
    ob = fixture('Region')
    before = independent_snapshot([ob])
    source_hash = run('scene.fingerprint', {'objects': [ob.name]})
    selection = run('selection.query', {'objects': [ob.name], 'box_min': [-.1, -.1, -.1], 'box_max': [1.01, 1.1, .1], 'space': 'local'})
    assert selection['count'] == 4
    result = run('object.separate', {'object': ob.name, 'selection_id': selection['selection_id'], 'face_policy': 'all_vertices', 'name': 'RegionCopy', 'keep_original': True})
    assert source_hash == run('scene.fingerprint', {'objects': [ob.name]})
    assert before == independent_snapshot(pieces(result))
    assert result['original']['name'] == ob.name
    assert result['created'][0]['faces'] == 1
    assert selection['selection_id'] in state.selections
    assert len({o['bb_object_id'] for o in [ob, *pieces(result)]}) == 3
    assert len({o.data['bb_mesh_id'] for o in [ob, *pieces(result)]}) == 3
    return result


def boundary_policies():
    ob = fixture('Boundary')
    before = independent_snapshot([ob])
    selection = run('selection.query', {'objects': [ob.name], 'indices': [1, 4]})
    values = {'object': ob.name, 'selection_id': selection['selection_id'], 'name': 'BoundaryCut'}
    reject(values)
    reject({**values, 'face_policy': 'all_vertices'}, 'EMPTY_SELECTION')
    assert before == independent_snapshot([ob])
    result = run('object.separate', {**values, 'face_policy': 'any_vertex'})
    assert result['created'][0]['faces'] == 2 and result['source']['faces'] == 0
    assert independent_snapshot(pieces(result)) == before
    assert selection['selection_id'] not in state.selections
    reject({**values, 'face_policy': 'any_vertex'}, 'STALE_SELECTION')


def loose_parts():
    ob = fixture('Loose', loose=True)
    before = independent_snapshot([ob])
    result = run('object.separate', {'object': ob.name, 'mode': 'loose', 'name': 'LooseParts'})
    assert len(result['created']) == 3, result
    assert before == independent_snapshot(pieces(result))
    assert result['preservation']['boundary_vertex_duplicates'] == 0


def stale_and_invalid():
    ob = fixture('Invalid')
    other = fixture('Other')
    before = independent_snapshot([ob])
    selection = run('selection.query', {'objects': [ob.name], 'indices': [0, 1, 3, 4]})
    values = {'object': ob.name, 'name': 'InvalidParts', 'selection_id': selection['selection_id'], 'face_policy': 'all_vertices'}
    reject({**values, 'object': other.name}, 'SELECTION_OBJECT_MISMATCH')
    reject({**values, 'faces': [0]})
    reject({**values, 'mode': 'loose'})
    reject({'object': ob.name, 'name': 'InvalidParts', 'faces': [999]})
    reject({'object': ob.name, 'name': 'InvalidParts', 'faces': [0, 0]})
    reject({'object': ob.name, 'name': 'InvalidParts', 'faces': [0], 'face_policy': 'any_vertex'})
    collision = bpy.data.objects.new('InvalidParts_001', None)
    bpy.context.scene.collection.objects.link(collision)
    reject(values, 'NAME_CONFLICT')
    assert before == independent_snapshot([ob])
    state.selections[selection['selection_id']]['session'] = 'old-session'
    reject(values, 'STALE_SELECTION')
    state.selections[selection['selection_id']]['session'] = state.session
    old_mesh_id = ob.data['bb_mesh_id']
    ob.data['bb_mesh_id'] = 'changed-mesh'
    reject(values, 'STALE_SELECTION')
    ob.data['bb_mesh_id'] = old_mesh_id
    ob.data.vertices.add(1)
    reject(values, 'STALE_SELECTION')
    no_temporary_attributes()


def guarded_sources():
    ob = fixture('Protected')
    before = independent_snapshot([ob])
    run('part.register', {'part_id': 'protected-fixture', 'objects': [ob.name], 'indices': [0, 1]})
    run('part.lock', {'part_id': 'protected-fixture'})
    parts = run('part.inspect', {})
    reject({'object': ob.name, 'name': 'ProtectedCut', 'faces': [0]}, 'PROTECTED_REGION_TOUCHED')
    result = run('object.separate', {'object': ob.name, 'name': 'ProtectedCopy', 'faces': [0], 'keep_original': True})
    assert before == independent_snapshot([ob]) == independent_snapshot(pieces(result))
    assert parts == run('part.inspect', {})
    shared = fixture('Shared')
    linked = bpy.data.objects.new('LinkedShared', shared.data)
    bpy.context.scene.collection.objects.link(linked)
    reject({'object': shared.name, 'name': 'SharedCut', 'faces': [0]}, 'SHARED_MESH')
    shaped = fixture('Shaped')
    shaped.shape_key_add(name='Basis')
    reject({'object': shaped.name, 'name': 'ShapedCut', 'faces': [0]}, 'UNSUPPORTED_DATA')


def full_selection_and_parts():
    count = 20
    vertices = [(x, y, 0) for y in range(count+1) for x in range(count+1)]
    faces = [(y*(count+1)+x, y*(count+1)+x+1, (y+1)*(count+1)+x+1, (y+1)*(count+1)+x)
             for y in range(count) for x in range(count)]
    run('mesh.create', {'name': 'LargeRegion', 'vertices': [list(v) for v in vertices], 'faces': [list(f) for f in faces]})
    run('scene.identify', {'objects': ['LargeRegion']})
    run('part.register', {'part_id': 'large-region', 'objects': ['LargeRegion'], 'indices': [0, 1]})
    selection = run('selection.query', {'objects': ['LargeRegion'], 'box_min': [-1, -1, -1], 'box_max': [10.01, 21, 1]})
    assert selection['count'] == 231 and len(selection['sample_indices']) == 32
    unrelated = run('selection.query', {'objects': ['Region'], 'indices': [0]})
    result = run('object.separate', {'object': 'LargeRegion', 'name': 'GridParts', 'selection_id': selection['selection_id'], 'face_policy': 'all_vertices'})
    assert result['source']['faces'] == result['created'][0]['faces'] == 200
    assert selection['selection_id'] not in state.selections
    assert unrelated['selection_id'] in state.selections
    part = run('part.inspect', {'part_id': 'large-region'})['parts'][0]
    assert part['mapping_status'] == 'stale' and len(part['object_ids']) == 2
    assert json.loads(bpy.context.scene['bb_parts'])['large-region']['mapping_status'] == 'needs_region_reassignment'


def failure_cleanup():
    from blender_bridge.operations_impl import separation
    prior_verify = separation.verify
    for corruption in ('UV', 'Weight', 'Texture'):
        ob = fixture('Partial' + corruption)
        prefix = ob.name + 'Cut'
        selection = run('selection.query', {'objects': [ob.name], 'indices': [0, 1, 3, 4]})
        request = {'operation': 'object.separate', 'args': {'object': ob.name, 'name': prefix, 'faces': [0]},
                   'request_id': str(uuid.uuid4()), 'session': state.session, 'revision': state.revision}
        def corrupt_then_verify(before, objects, *keys):
            part = objects[1]
            if corruption == 'UV':
                part.data.uv_layers[0].data[0].uv.x += .125
            elif corruption == 'Weight':
                part.vertex_groups['Root'].add([0], .99, 'REPLACE')
            else:
                node = next(n for n in part.material_slots[0].material.node_tree.nodes if n.type == 'TEX_IMAGE')
                node.image = bpy.data.images.new('UnexpectedTexture', width=2, height=2)
            return prior_verify(before, objects, *keys)
        separation.verify = corrupt_then_verify
        try:
            state.submit(request)
            state.execute_one(ops.execute, lambda: {})
            result = state.job(request['request_id'])
            assert result['state'] == 'failed' and result['error']['code'] == 'SEPARATION_DATA_CHANGED', result
            assert result['error']['partial_changes_possible']
            created = bpy.data.objects[prefix + '_001']
            assert created['bb_object_id'] != ob['bb_object_id']
            assert created.data['bb_mesh_id'] != ob.data['bb_mesh_id']
            assert selection['selection_id'] not in state.selections
            assert state.submit(request)['state'] == 'failed'  # No replay after unknown/failed outcome.
            no_temporary_attributes()
        finally:
            separation.verify = prior_verify


def add_test_pose(ob):
    from blender_bridge.operations import selected
    rig = next(modifier.object for modifier in ob.modifiers if modifier.type == 'ARMATURE')
    with selected([rig]):
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            root = rig.data.edit_bones.new('Root')
            root.head = (0, 0, 0); root.tail = (0, 0, 1)
            tip = rig.data.edit_bones.new('Tip')
            tip.head = (0, 0, 1); tip.tail = (0, 0, 2); tip.parent = root
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
    rig.pose.bones['Root'].rotation_mode = 'XYZ'
    rig.pose.bones['Root'].rotation_euler.z = .25
    rig.pose.bones['Tip'].location.x = .3
    bpy.context.view_layer.update()


def evaluated_points(objects):
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    points = set()
    for ob in objects:
        evaluated = ob.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            points.update(rounded(evaluated.matrix_world @ v.co) for v in mesh.vertices)
        finally:
            evaluated.to_mesh_clear()
    return sorted(points)


def save_for_readback():
    ob = fixture('Roundtrip')
    add_test_pose(ob)
    expected = independent_snapshot([ob])
    evaluated = evaluated_points([ob])
    assert evaluated != sorted({vertex[0] for vertex in expected['vertices']}), 'Pose did not deform the fixture'
    result = run('object.separate', {'object': ob.name, 'name': 'RoundtripCopy', 'faces': [0], 'keep_original': True})
    candidate = pieces(result)
    assert evaluated_points(candidate) == evaluated
    results.append('armature_pose_preserved')
    print('TEST_PASS armature_pose_preserved', flush=True)
    no_temporary_attributes()
    manifest = {'version': __version__, 'original': ob.name, 'objects': [item.name for item in candidate],
                'expected': expected, 'evaluated_world_points': evaluated, 'blend': str(OUT / 'separation.blend'),
                'preservation': result['preservation'], 'tests': results}
    # This entire factory scene belongs to this test process.
    run('scene.save', {'path': manifest['blend']})
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if args.readback:
    manifest = json.loads(Path(args.readback).read_text(encoding='utf-8'))
    bpy.ops.wm.open_mainfile(filepath=manifest['blend'])
    expected = manifest['expected']
    original = independent_snapshot([bpy.data.objects[manifest['original']]])
    actual = independent_snapshot([bpy.data.objects[name] for name in manifest['objects']])
    # JSON normalizes tuples identically across independent processes.
    assert json.loads(json.dumps(original)) == expected
    assert json.loads(json.dumps(actual)) == expected
    assert json.loads(json.dumps(evaluated_points([bpy.data.objects[name] for name in manifest['objects']]))) == manifest['evaluated_world_points']
    no_temporary_attributes()
    (OUT / 'readback.json').write_text(json.dumps({'state': 'passed', 'version': __version__, 'objects': manifest['objects'], 'blender': bpy.app.version_string}, indent=2), encoding='utf-8')
    print('SEPARATION_READBACK_PASS', flush=True)
else:
    bpy.context.window.scene = bpy.data.scenes.new('OwnedSeparationFixture')
    for name, test in [('exact_faces_ignore_previous_selection', explicit_faces), ('region_copy_preserves_original', region_copy),
                       ('boundary_policies_and_empty_remainder', boundary_policies), ('loose_faces_wires_isolated_vertices', loose_parts),
                       ('stale_selection_and_preflight', stale_and_invalid), ('protected_shared_shape_keys', guarded_sources),
                       ('complete_selection_and_part_mapping', full_selection_and_parts), ('partial_failure_cleanup_and_no_replay', failure_cleanup)]:
        record(name, test)
    manifest = save_for_readback()
    (OUT / 'result.json').write_text(json.dumps({'state': 'passed', 'version': __version__, 'blender': bpy.app.version_string, 'tests': results,
                                               'python_fallback_enabled': state.allow_python, 'manifest': str(OUT / 'manifest.json')}, indent=2), encoding='utf-8')
    print('SEPARATION_FIXTURE_PASS ' + str(OUT / 'manifest.json'), flush=True)
