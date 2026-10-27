"""Bounded main-thread graph edits with private candidates and exact owners."""
import hashlib
import json
import math
import uuid
import bpy
from mathutils import Vector
from ..core import BridgeError
from .common import Base, resolve, node_tree_state


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _socket(node, identifier, output=False):
    sockets = node.outputs if output else node.inputs
    found = [s for s in sockets if s.identifier == identifier]
    if len(found) != 1:
        raise BridgeError('SOCKET_IDENTITY', f'Expected one socket {node.name}.{identifier}; found {len(found)}')
    return found[0]


def _value(value):
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    if hasattr(value, 'to_list'):
        return value.to_list()
    try:
        return list(value)
    except TypeError:
        return {'type': type(value).__name__, 'name': getattr(value, 'name', None)}


def _properties(node):
    result = {}
    for prop in node.bl_rna.properties:
        if prop.is_readonly or prop.identifier in ('name', 'label') or prop.type not in ('BOOLEAN','INT','FLOAT','ENUM'):
            continue
        # Presentation-only fields are not graph computation controls.
        if prop.identifier in ('select','show_options','show_preview','show_texture','hide','width','height'):
            continue
        entry = {'type':prop.type, 'array_length':getattr(prop,'array_length',0), 'value':_value(getattr(node,prop.identifier))}
        if prop.type == 'ENUM':
            entry['enum'] = [item.identifier for item in prop.enum_items]
        elif prop.type in ('INT','FLOAT'):
            entry.update(minimum=prop.hard_min, maximum=prop.hard_max)
        result[prop.identifier] = entry
    return result


def _check_value(prop, value):
    if getattr(prop,'is_array',False):
        if not isinstance(value, list) or len(value) != prop.array_length:
            raise ValueError('Array length does not match live RNA')
        values = value
    else:
        values = [value]
    for item in values:
        if prop.type == 'BOOLEAN' and type(item) is not bool:
            raise ValueError('Boolean value required')
        if prop.type in ('INT','FLOAT'):
            if isinstance(item,bool) or not isinstance(item,(int,float)) or not math.isfinite(item):
                raise ValueError('Finite numeric value required')
            if prop.type == 'INT' and type(item) is not int:
                raise ValueError('Integer value required')
            if not prop.hard_min <= item <= prop.hard_max:
                raise ValueError('Value exceeds live RNA bounds')
        if prop.type == 'ENUM' and item not in {e.identifier for e in prop.enum_items}:
            raise ValueError('Value is not in the live RNA enum')
        if prop.type == 'STRING' and not isinstance(item,str):
            raise ValueError('String value required')
        if prop.type not in ('BOOLEAN','INT','FLOAT','ENUM','STRING'):
            raise ValueError('Pointer/collection socket writes are unsupported')


class NodeGraphOps(Base):
    def _graph_owner(self, owner):
        kind = owner['kind']
        if kind in ('geometry','shader'):
            ob = resolve(owner['object'])
            if ob.library or ob.is_library_indirect:
                raise BridgeError('LINKED_READ_ONLY','Linked object cannot receive a graph candidate')
            if kind == 'geometry':
                binding = ob.modifiers.get(owner['modifier'])
                if binding is None or binding.type != 'NODES' or binding.node_group is None:
                    raise ValueError('Exact Geometry Nodes modifier required')
                root = binding.node_group
            else:
                index = owner['material_slot']
                if index >= len(ob.material_slots):
                    raise ValueError('Material slot outside object')
                binding = ob.material_slots[index]
                if binding.material is None or binding.material.node_tree is None:
                    raise ValueError('Exact node material required')
                root = binding.material.node_tree
        else:
            ob = bpy.data.scenes.get(owner['scene'])
            if ob is None or ob.library:
                raise ValueError('Exact local scene required')
            if not hasattr(ob,'compositing_node_group'):
                raise BridgeError('UNSUPPORTED_CAPABILITY','Atomic compositor binding requires Scene.compositing_node_group')
            binding = ob
            root = ob.compositing_node_group
            if root is None:
                raise ValueError('Scene has no compositor graph')
        tree = root
        for name in owner.get('group_path',[]):
            node = tree.nodes.get(name)
            if node is None or node.type != 'GROUP' or node.node_tree is None:
                raise ValueError('Exact nested group node required: '+name)
            tree = node.node_tree
        return ob, binding, root, tree

    def _graph_token(self, owner, root):
        return _digest({'session':self.state.session,'owner':owner,'identity':root.as_pointer(),'state':node_tree_state(root)})

    def node_graph_inspect(self, owner, nodes=None, limit=64):
        ob, binding, root, tree = self._graph_owner(owner)
        requested = set(nodes or [])
        if requested - set(tree.nodes.keys()):
            raise ValueError('Unknown node names: '+','.join(sorted(requested-set(tree.nodes.keys()))))
        selected = [n for n in tree.nodes if not requested or n.name in requested]
        entries = []
        for node in selected[:limit]:
            sockets = {}
            for key, sequence in (('inputs',node.inputs),('outputs',node.outputs)):
                sockets[key] = [{'identifier':s.identifier,'name':s.name,'type':s.bl_idname,'linked':s.is_linked,
                                 'enabled':s.enabled,'multi_input':s.is_multi_input,
                                 'value':_value(s.default_value) if hasattr(s,'default_value') else None} for s in sequence]
            entries.append({'name':node.name,'type':node.bl_idname,'properties':_properties(node),**sockets})
        names = {n['name'] for n in entries}
        return {'owner':owner,'session':self.state.session,'revision':self.state.revision,
                'graph_token':self._graph_token(owner,root),'root':root.name,'graph':tree.name,'users':tree.users,
                'nodes':entries,'total_nodes':len(selected),'truncated':len(selected)>limit,
                'links':[{'from_node':l.from_node.name,'from_socket':l.from_socket.identifier,'to_node':l.to_node.name,'to_socket':l.to_socket.identifier}
                         for l in tree.links if l.from_node.name in names or l.to_node.name in names]}

    @staticmethod
    def _patch_tree(tree, actions):
        readback = []
        for action in actions:
            operation = action['action']
            if operation == 'add_node':
                if action['node'] in tree.nodes:
                    raise ValueError('Node name already exists')
                if action['node_type'] in ('ShaderNodeScript','CompositorNodeOutputFile'):
                    raise ValueError('External script/file side effects are not supported')
                node = tree.nodes.new(action['node_type']);node.name = action['node']
                if node.name != action['node']:
                    raise ValueError('Node name was not preserved')
                readback.append({'action':operation,'node':node.name,'type':node.bl_idname})
            elif operation in ('set_input','set_property'):
                node = tree.nodes.get(action['node'])
                if node is None:
                    raise ValueError('Exact node not found')
                if operation == 'set_input':
                    target = _socket(node,action['socket']);key = 'default_value'
                    if target.is_linked:
                        raise ValueError('Linked input requires explicit unlink before setting a default')
                    prop = target.bl_rna.properties.get(key)
                    if prop is None or prop.is_readonly:
                        raise ValueError('Socket has no writable default')
                else:
                    key = action['property'];target = node
                    if key not in _properties(node):
                        raise ValueError('Property is not an editable computation field')
                    prop = node.bl_rna.properties[key]
                _check_value(prop,action['value']);setattr(target,key,action['value'])
                readback.append({**action,'value':_value(getattr(target,key))})
            else:
                source = tree.nodes.get(action['from_node']);dest = tree.nodes.get(action['to_node'])
                if source is None or dest is None:
                    raise ValueError('Exact link nodes required')
                output = _socket(source,action['from_socket'],True);input_socket = _socket(dest,action['to_socket'])
                matches = [l for l in tree.links if l.from_socket == output and l.to_socket == input_socket]
                if operation == 'unlink':
                    if len(matches) != 1:
                        raise ValueError('Exact existing link required')
                    tree.links.remove(matches[0])
                else:
                    if matches or (input_socket.is_linked and not input_socket.is_multi_input):
                        raise ValueError('Link already exists or destination needs explicit unlink')
                    link = tree.links.new(output,input_socket,verify_limits=True)
                    if not link.is_valid:
                        raise ValueError('Blender rejected link type or graph cycle')
                readback.append(action)
        tree.update_tag()
        return readback

    @staticmethod
    def _evaluate(kind, owner, root, material=None):
        # Evaluate in an isolated temporary scene; never save or render to a path.
        scene = bpy.data.scenes.new('BridgeGraphEvaluation_'+uuid.uuid4().hex[:8])
        created_objects = [];created_data = []
        try:
            if kind == 'geometry':
                probe = owner.copy();scene.collection.objects.link(probe);created_objects.append(probe)
                return {'state':'evaluated','kind':'geometry','vertices':NodeGraphOps._evaluate_geometry(scene,probe,root)}
            def make_object(name, data):
                ob = bpy.data.objects.new(name,data);scene.collection.objects.link(ob);created_objects.append(ob);created_data.append(data);return ob
            camera = make_object('BridgeGraphCamera',bpy.data.cameras.new('BridgeGraphCamera'))
            camera.location = (0,-4,0);camera.rotation_euler = (Vector((0,0,0))-camera.location).to_track_quat('-Z','Y').to_euler()
            camera.data.type = 'ORTHO';camera.data.ortho_scale = 3;scene.camera = camera
            if kind == 'shader':
                mesh = bpy.data.meshes.new('BridgeGraphSurface');mesh.from_pydata([(-1,0,-1),(1,0,-1),(1,0,1),(-1,0,1)],[],[(0,1,2,3)])
                make_object('BridgeGraphSurface',mesh);mesh.materials.append(material)
                light = make_object('BridgeGraphLight',bpy.data.lights.new('BridgeGraphLight','AREA'));light.location=(0,-2,2);light.data.energy=200
                light.rotation_euler=(Vector((0,0,0))-light.location).to_track_quat('-Z','Y').to_euler()
            else:
                def safe(tree, visited=None):
                    visited = set(visited or ())
                    if tree.as_pointer() in visited:return
                    visited.add(tree.as_pointer())
                    for node in tree.nodes:
                        if node.bl_idname in ('CompositorNodeOutputFile','ShaderNodeScript'):
                            raise ValueError('Graph has external side effects; evaluation refused')
                        if node.type == 'GROUP' and node.node_tree:safe(node.node_tree,visited)
                safe(root);scene.compositing_node_group=root
            scene.render.engine='BLENDER_EEVEE';scene.render.resolution_x=32;scene.render.resolution_y=32;scene.render.resolution_percentage=100
            scene.render.image_settings.file_format='PNG'
            bpy.ops.render.render(scene=scene.name,write_still=False)
            result=bpy.data.images.get('Render Result')
            # Render Result can expose no pixel buffer in headless Blender; completion is separate from image acceptance.
            return {'state':'render_completed','kind':kind,'render_size':[32,32],'pixel_buffer_available':bool(result and len(result.pixels)), 'visual_acceptance':'pending'}
        finally:
            for ob in created_objects:bpy.data.objects.remove(ob,do_unlink=True)
            bpy.data.scenes.remove(scene)
            for data in created_data:
                table = bpy.data.meshes if isinstance(data,bpy.types.Mesh) else bpy.data.cameras if isinstance(data,bpy.types.Camera) else bpy.data.lights
                if data.users == 0:table.remove(data)

    @staticmethod
    def _evaluate_geometry(scene, probe, root):
        # Name carried only by this private candidate; exactly one modifier was selected.
        modifier = probe.modifiers.get(root.get('bb_target_modifier',''))
        if modifier is None:raise ValueError('Evaluation modifier identity lost')
        modifier.node_group=root
        with bpy.context.temp_override(scene=scene,view_layer=scene.view_layers[0]):
            deps=bpy.context.evaluated_depsgraph_get();deps.update();evaluated=probe.evaluated_get(deps);mesh=evaluated.to_mesh()
            try:
                if any(not math.isfinite(c) for v in mesh.vertices for c in v.co):raise ValueError('Non-finite evaluated geometry')
                return len(mesh.vertices)
            finally:evaluated.to_mesh_clear()

    def node_graph_patch(self, owner, graph_token, actions):
        ob,binding,root,tree=self._graph_owner(owner)
        if self._graph_token(owner,root) != graph_token:
            raise BridgeError('STALE_GRAPH','Owner graph or dependencies changed; inspect again')
        kind=owner['kind'];material=None;copies=[];switched=False
        old_material=binding.material if kind=='shader' else None
        old_link=binding.link if kind=='shader' else None
        before=_digest(node_tree_state(root))
        try:
            if kind=='shader':material=old_material.copy();candidate=material.node_tree
            else:candidate=root.copy();copies.append(candidate)
            target=candidate
            for name in owner.get('group_path',[]):
                node=target.nodes[name];node.node_tree=node.node_tree.copy();copies.append(node.node_tree);target=node.node_tree
            readback=self._patch_tree(target,actions)
            if kind=='geometry':candidate['bb_target_modifier']=owner['modifier']
            evaluation=self._evaluate(kind,ob,candidate,material)
            if _digest(node_tree_state(root)) != before:raise ValueError('Protected source graph changed')
            # Recheck token immediately before the only visible binding change.
            if self._graph_token(owner,root) != graph_token:raise ValueError('Source graph changed during evaluation')
            switched=True
            if kind=='geometry':binding.node_group=candidate
            elif kind=='shader':binding.link='OBJECT';binding.material=material
            else:binding.compositing_node_group=candidate
            bpy.context.view_layer.update()
            after=self.node_graph_inspect(owner)
            return {'status':'applied','owner':owner,'copy_on_write':True,'source_preserved':True,'source_hash':before,
                    'applied':readback,'evaluation':evaluation,'graph_token':after['graph_token'],'root':candidate.name,'graph':after['graph']}
        except Exception as exc:
            rollback_error=None
            try:
                if switched:
                    if kind=='geometry':binding.node_group=root
                    elif kind=='shader':binding.material=old_material;binding.link=old_link
                    else:binding.compositing_node_group=root
                if _digest(node_tree_state(root)) != before:raise ValueError('Source graph differs from preflight')
            except Exception as rollback:
                rollback_error=str(rollback)
            if rollback_error is None:
                if material and material.users==0:bpy.data.materials.remove(material)
                for copy in copies:
                    if copy.users==0:bpy.data.node_groups.remove(copy)
            return {'status':'rollback_failed' if rollback_error else 'rolled_back','owner':owner,'applied':[],
                    'error':str(exc),'rollback_error':rollback_error,'source_preserved':rollback_error is None}
