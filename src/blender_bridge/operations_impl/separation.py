"""Base-mesh preservation checks for native separation; main thread only.

Temporary original-index attributes distinguish coincident geometry and are removed
from every affected mesh even on partial failure. No coordinates or UVs are rebuilt.
"""
from collections import Counter
import hashlib
import json
from ..core import BridgeError


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).digest()


def vertex_record(ob, vertex):
    return digest((list(vertex.co), sorted((ob.vertex_groups[g.group].name, g.weight) for g in vertex.groups)))


def face_record(ob, face, original_vertices=None):
    mesh = ob.data
    corners = []
    for loop_index in face.loop_indices:
        vertex = mesh.loops[loop_index].vertex_index
        if original_vertices is not None:
            vertex = original_vertices[vertex]
        corners.append((vertex, [list(layer.data[loop_index].uv) for layer in mesh.uv_layers]))
    # Blender may rotate the starting corner, but must preserve winding and UV seams.
    start = min(range(len(corners)), key=lambda i: corners[i][0])
    return digest((face.material_index, face.use_smooth, corners[start:] + corners[:start]))


def texture_references(material):
    result = []
    def visit(tree, path, ancestors):
        if tree is None or tree.as_pointer() in ancestors:
            return
        ancestors = ancestors | {tree.as_pointer()}
        for node in tree.nodes:
            node_path = path + (node.name,)
            image = getattr(node, 'image', None)
            if image:
                result.append((node_path, image.as_pointer(), image.filepath, image.colorspace_settings.name))
            if node.type == 'GROUP':
                visit(node.node_tree, node_path, ancestors)
    if material:
        visit(material.node_tree, (), set())
    return result


def metadata(ob):
    mesh = ob.data
    return {
        'matrix_world': [list(row) for row in ob.matrix_world],
        'parent': ob.parent.as_pointer() if ob.parent else None,
        'materials': [(slot.link, slot.material.as_pointer() if slot.material else None) for slot in ob.material_slots],
        'data_materials': [m.as_pointer() if m else None for m in mesh.materials],
        'texture_references': [(m.as_pointer(), texture_references(m)) for m in
                               dict.fromkeys([*mesh.materials, *(s.material for s in ob.material_slots)]) if m],
        'groups': [group.name for group in ob.vertex_groups],
        'uv_layers': [(layer.name, layer.active_render) for layer in mesh.uv_layers],
        'active_uv': mesh.uv_layers.active_index,
        'armatures': [(m.name, m.object.as_pointer() if m.object else None, m.use_vertex_groups,
                       m.use_bone_envelopes, m.use_deform_preserve_volume) for m in ob.modifiers if m.type == 'ARMATURE'],
    }


def capture(ob):
    return {
        'metadata': metadata(ob),
        'data_materials': tuple(ob.data.materials),
        'slot_bindings': tuple((slot.link, slot.material) for slot in ob.material_slots),
        'vertices': [vertex_record(ob, v) for v in ob.data.vertices],
        'faces': [face_record(ob, p) for p in ob.data.polygons],
        'edges': {tuple(sorted(e.vertices)) for e in ob.data.edges},
    }


def preserve_material_slots(before, objects):
    # Native Separate converts OBJECT links to DATA on new objects in Blender 5.2.
    for ob in objects:
        if len(ob.material_slots) != len(before['slot_bindings']):
            raise BridgeError('SEPARATION_DATA_CHANGED', 'Material slot count changed')
        for i, (link, material) in enumerate(before['slot_bindings']):
            ob.data.materials[i] = before['data_materials'][i]
            ob.material_slots[i].link = link
            ob.material_slots[i].material = material


def add_indices(mesh, vertex_key, face_key):
    for name, domain, count in ((vertex_key, 'POINT', len(mesh.vertices)), (face_key, 'FACE', len(mesh.polygons))):
        attribute = mesh.attributes.new(name, 'INT', domain)
        if attribute.name != name:
            raise BridgeError('NAME_CONFLICT', 'Temporary separation attribute name changed')
        attribute.data.foreach_set('value', list(range(count)))


def remove_indices(objects, keys):
    for ob in objects:
        for key in keys:
            attribute = ob.data.attributes.get(key)
            if attribute:
                ob.data.attributes.remove(attribute)


def verify(before, objects, vertex_key, face_key):
    seen_vertices = set()
    seen_faces = Counter()
    seen_edges = set()
    total_vertices = 0
    partitions = []
    for ob in objects:
        mesh = ob.data
        current_metadata = metadata(ob)
        changed = [key for key in current_metadata if current_metadata[key] != before['metadata'][key]]
        if changed:
            raise BridgeError('SEPARATION_DATA_CHANGED', f'Metadata changed on {ob.name}: {changed}')
        vertex_attribute = mesh.attributes.get(vertex_key)
        face_attribute = mesh.attributes.get(face_key)
        # Empty remainders can have no attribute layers after separating every face.
        if (len(mesh.vertices) and vertex_attribute is None) or (len(mesh.polygons) and face_attribute is None):
            raise BridgeError('SEPARATION_DATA_CHANGED', 'Original-index mapping missing')
        mapping = [item.value for item in vertex_attribute.data] if vertex_attribute else []
        if len(mapping) != len(mesh.vertices) or len(set(mapping)) != len(mapping):
            raise BridgeError('SEPARATION_DATA_CHANGED', 'Vertex mapping is incomplete or duplicated within a piece')
        for vertex, original in zip(mesh.vertices, mapping):
            if not 0 <= original < len(before['vertices']) or vertex_record(ob, vertex) != before['vertices'][original]:
                raise BridgeError('SEPARATION_DATA_CHANGED', f'Position or vertex weights changed: {ob.name}')
            seen_vertices.add(original)
        face_ids = [item.value for item in face_attribute.data] if face_attribute else []
        if len(face_ids) != len(mesh.polygons):
            raise BridgeError('SEPARATION_DATA_CHANGED', 'Face mapping is incomplete')
        for face, original in zip(mesh.polygons, face_ids):
            if not 0 <= original < len(before['faces']) or face_record(ob, face, mapping) != before['faces'][original]:
                raise BridgeError('SEPARATION_DATA_CHANGED', f'Face, UV or material assignment changed: {ob.name}')
            seen_faces[original] += 1
        seen_edges.update(tuple(sorted(mapping[i] for i in edge.vertices)) for edge in mesh.edges)
        total_vertices += len(mesh.vertices)
        partitions.append({'object': ob.name, 'faces': len(face_ids), 'source_face_sample': sorted(face_ids)[:32]})
    if seen_vertices != set(range(len(before['vertices']))) or seen_faces != Counter(range(len(before['faces']))) or seen_edges != before['edges']:
        raise BridgeError('SEPARATION_DATA_CHANGED', 'Geometry was lost, duplicated or added during separation')
    return {
        'state': 'passed',
        'checks': ['base_vertex_positions', 'face_winding', 'face_material_assignments', 'uv_layers_and_coordinates',
                   'material_and_texture_references', 'vertex_group_weights', 'armature_bindings',
                   'world_transform', 'source_geometry_coverage'],
        'source_vertices': len(before['vertices']), 'source_faces': len(before['faces']),
        'boundary_vertex_duplicates': total_vertices - len(before['vertices']), 'partitions': partitions,
        'not_checked': ['evaluated_modifier_result', 'shading_normals', 'other_custom_attributes', 'artistic_acceptance'],
    }


def component_count(mesh):
    parent = list(range(len(mesh.vertices)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for edge in mesh.edges:
        a, b = edge.vertices
        parent[root(a)] = root(b)
    return len({root(i) for i in range(len(parent))})
