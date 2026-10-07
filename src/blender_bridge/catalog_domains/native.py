"""Blender-native typed operations. No bpy imports in schemas."""
from ..catalog import op, obj, arr, enum, S, N, I, B, V, IDS, INDICES, OPS

MAP = {"type": "object", "properties": {}, "additionalProperties": {}}
STRINGS = arr(S, 0, 1000)
POINTS = arr(V, 3, 100000)
UNIT = {"type": "number", "minimum": 0, "maximum": 1}
POS = {"type": "number", "exclusiveMinimum": 0, "minimum": 0.000000001}
PAGE = {"type": "integer", "minimum": 1, "maximum": 2000}

def native(name, description, props=None, required=(), write=True, artifacts=False, long_running=False):
    op(name, description, props, required, write, artifacts=artifacts, long_running=long_running)

native("scene.capabilities", "Probe installed Blender API, devices and supported import/render/modifier operations.", write=False)
native("scene.identify", "Assign persistent object/mesh IDs to explicitly selected data; preserve existing identities.", {"objects": IDS}, ["objects"])
native("scene.fingerprint", "Hash exact object geometry, transforms, UVs, groups and material state for protected-scope checks.", {"objects": IDS}, ["objects"], False)
native("scene.configure", "Set scene units/world/render quality explicitly.", {"unit_system": enum("NONE","METRIC","IMPERIAL"), "scale_length": POS, "world_color": V, "samples": {"type":"integer","minimum":1,"maximum":256}})

OPS["mesh.inspect"]["inputSchema"]["properties"].update(mode=enum("base","evaluated"))
OPS["object.transform"]["inputSchema"]["properties"].update(space=enum("local","world"), apply_location=B, apply_rotation=B, apply_scale=B)
OPS["uv.unwrap"]["inputSchema"]["properties"].update(method=enum("smart","angle_based","conformal"), margin=UNIT)
native("object.duplicate", "Duplicate one object, optionally with independent data and copied child hierarchy.", {"object":S,"name":S,"linked":B,"children":B,"collection":S}, ["object","name"])
native("object.make_single_user", "Copy shared mesh/curve/armature data explicitly.", {"object":S}, ["object"])
native("object.rename", "Rename an exact object while preserving persistent identity.", {"object":S,"name":S}, ["object","name"])
native("object.delete", "Preview exact objects by default. Deletion requires confirm=true and matching revision.", {"objects":IDS,"confirm":B}, ["objects"])
native("object.parent", "Set or clear parent while preserving world transform when requested.", {"objects":IDS,"parent":S,"clear":B,"keep_world":B}, ["objects"])
native("object.origin", "Move pivot to an explicit world location without moving visible geometry.", {"object":S,"location":V}, ["object","location"])
native("object.visibility", "Set exact object viewport/render visibility.", {"objects":IDS,"viewport":B,"render":B}, ["objects"])
native("object.join", "Join only explicit independent meshes into named target and preserve source part provenance.", {"objects":IDS,"name":S}, ["objects","name"])
native("object.separate", "Separate explicit faces, a current vertex selection, or loose components. selection_id requires explicit face_policy; keep_original splits an independent copy. Verify base positions, UVs, materials and weights; invalidate only edited-source selections.",
       {"object":S,"faces":INDICES,"selection_id":S,"face_policy":enum("all_vertices","any_vertex"),
        "mode":enum("faces","loose"),"name":S,"keep_original":B}, ["object","name"])
native("collection.inspect", "Read exact collection object IDs and nested collections.", {"collection":S}, ["collection"], False)
native("collection.move", "Link exact objects into destination; unlink old collections only when requested.", {"objects":IDS,"collection":S,"unlink_others":B}, ["objects","collection"])
native("collection.duplicate", "Duplicate a collection hierarchy with independent meshes by default.", {"collection":S,"name":S,"linked":B}, ["collection","name"])
native("collection.visibility", "Set collection viewport/render visibility.", {"collection":S,"viewport":B,"render":B}, ["collection"])
native("asset.create", "Create an asset collection and persistent candidate metadata.", {"asset_id":S,"name":S,"revision":I,"role":enum("native_source","editable_work","high_detail","game_low","fixture")}, ["asset_id","name"])
native("asset.inspect", "Inspect asset collection and explicit members.", {"asset_id":S}, ["asset_id"], False)
native("asset.clone_revision", "Clone exact asset collection as an independent editable candidate.", {"asset_id":S,"name":S,"revision":I}, ["asset_id","name","revision"])
for _name in ("asset.import","asset.append"):
    native(_name, "Import GLB/GLTF/OBJ/FBX or append selected blend objects without replacing the scene.", {"path":S,"collection":S,"objects":STRINGS,"prefix":S,"scale":POS}, ["path","collection"], long_running=True)

MODIFIERS = ("BEVEL","MIRROR","SOLIDIFY","SUBSURF","BOOLEAN","WEIGHTED_NORMAL","SHRINKWRAP","DECIMATE","REMESH","TRIANGULATE","ARRAY","SIMPLE_DEFORM")
OPS["modifier.add"]["inputSchema"]["properties"].update(kind=enum(*MODIFIERS), properties=MAP)
native("modifier.inspect", "Inspect RNA-supported parameters and modifier order; report accepted parameter schema per type.", {"object":S,"name":S}, ["object"], False)
native("modifier.update", "Update only supported type-specific modifier parameters; validate RNA before writing.", {"object":S,"name":S,"properties":MAP}, ["object","name","properties"])
native("modifier.remove", "Remove one exact modifier; preserves other modifiers.", {"object":S,"name":S}, ["object","name"])
native("modifier.reorder", "Move one named modifier to the explicit stack index.", {"object":S,"name":S,"index":I}, ["object","name","index"])
native("modifier.copy", "Copy a supported modifier to another exact object, preserving parameters and operands.", {"object":S,"name":S,"target":S,"new_name":S}, ["object","name","target"])

native("geometry.profile", "Create a planar custom contour with explicit extrusion; validates polygon and thickness.", {"name":S,"points":POINTS,"depth":N,"direction":V,"collection":S}, ["name","points"])
native("geometry.loft", "Loft equal-length ordered cross sections with optional caps and cyclic alignment.", {"name":S,"sections":arr(POINTS,2,256),"cap":B,"align":B,"collection":S}, ["name","sections"])
native("geometry.sweep", "Sweep a 2D contour along a 3D path using transported frames and explicit caps.", {"name":S,"profile":arr(arr(N,2,2),3,256),"path":arr(V,2,10000),"up":V,"cap":B,"collection":S}, ["name","profile","path"])
native("geometry.curve", "Create editable POLY/BEZIER curve with optional bevel radius.", {"name":S,"points":arr(V,2,10000),"kind":enum("POLY","BEZIER"),"closed":B,"radius":N,"collection":S}, ["name","points"])
native("geometry_nodes.inspect", "Inspect exact Geometry Nodes modifier input sockets and evaluated geometry.", {"object":S,"modifier":S}, ["object","modifier"], False)
native("geometry_nodes.set_input", "Set exposed scalar/vector/bool Geometry Nodes modifier input using its socket identifier.", {"object":S,"modifier":S,"identifier":S,"value":{}}, ["object","modifier","identifier","value"])

region = {"object":S,"indices":INDICES,"selection_id":S,"delta":V,"scale":V,"center":V,"rotation":V,"space":enum("local","world"),"radius":POS,"falloff":enum("constant","linear","cosine"),"mask_group":S,"protected_parts":STRINGS}
native("mesh.region_transform", "Transform an exact vertex region with falloff and protected part/region checks.", region, ["object"])
native("mesh.flatten", "Project explicit vertices toward a plane with strength, mask and protection.", {**region,"normal":V,"strength":UNIT}, ["object","normal"])
native("mesh.smooth", "Laplacian smooth explicit vertices with fixed boundary and protected regions.", {**region,"iterations":{"type":"integer","minimum":1,"maximum":100},"strength":UNIT}, ["object"])
native("mesh.bridge_loops", "Bridge two explicit ordered edge loops, validate order and optional cyclic alignment.", {"object":S,"first":INDICES,"second":INDICES,"closed":B,"align":B}, ["object","first","second"])
native("mesh.slide", "Slide selected vertices along explicit neighboring edges without arbitrary remeshing.", {"object":S,"indices":INDICES,"towards":INDICES,"factor":UNIT}, ["object","indices","towards"])
native("mesh.cut", "Bisect an exact mesh by plane; optional clear/fill are explicit topology changes.", {"object":S,"point":V,"normal":V,"clear_inner":B,"clear_outer":B,"fill":B}, ["object","point","normal"])

native("part.register", "Register explicit semantic part as object set or vertex region; never infer semantics from loose geometry.", {"part_id":S,"objects":IDS,"indices":INDICES,"source":enum("explicit","geometric_proposal","reviewed"),"role":S}, ["part_id","objects"])
native("part.assign_region", "Assign an explicit current-topology vertex region to a semantic part.", {"part_id":S,"object":S,"indices":INDICES}, ["part_id","object","indices"])
native("part.inspect", "Read persistent part mapping, region topology and lock state.", {"part_id":S}, write=False)
for _action in ("lock","unlock"):
    native("part."+_action, "Set semantic part protection with geometry snapshot.", {"part_id":S}, ["part_id"])
query={"objects":IDS,"part_id":S,"indices":INDICES,"box_min":V,"box_max":V,"center":V,"radius":POS,"height_range":arr(N,2,2),"normal":V,"angle_degrees":{"type":"number","minimum":0,"maximum":180},"material":S,"vertex_group":S,"connected_from":I,"boundary":B,"sharp_angle":N,"space":enum("local","world")}
native("selection.query", "Create bounded vertex selection from geometry predicates; binds mesh identity and topology hash.", query, write=False)
native("selection.combine", "Union/intersect/subtract or grow/shrink current-topology selections.", {"selections":IDS,"mode":enum("union","intersection","difference","grow","shrink"),"steps":{"type":"integer","minimum":1,"maximum":50}}, ["selections","mode"], False)
native("selection.pick", "Ray-pick using registered render camera/pixels. Optional image_transform maps a displayed crop/resize to source pixels; evaluated indices are never base indices.", {"artifact_id":S,"pixel":arr(N,2,2),"rectangle":arr(N,4,4),"objects":IDS,"radius":POS,"visible_only":B,"image_transform":obj({"source_rectangle":arr(N,4,4),"display_size":arr(POS,2,2)},["source_rectangle","display_size"])}, ["artifact_id","objects"], False)
native("selection.preview", "Render actual selection overlay from the original camera into a new registered image.", {"selection_id":S,"camera":S,"path":S,"width":PAGE,"height":PAGE}, ["selection_id","camera","path"], False, True)

for _action in ("grab","inflate","smooth","flatten"):
    native("sculpt."+_action, "Deterministic geometry-based local sculpt (not a native brush replay), with mask and falloff.", {**region,"normal":V,"strength":N,"iterations":{"type":"integer","minimum":1,"maximum":100}}, ["object"])
native("sculpt.mask", "Create/update an explicit vertex mask group.", {"object":S,"name":S,"indices":INDICES,"weight":UNIT,"clear":B}, ["object","name","indices"])
native("sculpt.symmetrize", "Mirror coordinates using bounded nearest mirrored vertices; asymmetric parts remain explicit.", {"object":S,"axis":enum("X","Y","Z"),"direction":enum("positive_to_negative","negative_to_positive"),"tolerance":POS}, ["object"])

native("retopo.prepare", "Create an independent low/work candidate from a preserved high source.", {"source":S,"name":S,"collection":S}, ["source","name"])
native("retopo.remesh", "Apply voxel remesh or controlled decimation to an independent candidate; declare UV/weight loss.", {"object":S,"method":enum("voxel","decimate","quadriflow"),"voxel_size":POS,"ratio":UNIT,"faces":{"type":"integer","minimum":20,"maximum":1000000},"allow_data_loss":B}, ["object","method"], long_running=True)
native("retopo.strip", "Build an editable quad strip from two matched rails and optionally project onto a high mesh.", {"name":S,"first":arr(V,2),"second":arr(V,2),"target":S,"collection":S}, ["name","first","second"])
native("retopo.project", "Project a low candidate onto a preserved source with nearest surface queries and a distance limit.", {"object":S,"target":S,"max_distance":POS,"indices":INDICES}, ["object","target","max_distance"])
native("retopo.validate", "Measure low-to-high surface deviations and actual triangle budget; no art approval.", {"object":S,"source":S,"max_distance":POS,"max_triangles":I}, ["object","source"], False)

native("uv.inspect", "Inspect UV islands, area, density and UV topology without changing the mesh.", {"object":S,"resolution":I}, ["object"], False)
native("uv.mark_seams", "Set/clear exact seam edges, optionally by dihedral angle.", {"object":S,"edges":INDICES,"angle_degrees":N,"clear":B}, ["object"])
native("uv.pack", "Pack UV islands with explicit padding/rotation policy.", {"object":S,"margin":UNIT,"rotate":B}, ["object"])
native("uv.set_density", "Scale UV islands toward explicit pixels-per-meter; record potential bounds changes.", {"object":S,"pixels_per_meter":POS,"resolution":I}, ["object","pixels_per_meter","resolution"])
native("uv.transform", "Transform exact UV faces/islands with explicit offset, scale and radians.", {"object":S,"faces":INDICES,"offset":arr(N,2,2),"scale":arr(N,2,2),"rotation":N}, ["object"])
native("uv.validate", "Check actual rasterized UV overlap, intentional sharing, bounds and padding.", {"object":S,"resolution":I,"allow_overlap":B,"padding_pixels":I}, ["object"], False)
native("material.inspect", "Inspect Principled values, node links, image paths and color spaces.", {"material":S}, ["material"], False)
native("material.update", "Set supported PBR inputs, emission and optional procedural noise detail.", {"material":S,"color":arr(N,4,4),"metallic":UNIT,"roughness":UNIT,"emission":arr(N,4,4),"emission_strength":N,"opacity":UNIT,"noise_scale":POS,"bump_strength":N}, ["material"])
native("material.copy", "Duplicate one material with independent editable nodes.", {"material":S,"name":S}, ["material","name"])
native("material.relink", "Attach a validated local image to an exact PBR channel with correct color space.", {"material":S,"channel":enum("BaseColor","Normal","Roughness","Metallic","AO","Emissive","Opacity"),"path":S,"flip_normal_y":B}, ["material","channel","path"])
projection=obj({"camera":S,"image":S,"weight":POS}, ["camera","image"])
native("texture.project", "Rasterize calibrated view colors into current UVs with ray-based visibility and coverage report.", {"object":S,"views":arr(projection,1,8),"path":S,"resolution":{"type":"integer","minimum":16,"maximum":2048},"background":arr(N,4,4),"material":S}, ["object","views","path"], False, True, True)
native("bake.prepare", "Freeze explicit high/low/cage mapping, UV and geometry hashes; creates a bake plan.", {"high":STRINGS,"low":S,"cage":S,"channels":arr(enum("Normal","AO","BaseColor","Roughness","Metallic","Emissive","Opacity"),1,7),"resolution":{"type":"integer","minimum":16,"maximum":4096},"margin":I,"ray_distance":N,"directory":S}, ["low","channels","directory"], False, True)
native("bake.execute", "Bake a frozen plan with source/UV validation and real image statistics; settings restored.", {"plan_id":S}, ["plan_id"], False, True, True)
native("bake.inspect", "Read bake plan/artifacts and stale-source state.", {"plan_id":S}, ["plan_id"], False)

native("rig.inspect", "Inspect deform bones, transforms, hierarchy and current/rest poses.", {"armature":S}, ["armature"], False)
bone=obj({"name":S,"head":V,"tail":V,"roll":N,"deform":B,"parent":S}, ["name"])
native("rig.fit", "Adjust exact edit bones and deformation flags without replacing the armature.", {"armature":S,"bones":arr(bone,1,1000)}, ["armature","bones"])
native("rig.bind_rigid", "Bind explicitly named rigid meshes to individual deform bones.", {"armature":S,"bindings":arr(obj({"object":S,"bone":S},["object","bone"]),1,1000)}, ["armature","bindings"])
native("rig.bind_auto", "Use Blender automatic weights as an initial candidate, then return deform-only validation.", {"objects":IDS,"armature":S}, ["objects","armature"], long_running=True)
native("rig.weights_edit", "Edit, clear, smooth or mirror only deform-bone weights within an explicit region.", {"object":S,"armature":S,"action":enum("set","add","clear","smooth","mirror"),"bone":S,"indices":INDICES,"weight":UNIT,"iterations":{"type":"integer","minimum":1,"maximum":50},"axis":enum("X","Y","Z"),"bone_map":MAP}, ["object","armature","action"])
native("rig.weights_transfer", "Transfer deform weights from nearest source surface within distance and region bounds.", {"object":S,"source":S,"armature":S,"max_distance":POS,"indices":INDICES}, ["object","source","armature","max_distance"])
native("rig.weights_normalize", "Normalize and limit deform weights; unweighted vertices remain reported unless explicit fallback is supplied.", {"object":S,"armature":S,"max_influences":{"type":"integer","minimum":1,"maximum":32},"fallback_bone":S}, ["object","armature"])
native("rig.validate", "Validate only deform-bone weights; report non-deform groups independently.", {"object":S,"armature":S,"max_influences":I}, ["object","armature"], False)
native("animation.inspect", "Read action/layer frame ranges and current pose without mutating scene.", {"object":S}, ["object"], False)
native("animation.sample", "Evaluate explicit frames and restore the original frame; report evaluated bounds and bone transforms.", {"objects":IDS,"frames":arr(I,1,1000)}, ["objects","frames"], False)
pose=obj({"label":S,"bones":MAP}, ["label","bones"])
native("animation.pose_test", "Apply explicit test poses temporarily; capture measurements/renders and verify return to original pose.", {"armature":S,"objects":IDS,"poses":arr(pose,1,100),"camera":S,"directory":S,"width":PAGE,"height":PAGE}, ["armature","objects","poses","directory"], False, True, True)

view=obj({"label":S,"camera":S},["label","camera"])
native("preview.camera_set", "Create fixed front/left/back/right/three-quarter cameras at explicit center and scale.", {"name":S,"center":V,"scale":POS,"distance":POS}, ["name","center","scale"])
native("preview.validate", "Validate current source and camera against registered renders; stale images cannot authorize edits or review.", {"artifact_ids":IDS}, ["artifact_ids"], False)
native("preview.multiview", "Render fixed camera set with exact subjects and registered source geometry/camera provenance.", {"objects":IDS,"views":arr(view,1,32),"directory":S,"style":enum("clay","material","silhouette","wireframe","normal","parts"),"width":PAGE,"height":PAGE}, ["objects","views","directory"], False, True, True)
native("preview.turntable", "Render turntable around explicit center at frozen scale with exact subjects.", {"objects":IDS,"center":V,"scale":POS,"directory":S,"frames":{"type":"integer","minimum":4,"maximum":64},"width":PAGE,"height":PAGE,"style":enum("clay","material")}, ["objects","center","scale","directory"], False, True, True)
native("preview.region", "Render a specified camera/subject region without changing the approved whole-object cameras.", {"objects":IDS,"center":V,"scale":POS,"direction":V,"path":S,"width":PAGE,"height":PAGE}, ["objects","center","scale","path"], False, True, True)

native("checkpoint.create", "Save source, metadata, object fingerprints and manifests as an immutable checkpoint.", {"label":S,"objects":IDS}, ["label"], False, True, True)
native("checkpoint.list", "List checkpoints registered beneath the current output root.", write=False)
native("checkpoint.restore", "Append checkpoint objects into a new candidate; preserve current scene and rotate session/selection identity.", {"checkpoint_id":S,"name":S}, ["checkpoint_id","name"], True, True, True)
step=obj({"operation":S,"args":MAP},["operation","args"])
native("batch.execute", "Prevalidate ordered native steps; execute once, report exact partial completion on failure.", {"steps":arr(step,1,256),"protected_parts":STRINGS,"expected_hashes":MAP}, ["steps"])
native("recipe.inspect", "Read editable geometry recipe and current object values.", {"object":S}, ["object"], False)
native("recipe.replay", "Rebuild a parametric geometry recipe into a new object, preserving manually edited source.", {"object":S,"name":S,"parameters":MAP,"collection":S}, ["object","name"])
native("game.validate", "Check explicit game profile, transforms, mesh/UV/weights, materials, dimensions and unknown requirements.", {"objects":IDS,"profile":MAP}, ["objects"], False)
native("game.lod", "Create independent named LOD meshes with explicit reduction ratios and deviation reports.", {"object":S,"ratios":arr(UNIT,1,8),"collection":S}, ["object","ratios"])
native("game.collision", "Create separately named convex-hull or box collision mesh from exact source.", {"object":S,"name":S,"kind":enum("convex","box"),"collection":S}, ["object","name"])
native("export.package", "Save editable blend, selected FBX/GLB, textures and manifest using explicit objects/profile/range.", {"objects":IDS,"directory":S,"formats":arr(enum("fbx","glb","obj"),1,3),"animation":B,"frame_start":I,"frame_end":I,"profile":MAP}, ["objects","directory"], False, True, True)
native("export.prepare_ue", "Create read-only Unreal import plan from explicit export manifest; never writes UE content.", {"manifest":S,"destination":S}, ["manifest"], False, True)
