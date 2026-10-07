"""All functions in this module run on Blender's main thread."""
from contextlib import contextmanager
import io
import contextlib
import math
import bpy
import bmesh
from mathutils import Vector
from .core import BridgeError


def target(name, kind=None):
    from .operations_impl.common import resolve
    return resolve(name,kind)


def unique(name, table):
    if name in table:
        raise ValueError(f"Name already exists: {name}")


def writable_mesh(name):
    ob = target(name, "MESH")
    if ob.data.users != 1 or ob.data.library:
        raise ValueError("Mesh has shared or linked data; make an explicit independent copy first")
    return ob


def object_info(ob):
    data = {"name": ob.name, "type": ob.type, "location": list(ob.location),
            "rotation": list(ob.rotation_euler), "scale": list(ob.scale),
            "dimensions": list(ob.dimensions), "selected": ob.select_get(),
            "bounds_world": [list(ob.matrix_world @ Vector(v)) for v in ob.bound_box],
            "modifiers": [{"name": m.name, "type": m.type} for m in ob.modifiers],
            "materials": [s.material.name if s.material else None for s in ob.material_slots]}
    if ob.type == "MESH":
        ob.data.calc_loop_triangles()
        data.update(vertices=len(ob.data.vertices), edges=len(ob.data.edges), faces=len(ob.data.polygons),
                    triangles=len(ob.data.loop_triangles), uv_layers=[u.name for u in ob.data.uv_layers])
        rigs=[m.object for m in ob.modifiers if m.type=='ARMATURE' and m.object]
        if ob.vertex_groups or rigs:
            names={b.name for rig in rigs for b in rig.data.bones if b.use_deform}
            sums = [sum(g.weight for g in v.groups if ob.vertex_groups[g.group].name in names) for v in ob.data.vertices]
            data["weights"] = {"unweighted": sum(w <= 1e-7 for w in sums),
                               "non_normalized": sum(w>1e-7 and abs(w - 1) > 1e-4 for w in sums),
                               "scope":"deform_bones_only", "armature_present":bool(rigs)}
    if ob.type == "ARMATURE":
        data["bones"] = [{"name": b.name, "parent": b.parent.name if b.parent else None,
                          "head": list(b.head_local), "tail": list(b.tail_local)} for b in ob.data.bones]
    return data


def snapshot():
    scene = bpy.context.scene
    return {"blender_version": bpy.app.version_string, "background": bpy.app.background,
            "filepath": bpy.data.filepath, "dirty": bpy.data.is_dirty, "scene": scene.name,
            "object_count": len(scene.objects), "frame": scene.frame_current,
            "frame_range": [scene.frame_start,scene.frame_end], "fps": scene.render.fps/scene.render.fps_base,
            "mode": bpy.context.mode, "units": scene.unit_settings.system,
            "scale_length": scene.unit_settings.scale_length}


def checked_indices(indices, count):
    if len(set(indices)) != len(indices) or any(i < 0 or i >= count for i in indices):
        raise ValueError(f"Indices must be distinct and within 0..{count - 1}")


@contextmanager
def selected(objects):
    if bpy.context.mode != "OBJECT":
        raise ValueError("Object mode required; preserve the user's active edit/sculpt operation")
    old = list(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    try:
        for ob in old:
            ob.select_set(False)
        for ob in objects:
            ob.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]
        yield
    finally:
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for ob in bpy.context.selected_objects:
            ob.select_set(False)
        for ob in old:
            try:
                if ob.name in bpy.context.view_layer.objects: ob.select_set(True)
            except ReferenceError: pass
        try:
            bpy.context.view_layer.objects.active = active if active and active.name in bpy.context.view_layer.objects else None
        except ReferenceError: bpy.context.view_layer.objects.active=None


def link(ob, collection=None):
    dest = bpy.data.collections.get(collection) if collection else bpy.context.scene.collection
    if not dest:
        raise ValueError(f"Collection not found: {collection}")
    dest.objects.link(ob)


def point_at(ob, location):
    direction = Vector(location) - ob.location
    if direction.length < 1e-6:
        raise ValueError("Target and location must differ")
    ob.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


class Operations:
    def __init__(self, state):
        self.state = state
        from .operations_impl import NativeOperations
        self.native=NativeOperations(state,self)

    def execute(self, name, args):
        if bpy.context.mode != "OBJECT" and name not in ("scene.inspect", "object.inspect"):
            raise ValueError("Object mode required; leave the current user edit operation intact")
        from .catalog import OPS
        from .operations_impl.common import guarded,resolve,identify
        method=name.replace('.','_')
        before=set(bpy.data.objects)
        try:
            if hasattr(self.native,method):result=getattr(self.native,method)(**args)
            else:
                if OPS[name]['mutates_scene']:
                    if 'object' in args:guarded(resolve(args['object'],writable=True),args.get('indices'),name=='mesh.edit')
                    for object_name in args.get('objects',[]):guarded(resolve(object_name))
                result=getattr(self,method)(**args)
            bpy.context.view_layer.update()
            created=set(bpy.data.objects)-before
            for ob in created:identify(ob)
            if isinstance(result,dict) and result.get('type') and result.get('name') in {o.name for o in created}:
                from .operations_impl.common import info
                result.update(info(bpy.data.objects[result['name']]))
            return result
        finally:
            for ob in set(bpy.data.objects)-before:identify(ob)

    def scene_inspect(self, offset=0, limit=100):
        objects = sorted(bpy.context.scene.objects, key=lambda o: o.name)
        return {**snapshot(), "objects": [{"name": o.name, "type": o.type} for o in objects[offset:offset+limit]],
                "total": len(objects), "next_offset": offset + limit if offset + limit < len(objects) else None,
                "collections": [c.name for c in bpy.data.collections],
                "selection": [o.name for o in bpy.context.selected_objects]}

    def object_inspect(self, object):
        return object_info(target(object))

    def mesh_inspect(self, object, offset=0, limit=200):
        ob = target(object, "MESH")
        mesh = ob.data
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            health = {"zero_area_faces": sum(f.calc_area() <= 1e-12 for f in bm.faces),
                      "boundary_edges": sum(e.is_boundary for e in bm.edges),
                      "non_manifold_edges": sum(not e.is_manifold for e in bm.edges),
                      "loose_vertices": sum(not v.link_edges for v in bm.verts)}
        finally:
            bm.free()
        return {**object_info(ob), "health": health, "offset": offset,
                "vertex_data": [{"index": v.index, "co": list(v.co)} for v in mesh.vertices[offset:offset+limit]],
                "edge_data": [{"index": e.index, "vertices": list(e.vertices)} for e in mesh.edges[offset:offset+limit]],
                "face_data": [{"index": p.index, "vertices": list(p.vertices), "normal": list(p.normal)} for p in mesh.polygons[offset:offset+limit]]}

    def collection_create(self, name):
        unique(name, bpy.data.collections)
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
        return {"name": col.name}

    def mesh_create(self, name, vertices, faces, collection=None):
        unique(name, bpy.data.objects)
        if collection and not bpy.data.collections.get(collection):
            raise ValueError("Collection does not exist")
        for face in faces:
            checked_indices(face, len(vertices))
        mesh = bpy.data.meshes.new(name + "_Mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        ob = bpy.data.objects.new(name, mesh)
        link(ob, collection)
        return object_info(ob)

    def mesh_primitive(self, name, kind, location=(0,0,0), scale=(1,1,1), segments=32, collection=None):
        unique(name, bpy.data.objects)
        if collection and not bpy.data.collections.get(collection):
            raise ValueError("Collection does not exist")
        mesh = bpy.data.meshes.new(name + "_Mesh")
        bm = bmesh.new()
        try:
            if kind == "cube":
                bmesh.ops.create_cube(bm, size=2)
            elif kind in ("cylinder", "cone"):
                bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                                     radius1=1, radius2=1 if kind == "cylinder" else 0, depth=2)
            else:
                bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=max(3, segments//2), radius=1)
            bm.to_mesh(mesh)
        finally:
            bm.free()
        ob = bpy.data.objects.new(name, mesh)
        link(ob, collection)
        ob.location, ob.scale = location, scale
        bpy.context.view_layer.update()
        return object_info(ob)

    def object_transform(self, object, location=None, rotation=None, scale=None, apply=False):
        ob = target(object)
        if apply and ob.type == "MESH":
            writable_mesh(object)
        if location is not None: ob.location = location
        if rotation is not None:
            ob.rotation_mode = 'XYZ'
            ob.rotation_euler = rotation
        if scale is not None: ob.scale = scale
        if apply:
            with selected([ob]):
                bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        bpy.context.view_layer.update()
        return object_info(ob)

    def object_select(self, objects):
        targets = [target(n) for n in objects]
        for ob in bpy.context.selected_objects: ob.select_set(False)
        for ob in targets: ob.select_set(True)
        bpy.context.view_layer.objects.active = targets[0]
        return {"selection": objects, "active": objects[0]}

    def mesh_vertices(self, object, indices, delta=None, positions=None):
        ob = writable_mesh(object)
        checked_indices(indices, len(ob.data.vertices))
        if (delta is None) == (positions is None):
            raise ValueError("Specify exactly one of delta or positions")
        if positions is not None and len(positions) != len(indices):
            raise ValueError("positions must match indices count")
        for n, index in enumerate(indices):
            v = ob.data.vertices[index]
            v.co = positions[n] if positions is not None else v.co + Vector(delta)
        ob.data.update()
        return {"object": ob.name, "edited_vertices": len(indices)}

    def mesh_edit(self, object, action, indices=None, offset=(0,0,0), amount=0.05, segments=1):
        ob = writable_mesh(object)
        bm = bmesh.new()
        try:
            bm.from_mesh(ob.data)
            bm.faces.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            if action != "recalc_normals" and not indices:
                raise ValueError("Explicit face/edge indices required")
            elems = bm.faces if action.endswith("faces") else bm.edges
            if indices:
                checked_indices(indices, len(elems))
            chosen = [elems[i] for i in indices] if indices else []
            if action == "extrude_faces":
                region_edges = list({edge for face in chosen for edge in face.edges})
                region_verts = list({vertex for face in chosen for vertex in face.verts})
                result = bmesh.ops.extrude_face_region(bm, geom=chosen + region_edges, use_keep_orig=False)
                verts = [g for g in result["geom"] if isinstance(g, bmesh.types.BMVert)]
                bmesh.ops.translate(bm, verts=verts, vec=Vector(offset))
                # Retain boundary connections but never duplicate source caps.
                caps = [f for f in chosen if f.is_valid]
                if caps: bmesh.ops.delete(bm, geom=caps, context='FACES_ONLY')
                orphan_edges = [e for e in region_edges if e.is_valid and not e.link_faces]
                if orphan_edges: bmesh.ops.delete(bm, geom=orphan_edges, context='EDGES')
                orphan_verts = [v for v in region_verts if v.is_valid and not v.link_edges]
                if orphan_verts: bmesh.ops.delete(bm, geom=orphan_verts, context='VERTS')
            elif action == "inset_faces":
                bmesh.ops.inset_region(bm, faces=chosen, thickness=amount, depth=offset[2], use_even_offset=True)
            elif action == "bevel_edges":
                bmesh.ops.bevel(bm, geom=chosen, offset=amount, segments=segments, affect='EDGES')
            elif action == "subdivide_edges":
                bmesh.ops.subdivide_edges(bm, edges=chosen, cuts=segments, use_grid_fill=True)
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            bm.to_mesh(ob.data)
            ob.data.update()
        finally:
            bm.free()
        return object_info(ob)

    def modifier_add(self, object, name, kind, **values):
        ob = target(object, "MESH")
        unique(name, ob.modifiers)
        allowed = {"BEVEL": {"width", "segments"}, "MIRROR": set(), "SOLIDIFY": {"thickness"},
                   "SUBSURF": {"levels"}, "BOOLEAN": {"operand", "operation"}, "WEIGHTED_NORMAL": set()}
        if set(values) - allowed[kind]:
            raise ValueError("Properties do not apply to this modifier type")
        operand = target(values["operand"], "MESH") if "operand" in values else None
        if kind == "BOOLEAN" and (not operand or operand == ob):
            raise ValueError("Boolean requires a different operand mesh")
        mod = ob.modifiers.new(name, kind)
        for key, value in values.items():
            setattr(mod, "object" if key == "operand" else key, operand if key == "operand" else value)
        return object_info(ob)

    def modifier_apply(self, object, name):
        ob = writable_mesh(object)
        if name not in ob.modifiers: raise ValueError("Modifier does not exist")
        with selected([ob]):
            bpy.ops.object.modifier_apply(modifier=name)
        return object_info(ob)

    def material_create(self, name, color=(0.38,0.4,0.44,1), metallic=0, roughness=0.45,
                        base_color_image=None, normal_image=None, roughness_image=None):
        unique(name, bpy.data.materials)
        paths = {k: self.state.input_path(p) for k, p in {"Base Color": base_color_image,
                 "Normal": normal_image, "Roughness": roughness_image}.items() if p}
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        mat.diffuse_color = color
        mat.metallic, mat.roughness = metallic, roughness
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs['Base Color'].default_value = color
        bsdf.inputs['Metallic'].default_value = metallic
        bsdf.inputs['Roughness'].default_value = roughness
        for channel, path in paths.items():
            node = mat.node_tree.nodes.new('ShaderNodeTexImage')
            node.image = bpy.data.images.load(str(path), check_existing=False)
            if channel != 'Base Color': node.image.colorspace_settings.name = 'Non-Color'
            if channel == 'Normal':
                normal = mat.node_tree.nodes.new('ShaderNodeNormalMap')
                mat.node_tree.links.new(node.outputs['Color'], normal.inputs['Color'])
                mat.node_tree.links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
            else:
                mat.node_tree.links.new(node.outputs['Color'], bsdf.inputs[channel])
            node.image.pack()
        return {"material": mat.name, "texture_channels": list(paths)}

    def material_assign(self, object, material, faces=None):
        ob = writable_mesh(object)
        mat = bpy.data.materials.get(material)
        if not mat: raise ValueError("Material does not exist")
        if faces is not None: checked_indices(faces, len(ob.data.polygons))
        slot = next((i for i, m in enumerate(ob.data.materials) if m == mat), None)
        if slot is None:
            ob.data.materials.append(mat)
            slot = len(ob.data.materials) - 1
        for index in faces if faces is not None else range(len(ob.data.polygons)):
            ob.data.polygons[index].material_index = slot
        return object_info(ob)

    def uv_unwrap(self, object):
        ob = writable_mesh(object)
        with selected([ob]):
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.03)
            bpy.ops.object.mode_set(mode='OBJECT')
        return object_info(ob)

    def reference_add(self, name, path, location=(0,0,0), rotation=(0,0,0), size=4):
        unique(name, bpy.data.objects)
        path = self.state.input_path(path)
        image = bpy.data.images.load(str(path), check_existing=True)
        ob = bpy.data.objects.new(name, None)
        ob.empty_display_type = 'IMAGE'
        ob.data = image
        ob.empty_display_size = size
        ob.empty_image_depth = 'BACK'
        ob.location, ob.rotation_euler = location, rotation
        link(ob)
        return {"name": ob.name, "image": str(path)}

    def camera_create(self, name, location, target, orthographic_scale=None, lens=50):
        unique(name, bpy.data.objects)
        if (Vector(target) - Vector(location)).length < 1e-6: raise ValueError("Camera target equals location")
        data = bpy.data.cameras.new(name)
        if orthographic_scale is not None:
            if orthographic_scale <= 0: raise ValueError("Scale must be positive")
            data.type, data.ortho_scale = 'ORTHO', orthographic_scale
        data.lens = lens
        ob = bpy.data.objects.new(name, data)
        link(ob)
        ob.location = location
        point_at(ob, target)
        return object_info(ob)

    def light_create(self, name, location, target, energy=1000, size=5):
        unique(name, bpy.data.objects)
        if (Vector(target) - Vector(location)).length < 1e-6: raise ValueError("Light target equals location")
        data = bpy.data.lights.new(name, 'AREA')
        data.energy, data.shape, data.size = energy, 'DISK', size
        ob = bpy.data.objects.new(name, data)
        link(ob)
        ob.location = location
        point_at(ob, target)
        return object_info(ob)

    @contextmanager
    def render_settings(self, path, camera=None, width=960, height=540, style=None):
        scene = bpy.context.scene
        r = scene.render
        attrs = ['filepath', 'resolution_x', 'resolution_y', 'resolution_percentage', 'engine', 'film_transparent']
        saved = {k: getattr(r, k) for k in attrs}
        old_camera, fmt = scene.camera, r.image_settings.file_format
        shade = scene.display.shading
        shade_keys = ['light', 'color_type', 'single_color', 'show_shadows', 'show_cavity', 'background_type', 'background_color']
        shade_saved = {k: tuple(getattr(shade,k)) if k.endswith('color') else getattr(shade,k) for k in shade_keys}
        try:
            r.filepath, r.resolution_x, r.resolution_y, r.resolution_percentage = str(path), width, height, 100
            r.image_settings.file_format = 'PNG'
            r.film_transparent = False
            if camera: scene.camera = camera
            if style:
                engines = {e.identifier for e in r.bl_rna.properties['engine'].enum_items}
                eevee = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
                r.engine = 'BLENDER_WORKBENCH' if style == 'clay' else 'CYCLES' if bpy.app.background else eevee
                # Material previews in background use CPU Cycles to avoid headless graphics context limitations.
                if style == 'clay':
                    shade.light, shade.color_type = 'STUDIO', 'SINGLE'
                    shade.single_color = (0.55, 0.57, 0.62)
                    shade.show_shadows, shade.show_cavity = True, True
                    shade.background_type, shade.background_color = 'WORLD', (0.06,0.06,0.06)
            yield
        finally:
            for k,v in saved.items(): setattr(r,k,v)
            for k,v in shade_saved.items(): setattr(shade,k,v)
            scene.camera, r.image_settings.file_format = old_camera, fmt

    def preview_render(self, camera, path, width=960, height=540, style='clay', overwrite=False, objects=None):
        cam = target(camera, "CAMERA")
        subject = [target(n) for n in objects] if objects else None
        output = self.state.output_path(path, '.png', overwrite)
        scene = bpy.context.scene
        samples = scene.cycles.samples
        visibility = {ob:ob.hide_render for ob in scene.objects if ob.type in ('MESH','CURVE','SURFACE','META','FONT','VOLUME')}
        try:
            if subject:
                for ob in visibility: ob.hide_render = ob not in subject
            scene.cycles.samples = 24
            with self.render_settings(output, cam, width, height, style):
                bpy.ops.render.render(write_still=True)
        finally:
            scene.cycles.samples = samples
            for ob,value in visibility.items(): ob.hide_render = value
        return self.state.artifact(output, 'image/png')

    def preview_viewport(self, path, overwrite=False):
        if bpy.app.background: raise ValueError("Viewport capture requires an interactive Blender window")
        window = bpy.context.window
        area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None) if window else None
        if not area: raise ValueError("No VIEW_3D area is available")
        region = next(r for r in area.regions if r.type == 'WINDOW')
        output = self.state.output_path(path, '.png', overwrite)
        with self.render_settings(output):
            with bpy.context.temp_override(window=window, area=area, region=region):
                bpy.ops.render.opengl(write_still=True, view_context=True)
        return self.state.artifact(output, 'image/png')

    def scene_save(self, path, copy=True, overwrite=False):
        output = self.state.output_path(path, '.blend', overwrite)
        bpy.ops.wm.save_as_mainfile(filepath=str(output), copy=copy, compress=True, check_existing=False)
        return self.state.artifact(output, 'application/x-blender')

    def export_fbx(self, objects, path, animation=False, overwrite=False, frame_start=None, frame_end=None):
        obs = [target(n) for n in objects]
        if any(ob.type not in ('MESH', 'ARMATURE', 'EMPTY') for ob in obs):
            raise ValueError("Only explicit mesh/armature/empty objects are exportable")
        if (frame_start is None) != (frame_end is None) or (frame_start is not None and (not animation or frame_start > frame_end)):
            raise ValueError('An explicit range requires animation=true and frame_start <= frame_end')
        output = self.state.output_path(path, '.fbx', overwrite)
        scene = bpy.context.scene
        old_range = (scene.frame_start,scene.frame_end,scene.frame_current)
        try:
            if frame_start is not None:
                scene.frame_start,scene.frame_end = frame_start,frame_end
            with selected(obs):
                bpy.ops.export_scene.fbx(filepath=str(output), use_selection=True, object_types={'MESH','ARMATURE','EMPTY'},
                    apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Y', axis_up='Z',
                    add_leaf_bones=False, bake_anim=animation, bake_anim_use_nla_strips=False,
                    bake_anim_use_all_actions=False, path_mode='AUTO')
        finally:
            scene.frame_start,scene.frame_end = old_range[:2]
            scene.frame_set(old_range[2])
        return self.state.artifact(output, 'model/fbx')

    def rig_create(self, name, bones):
        unique(name, bpy.data.objects)
        seen = set()
        for b in bones:
            if b['name'] in seen or (b.get('parent') and b['parent'] not in seen): raise ValueError("Duplicate bone or parent order invalid")
            if (Vector(b['tail']) - Vector(b['head'])).length < 1e-6: raise ValueError("Zero-length bone")
            seen.add(b['name'])
        data = bpy.data.armatures.new(name + '_Data')
        ob = bpy.data.objects.new(name, data)
        link(ob)
        with selected([ob]):
            bpy.ops.object.mode_set(mode='EDIT')
            try:
                for b in bones:
                    bone = data.edit_bones.new(b['name'])
                    bone.head, bone.tail = b['head'], b['tail']
                    if b.get('parent'): bone.parent = data.edit_bones[b['parent']]
            finally:
                if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        return object_info(ob)

    def rig_bind(self, object, armature, weights):
        ob, rig = writable_mesh(object), target(armature, 'ARMATURE')
        if any(m.type == 'ARMATURE' for m in ob.modifiers): raise ValueError("Mesh already has an armature modifier")
        if ob.vertex_groups: raise ValueError("Existing groups retained; bind requires a fresh mesh with no groups")
        for w in weights:
            if w['bone'] not in rig.data.bones: raise ValueError("Unknown bone")
            checked_indices(w['indices'], len(ob.data.vertices))
        for w in weights:
            group = ob.vertex_groups.get(w['bone']) or ob.vertex_groups.new(name=w['bone'])
            group.add(w['indices'], w['weight'], 'REPLACE')
        mod = ob.modifiers.new('BridgeArmature', 'ARMATURE')
        mod.object = rig
        return object_info(ob)

    def animation_keyframe(self, object, frame, bone=None, location=None, rotation=None, scale=None):
        ob = target(object)
        item = ob.pose.bones.get(bone) if bone and ob.type == 'ARMATURE' else ob if not bone else None
        if item is None: raise ValueError("Pose bone not found")
        if all(v is None for v in (location, rotation, scale)): raise ValueError("At least one channel required")
        for key, value in {'location':location, 'rotation_euler':rotation, 'scale':scale}.items():
            if value is not None:
                if key == 'rotation_euler': item.rotation_mode = 'XYZ'
                setattr(item, key, value)
                item.keyframe_insert(data_path=key, frame=frame)
        return {"object": object, "bone": bone, "frame": frame}

    def animation_frame(self, frame):
        bpy.context.scene.frame_set(frame)
        return snapshot()

    def python_execute(self, code):
        if not self.state.allow_python: raise BridgeError("PYTHON_DISABLED", "Disabled")
        stream = io.StringIO()
        namespace = {"bpy": bpy, "bmesh": bmesh, "result": None}
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            exec(compile(code, '<trusted BlenderBridge>', 'exec'), namespace)
        return {"result": namespace.get('result'), "output": stream.getvalue()[-16000:], "trusted_unrestricted": True}
