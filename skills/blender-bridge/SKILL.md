---
name: blender-bridge
description: Inspect and refine supplied or imported Blender assets through grouped MCP or the same-contract CLI. For concept-based asset work, deliver concept and separate view images first, wait for the user's externally generated model, then perform scoped visual refinement, UV/material/rig work and verified exports. Do not start a model from reference images alone.
---

# Blender Bridge

Use this repository's runtime and live catalog for Blender work. Do not invent Blender operators or send large one-shot generators as a substitute for scoped refinement.

## Choose the current stage

- **Concept images only:** prepare the requested concept and view images with the available image-generation workflow. For a concept plus three-view package, provide four separate files: hero, front, right side and back. Preserve originals, view labels, prompts and uncertain hidden geometry. Image-generated views are references, not guaranteed projections of one mesh. Deliver the images and stop at the user's external-model handoff; do not start Blender, construct geometry, or treat concept approval as authorization to model.
- **External model supplied or imported:** the user generates the initial model with their chosen online service. Continue when an actual model file with its textures, or an identified imported scene object, is available and refinement is requested. Record the source path/hash and target objects; preserve the original. Inspect dimensions, axes, disconnected/fused parts, topology, normals, UVs, materials and any rig before planning local corrections. Use `$blender-reference-modeling` for this refinement stage.
- **Other explicit Blender edits:** operate on the user's existing scene or supplied asset within the requested scope. The external-model handoff does not block ordinary inspection, material edits, animation, export or tool maintenance.

Do not upload images, invoke an online modeling service, download weights or replace the user's model as an implied step. New explicit user instructions may select a different creation workflow; do not infer that change from an approved image.

## Connect and inspect

1. Read the current project's instructions and exact authorized file/object scope. Preserve other Blender/Unreal sessions and unrelated scene data.
2. Call `blender_discover`; select the exact session by PID, file and output root. Multiple sessions require an explicit match; never pick the first. Call `blender_health` and `scene.inspect`.
3. No runtime: use [runtime guide](references/runtime.md) to start an owned Blender instance or use the installed add-on panel in an authorized existing instance. Do not reset a user scene, replace their file or stop their process.
4. Search with `blender_catalog(query=...)`, then use `describe=<exact operation>` for the full input schema. This release exposes grouped tools, not one tool for every Blender operator.
5. Host operations such as `reference.*`, `system.*`, `worker.*` and `delivery.*` do not require a live scene unless the catalog says so. `modeling.plan/submit/resume` bind an exact scene session and revision. The catalog declares execution domain, mutation, artifact writes, long-running state and cancellation policy; do not infer these from the operation name.

## Edit and verify

- Use `blender_execute(session, operation, args, request_id, revision)`. Generate a stable UUID per logical operation. Use the just-inspected revision for mutations, previews, saves and exports. Do not silently refresh a stale revision and retry a write; inspect the intervening change first.
- All `bpy` operations execute on the Blender main thread. Calls may return `queued` or `running`. Query `blender_job` until terminal. A timeout or disconnect is an unknown outcome: query the original ID. Do not resubmit using a new ID.
- Work in short, reviewable edits. Inspect actual mesh vertices/faces before editing; topology operations invalidate indices. Re-read after extrude/inset/bevel/subdivide/apply. Shared mesh data is deliberately rejected for direct edits.
- Make a scoped `checkpoint.create(objects=...)` before significant topology changes. `checkpoint.restore` appends a new candidate, preserves the current scene and invalidates the old session/selection context. `batch.execute` prevalidates and reports exact completed steps on partial failure; it is not an atomic rollback. Do not revert without authorization.
- Use `preview.render` with explicit subject `objects` and a named review camera; inspect the image with `blender_view_image`. The viewport screenshot is separate evidence of the live GUI. Render completion alone says nothing about reference fidelity.
- Use semantic parts and topology-bound selections. Inspect base versus evaluated geometry separately; evaluated polygon indices are not editable base indices. `selection.pick` uses the exact registered render camera and stale-source checks. Lock approved regions and use bounded transforms, flatten/smooth or geometry sculpt; requery after topology changes.
- End with `export.package` for exact source/FBX/GLB/OBJ/texture manifests, `game.validate` for a concrete profile, and Host `delivery.verify` for independent process readback. Files stay inside configured output roots; immutable outputs require a new path. `scene.save(copy=true)` remains a whole-scene file copy, so use it only when the entire scene is authorized. UE remains separate.
- `python.execute` is a trusted unrestricted fallback, disabled by default. It is not a sandbox, cannot be interrupted safely, and bypasses typed-operation path protections. Use only for a justified missing capability within existing authorization; prefer adding a typed operation with a real Blender test.

## Native visual loop

For concept-based asset work, enter this loop only after the external model is available. Establish fixed Before views of the imported model before editing; retain useful geometry and correct concrete mismatches instead of rebuilding the whole asset from primitives.

1. Register actual reference images with `reference.register`. Preserve original files, real view labels, approval provenance, pose, physical dimensions and unknown areas. Crop/mask/calibrate explicitly; converting RGB to RGBA does not remove the background. Freeze immutable inputs with `reference.freeze`.
2. Get `reference.view` artifacts and actually read them with `blender_view_image`. A filename, image hash, contact-sheet path or image delivery receipt is not a visual judgment.
3. Author bounded corrective steps against the inspected imported geometry, protected parts and fixed cameras in `modeling.plan`; `modeling.submit` executes once, renders and stops at `awaiting_visual_review`. References guide the correction; they are not a request to generate the initial mesh.
4. Read all returned images, compare proportions, silhouettes, structural layering, thickness and mechanical connections. Register factual observations and stable difference IDs with `review.record`. Self-review must be based on the current candidate, images and reference hash.
5. Use `modeling.resume` with explicit corrective steps or a matching self-review pass. Carry every unresolved difference forward until explicitly resolved. A fixture-protocol review never establishes art quality. User visual acceptance remains pending unless the user actually supplies it.
6. After restarting a saved scene, inspect its new session/revision and use `modeling.reconnect` only for a pending review with unchanged source/camera evidence. It preserves issues and never replays writes. See the runtime guide for the persistent Windows Host broker and prepared bake-plan worker requirements.

Long operations can run on an immutable blend through `worker.submit` in an owned background Blender. Query the original Host job after disconnect. `worker.cancel` requires the exact registered PID/start/executable/command identity and retains partial output; it never stops an unrelated Blender or pretends a running interactive bpy call can be interrupted safely. BlenderBridge supplies the inspection/refinement toolchain; it does not bundle an image-to-3D engine or run the user's online generation step.

## Report honestly

List changed objects/files, saved versus unsaved state, session/PID when applicable, actual validation and untested limitations. State whether the handoff is images awaiting an external model, an inspected import, or a refined asset. Keep technical validation separate from artistic acceptance. UE import remains a separate UnrealBridge/project workflow.

