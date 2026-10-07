"""Identity, topology and scoped protection shared by native operations."""
from __future__ import annotations
from array import array
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import uuid
import bpy
import bmesh
from mathutils import Vector
from ..core import BridgeError, atomic_json


def identify(ob, fresh=False):
    if fresh or not ob.get("bb_object_id"):
        ob["bb_object_id"] = str(uuid.uuid4())
    if ob.data and hasattr(ob.data, "get") and (fresh or not ob.data.get("bb_mesh_id")):
        ob.data["bb_mesh_id"] = str(uuid.uuid4())
    return ob


def resolve(identifier, kind=None, writable=False):
    ob = bpy.data.objects.get(identifier)
    if ob is None:
        matches = [o for o in bpy.context.scene.objects if o.get("bb_object_id") == identifier]
        if len(matches) == 1:
            ob = matches[0]
    if ob is None or ob.name not in bpy.context.scene.objects:
        raise BridgeError("OBJECT_NOT_FOUND", f"Object not in active scene: {identifier}")
    if kind and ob.type != kind:
        raise BridgeError("OBJECT_TYPE", f"Expected {kind}: {ob.name}")
    if writable and (ob.library or ob.is_library_indirect or (ob.data and ob.data.library)):
        raise BridgeError("LINKED_READ_ONLY", "Linked library data is read-only")
    if writable and ob.type == "MESH" and ob.data.users != 1:
        raise BridgeError("SHARED_MESH", "Make an explicit independent copy before editing shared mesh data")
    return ob


def topology(mesh):
    h = hashlib.sha256()
    h.update(str((len(mesh.vertices), len(mesh.edges), len(mesh.polygons))).encode())
    for elements, field, size in ((mesh.edges,"vertices",2),(mesh.loops,"vertex_index",1),(mesh.polygons,"loop_total",1)):
        values = array('i', [0]) * (len(elements) * size)
        elements.foreach_get(field, values)
        h.update(values.tobytes())
    return h.hexdigest()


def matrix_values(matrix):
    return [list(row) for row in matrix]


def rna_values(item):
    values={}
    for prop in item.bl_rna.properties:
        key=prop.identifier
        if key in ('rna_type','execution_time','is_active','show_expanded','select') or prop.type=='COLLECTION': continue
        try:
            value=getattr(item,key)
            if prop.type=='POINTER':
                value={'name':value.name,'type':type(value).__name__} if value and hasattr(value,'name') else None
            elif prop.is_array: value=list(value)
            elif isinstance(value,set): value=sorted(value)
            if isinstance(value,(str,int,float,bool,list,dict)) or value is None: values[key]=value
        except (AttributeError,TypeError,ValueError): pass
    return values


def node_tree_state(tree,visited=None):
    if tree is None:return None
    visited=set(visited or ())
    if tree.name in visited:return {'cycle':tree.name}
    visited.add(tree.name);nodes=[]
    for node in tree.nodes:
        entry={'name':node.name,'type':node.bl_idname,'values':rna_values(node),'inputs':[]}
        for socket in node.inputs:
            if not hasattr(socket,'default_value'):continue
            value=socket.default_value
            if isinstance(value,bpy.types.ID):value={'name':value.name}
            elif hasattr(value,'__len__') and not isinstance(value,str):
                try:value=list(value)
                except TypeError:continue
            if isinstance(value,(int,float,str,bool,list,dict)) or value is None:entry['inputs'].append((socket.identifier,value))
        if node.type=='GROUP':entry['group']=node_tree_state(node.node_tree,visited)
        if node.type=='TEX_IMAGE' and node.image:
            img=node.image;path=Path(bpy.path.abspath(img.filepath));record={'path':str(path.resolve()) if img.filepath else None,'colorspace':img.colorspace_settings.name,'size':list(img.size)}
            if img.packed_file:record['sha256']=hashlib.sha256(img.packed_file.data).hexdigest()
            elif path.is_file():
                digest=hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
                record['sha256']=digest.hexdigest()
            elif img.has_data:
                pixels=array('f',[0])*len(img.pixels);img.pixels.foreach_get(pixels);record['sha256']=hashlib.sha256(pixels.tobytes()).hexdigest()
            entry['image']=record
        nodes.append(entry)
    return {'nodes':nodes,'links':[(l.from_node.name,l.from_socket.identifier,l.to_node.name,l.to_socket.identifier) for l in tree.links]}


def material_state(material):
    if not material: return None
    record={'name':material.name,'color':list(material.diffuse_color),'metallic':material.metallic,'roughness':material.roughness}
    if material.use_nodes and material.node_tree:
        record['tree']=node_tree_state(material.node_tree)
    return record


def geometry_node_input(modifier,identifier):
    if hasattr(modifier,'properties'):
        socket=getattr(modifier.properties.inputs,identifier,None)
        return getattr(socket,'value',None)
    return modifier.get(identifier)


def fingerprint(ob, indices=None, _visited=None):
    visited=set(_visited or ())
    if ob.name in visited:return 'dependency-cycle:'+ob.name
    visited.add(ob.name)
    h = hashlib.sha256()
    h.update(json.dumps(matrix_values(ob.matrix_world)).encode())
    h.update(json.dumps({'hide_render':ob.hide_render,'parent':ob.parent.get('bb_object_id',ob.parent.name) if ob.parent else None}).encode())
    if ob.type == "MESH":
        mesh = ob.data
        h.update(topology(mesh).encode())
        vertices = mesh.vertices if indices is None else [mesh.vertices[i] for i in indices]
        for v in vertices:
            h.update(array('d', v.co).tobytes())
            if indices is None:
                h.update(json.dumps([(g.group,g.weight) for g in v.groups]).encode())
        if indices is None:
            for layer in mesh.uv_layers:
                values = array('f', [0]) * (len(layer.data)*2)
                layer.data.foreach_get('uv', values)
                h.update(layer.name.encode()); h.update(values.tobytes())
            h.update(json.dumps([p.material_index for p in mesh.polygons]).encode())
            h.update(json.dumps([material_state(m) for m in mesh.materials],sort_keys=True).encode())
    if ob.type=='ARMATURE':
        h.update(json.dumps([(b.name,list(b.head_local),list(b.tail_local),b.use_deform,b.parent.name if b.parent else None) for b in ob.data.bones]).encode())
        h.update(json.dumps([(b.name,matrix_values(b.matrix_basis)) for b in ob.pose.bones]).encode())
    if ob.type=='CURVE':
        h.update(json.dumps(rna_values(ob.data),sort_keys=True).encode())
        h.update(json.dumps([[(list(p.co),list(p.handle_left),list(p.handle_right)) for p in s.bezier_points] if s.type=='BEZIER' else [list(p.co) for p in s.points] for s in ob.data.splines]).encode())
    if ob.type=='LIGHT':h.update(json.dumps(rna_values(ob.data),sort_keys=True).encode())
    h.update(json.dumps([rna_values(m) for m in ob.modifiers],sort_keys=True).encode())
    for modifier in ob.modifiers:
        for prop in modifier.bl_rna.properties:
            if prop.type=='POINTER':
                value=getattr(modifier,prop.identifier,None)
                if isinstance(value,bpy.types.Object):h.update(fingerprint(value,_visited=visited).encode())
        if modifier.type=='NODES':
            h.update(json.dumps(node_tree_state(modifier.node_group),sort_keys=True).encode())
            keys=[i.identifier for i in modifier.node_group.interface.items_tree if i.item_type=='SOCKET' and i.in_out=='INPUT'] if modifier.node_group else []
            for key in keys:
                value=geometry_node_input(modifier,key)
                if hasattr(value,'to_list'):value=value.to_list()
                elif hasattr(value,'__len__') and not isinstance(value,str):value=list(value)
                elif isinstance(value,bpy.types.ID):value={'name':value.name}
                h.update(json.dumps([key,value],sort_keys=True,default=str).encode())
    return h.hexdigest()


def part_map():
    return json.loads(bpy.context.scene.get("bb_parts", "{}"))


def save_parts(parts):
    bpy.context.scene["bb_parts"] = json.dumps(parts, ensure_ascii=False)


def guarded(ob, indices=None, topology_change=False, extra_parts=()):
    selected = None if indices is None else set(indices)
    for pid, part in part_map().items():
        if not part.get("locked") and pid not in extra_parts:
            continue
        if ob.get("bb_object_id") not in part["object_ids"]:
            continue
        region = part.get("indices")
        if region is not None and (part.get('mapping_status')!='current' or topology(ob.data)!=part.get('topology_revision')):
            raise BridgeError('STALE_SELECTION','Protected part mapping is stale: '+pid)
        if region is None or topology_change or selected is None or set(region) & selected:
            raise BridgeError("PROTECTED_REGION_TOUCHED", f"Operation would touch protected part {pid}")


def protection_snapshot(part_ids=()):
    parts = part_map()
    result = {}
    for pid in part_ids:
        if pid not in parts:
            raise BridgeError("PART_NOT_FOUND", pid)
        part = parts[pid]
        if part.get('mapping_status')!='current':raise BridgeError('STALE_SELECTION','Protected part mapping is stale: '+pid)
        if part.get('indices') is not None:
            ob=resolve(part['object_ids'][0],'MESH')
            if topology(ob.data)!=part.get('topology_revision'):raise BridgeError('STALE_SELECTION','Protected topology changed: '+pid)
        result[pid] = {oid: fingerprint(resolve(oid),part.get("indices")) for oid in part["object_ids"]}
    return result


def verify_protection(before):
    after = protection_snapshot(before)
    if after != before:
        raise BridgeError("PROTECTED_REGION_TOUCHED", "Protected geometry changed; inspect partial effects before continuing")
    return {"state":"passed", "parts":list(before)}


def info(ob):
    from ..operations import object_info
    result = object_info(ob)
    result.update(object_id=ob.get("bb_object_id"), mesh_id=ob.data.get("bb_mesh_id") if ob.data and hasattr(ob.data,"get") else None)
    if ob.type == 'MESH': result['topology_revision'] = topology(ob.data)
    return result


def collection(name=None):
    if name is None: return bpy.context.scene.collection
    col = bpy.data.collections.get(name)
    if not col: raise BridgeError("COLLECTION_NOT_FOUND", name)
    return col


def new_mesh(name, vertices, faces, destination=None):
    if name in bpy.data.objects: raise BridgeError("NAME_CONFLICT", name)
    dest = collection(destination)
    mesh = bpy.data.meshes.new(name + '_Mesh')
    mesh.from_pydata(vertices, [], faces)
    if mesh.validate(verbose=False):
        bpy.data.meshes.remove(mesh)
        raise BridgeError("INVALID_GEOMETRY", "Input mesh required repairs")
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh); bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces)); bm.to_mesh(mesh)
    finally: bm.free()
    mesh.update()
    ob = bpy.data.objects.new(name,mesh); dest.objects.link(ob); identify(ob)
    bpy.context.view_layer.update()
    return ob


@contextmanager
def bm_edit(ob, *, topology_change=True, indices=None):
    guarded(ob,indices,topology_change)
    bm = bmesh.new()
    try:
        bm.from_mesh(ob.data)
        for elems in (bm.verts,bm.edges,bm.faces): elems.ensure_lookup_table()
        yield bm
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(ob.data); ob.data.update()
    finally: bm.free()


def index_check(indices, length):
    if len(set(indices)) != len(indices) or any(type(i) is not int or i < 0 or i >= length for i in indices):
        raise BridgeError("INVALID_SELECTION", f"Distinct indices in 0..{length-1} required")


def load_json(state,path):
    return json.loads(state.input_path(path).read_text(encoding='utf-8-sig'))


def write_json(state,path,data,kind='application/json'):
    out = state.output_path(path,'.json')
    atomic_json(out,data)
    return state.artifact(out,kind)


def snapshot_recipe(ob,operation,args):
    ob['bb_recipe'] = json.dumps({'operation':operation,'args':args,'blender':bpy.app.version_string},ensure_ascii=False)


class Base:
    def __init__(self,state,legacy):
        self.state, self.legacy = state, legacy
        for name in ('selections','bake_plans','preview_metadata'):
            if not hasattr(state,name): setattr(state,name,{})

    def execute(self,name,args):
        return getattr(self,name.replace('.','_'))(**args)
