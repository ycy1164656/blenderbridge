"""Single operation contract used by runtime, CLI, MCP and documentation."""
import math


def obj(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def arr(items, minimum=0, maximum=100000):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


def enum(*values):
    return {"type": "string", "enum": list(values)}


S = {"type": "string", "minLength": 1, "maxLength": 4096}
N = {"type": "number"}
I = {"type": "integer", "minimum": 0}
B = {"type": "boolean"}
V = arr(N, 3, 3)
IDS = arr(S, 1, 1000)
INDICES = arr(I, 1, 100000)
OPS = {}


def op(name, description, props=None, required=(), write=False, *, domain="blender_main_thread",
       artifacts=False, long_running=False, gui=False, gpu=False, cancellation="queued_only"):
    scene = domain == "blender_main_thread"
    OPS[name] = {"name": name, "description": description, "mutates": bool(write and scene),
                 "mutates_scene": bool(write and scene), "writes_artifacts": artifacts,
                 "execution_domain": domain, "long_running": long_running,
                 "requires_gui": gui, "requires_gpu": gpu, "cancellation": cancellation,
                 "requires_session": scene, "requires_revision": scene and (write or artifacts),
                 "inputSchema": obj(props or {}, required)}


op("scene.inspect", "Read scene, objects, units, selection and dirty state.",
   {"offset": I, "limit": {"type": "integer", "minimum": 1, "maximum": 500}})
op("object.inspect", "Read object transform, bounds, topology, modifiers and materials.", {"object": S}, ["object"])
op("mesh.inspect", "Read bounded local-space vertex/edge/face arrays and topology health; indices change after topology edits.",
   {"object": S, "offset": I, "limit": {"type": "integer", "minimum": 1, "maximum": 2000}}, ["object"])
op("collection.create", "Create a named collection without replacing existing data.", {"name": S}, ["name"], True)
op("mesh.create", "Create a mesh from explicit vertices and polygon faces in meters.",
   {"name": S, "vertices": arr(V, 3), "faces": arr(arr(I, 3, 10000), 1), "collection": S}, ["name", "vertices", "faces"], True)
op("mesh.primitive", "Create a cube, cylinder, UV sphere or cone as a starting form.",
   {"name": S, "kind": enum("cube", "cylinder", "sphere", "cone"), "location": V, "scale": V,
    "segments": {"type": "integer", "minimum": 3, "maximum": 256}, "collection": S}, ["name", "kind"], True)
op("object.transform", "Set local transform; rotation is XYZ radians. Optional apply preserves geometry in world space.",
   {"object": S, "location": V, "rotation": V, "scale": V, "apply": B}, ["object"], True)
op("object.select", "Set explicit object selection and active object.", {"objects": IDS}, ["objects"], True)
op("mesh.vertices", "Set or translate selected mesh vertices; exact vertex indices required.",
   {"object": S, "indices": INDICES, "delta": V, "positions": arr(V, 1)}, ["object", "indices"], True)
op("mesh.edit", "BMesh extrude/inset/bevel/subdivide/recalculate normals. Read topology again after changes.",
   {"object": S, "action": enum("extrude_faces", "inset_faces", "bevel_edges", "subdivide_edges", "recalc_normals"),
    "indices": INDICES, "offset": V, "amount": {"type": "number", "minimum": 0},
    "segments": {"type": "integer", "minimum": 1, "maximum": 16}}, ["object", "action"], True)
op("modifier.add", "Add a named non-destructive modifier. Booleans require a separate mesh operand.",
   {"object": S, "name": S, "kind": enum("BEVEL", "MIRROR", "SOLIDIFY", "SUBSURF", "BOOLEAN", "WEIGHTED_NORMAL"),
    "width": N, "segments": {"type": "integer", "minimum": 1, "maximum": 16}, "thickness": N,
    "levels": {"type": "integer", "minimum": 0, "maximum": 4}, "operand": S,
    "operation": enum("DIFFERENCE", "UNION", "INTERSECT")}, ["object", "name", "kind"], True)
op("modifier.apply", "Bake one existing modifier into an editable mesh. Make a checkpoint first.", {"object": S, "name": S}, ["object", "name"], True)
op("material.create", "Create a Principled material, optional local base-color/normal/roughness images.",
   {"name": S, "color": arr(N, 4, 4), "metallic": {"type": "number", "minimum": 0, "maximum": 1},
    "roughness": {"type": "number", "minimum": 0, "maximum": 1}, "base_color_image": S,
    "normal_image": S, "roughness_image": S}, ["name"], True)
op("material.assign", "Assign an existing material to an object or selected polygon indices.",
   {"object": S, "material": S, "faces": INDICES}, ["object", "material"], True)
op("uv.unwrap", "Smart-project a mesh UV layer; local geometry and topology preserved.", {"object": S}, ["object"], True)
op("reference.add", "Add a local reference image as an empty; reads only allowed roots.",
   {"name": S, "path": S, "location": V, "rotation": V, "size": N}, ["name", "path"], True)
op("camera.create", "Create camera looking at target; orthographic_scale in meters, or perspective lens mm.",
   {"name": S, "location": V, "target": V, "orthographic_scale": N, "lens": N}, ["name", "location", "target"], True)
op("light.create", "Create area light looking at target.",
   {"name": S, "location": V, "target": V, "energy": N, "size": N}, ["name", "location", "target"], True)
op("preview.render", "Render actual PNG from a named camera using Workbench clay or material (GUI Eevee/background Cycles). Optional objects isolate the subject; settings restored.",
   {"camera": S, "path": S, "objects": IDS, "width": {"type": "integer", "minimum": 64, "maximum": 2048},
    "height": {"type": "integer", "minimum": 64, "maximum": 2048}, "style": enum("clay", "material"), "overwrite": B}, ["camera", "path"])
op("preview.viewport", "Capture the current 3D viewport through Blender OpenGL. Requires GUI VIEW_3D context.",
   {"path": S, "overwrite": B}, ["path"])
op("scene.save", "Save a .blend under output root; copy=true makes a checkpoint without changing current file. Overwrites create backups.",
   {"path": S, "copy": B, "overwrite": B}, ["path"])
op("export.fbx", "Export explicit objects only, Blender meters to FBX units, -Y forward / Z up. Source scene retained.",
   {"objects": IDS, "path": S, "animation": B, "overwrite": B,
    "frame_start": {"type": "integer", "minimum": 0, "maximum": 100000},
    "frame_end": {"type": "integer", "minimum": 0, "maximum": 100000}}, ["objects", "path"])
bone = obj({"name": S, "head": V, "tail": V, "parent": S}, ["name", "head", "tail"])
op("rig.create", "Create an armature with explicitly positioned bones; parent bones must precede children.",
   {"name": S, "bones": arr(bone, 1, 1000)}, ["name", "bones"], True)
weight = obj({"bone": S, "indices": INDICES, "weight": {"type": "number", "minimum": 0, "maximum": 1}}, ["bone", "indices", "weight"])
op("rig.bind", "Bind a mesh to an armature with explicit weights; inspect normalization before delivery.",
   {"object": S, "armature": S, "weights": arr(weight, 1, 1000)}, ["object", "armature", "weights"], True)
op("animation.keyframe", "Key object or pose-bone local location/XYZ rotation/scale at a frame.",
   {"object": S, "bone": S, "frame": {"type": "integer", "minimum": -10000, "maximum": 100000},
    "location": V, "rotation": V, "scale": V}, ["object", "frame"], True)
op("animation.frame", "Set scene frame and evaluate dependencies.", {"frame": {"type": "integer", "minimum": -10000, "maximum": 100000}}, ["frame"], True)
op("python.execute", "Trusted unrestricted Python fallback; disabled unless runtime launched with --allow-python. Not a sandbox.",
   {"code": {"type": "string", "minLength": 1, "maxLength": 100000}}, ["code"], True)


def validate(value, schema, path="args"):
    if not schema:
        import json
        json.dumps(value, allow_nan=False)
        return
    if "oneOf" in schema or "anyOf" in schema:
        matches = 0
        for variant in schema.get("oneOf", schema.get("anyOf", [])):
            try:
                validate(value, variant, path)
                matches += 1
            except ValueError:
                pass
        if not matches or ("oneOf" in schema and matches != 1):
            raise ValueError(f"{path}: no unique supported variant")
        return
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int, "number": (int, float), "null": type(None)}
    if not isinstance(value, types[kind]) or (kind in ("integer", "number") and isinstance(value, bool)):
        raise ValueError(f"{path}: expected {kind}")
    if kind == "object":
        props = schema["properties"]
        extra = set(value) - set(props)
        additional = schema.get("additionalProperties", False)
        if extra and additional is False:
            raise ValueError(f"{path}: unknown keys {sorted(set(value) - set(props))}")
        if set(schema.get("required", [])) - set(value):
            raise ValueError(f"{path}: missing required keys")
        for key, item in value.items():
            validate(item, props.get(key, additional if isinstance(additional, dict) else {}), f"{path}.{key}")
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 100000):
            raise ValueError(f"{path}: invalid array length")
        for index, item in enumerate(value):
            validate(item, schema["items"], f"{path}[{index}]")
    elif kind == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 100000):
            raise ValueError(f"{path}: invalid string length")
    elif kind in ("number", "integer"):
        if not math.isfinite(value) or value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise ValueError(f"{path}: invalid numeric range")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: expected one of {schema['enum']}")


# One contract registry. Domain modules only contribute entries through op().
for _name in ("scene.save", "export.fbx", "preview.render", "preview.viewport"):
    OPS[_name].update(writes_artifacts=True, requires_revision=True,
                      long_running=True, requires_gui=_name == "preview.viewport")
from .catalog_domains import native, host  # noqa: E402,F401
