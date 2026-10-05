---
name: blender-bridge
description: Inspect or edit a live Blender scene through Blender Bridge's session-aware MCP or CLI. Use for scene and mesh inspection, vertex or BMesh edits, modifiers, materials, UVs, reference images, cameras, previews, rigs, animation, checkpoints and FBX export. Read the live capability schema before invoking operations. Does not itself certify visual quality or authorize Unreal Content changes.
---

# Blender Bridge

Use this repository's runtime and live catalog. Do not invent Blender operators or send large one-shot generators as a substitute for iterative modeling.

## Connect and inspect

1. Read the current project's instructions and exact authorized file/object scope. Preserve other Blender/Unreal sessions and unrelated scene data.
2. Call `blender_discover`; select the exact session by PID, file and output root. Multiple sessions require an explicit match; never pick the first. Call `blender_health` and `scene.inspect`.
3. No runtime: use [runtime guide](references/runtime.md) to start an owned Blender instance or use the installed add-on panel in an authorized existing instance. Do not reset a user scene, replace their file or stop their process.
4. Search with `blender_catalog(query=...)`, then use `describe=<exact operation>` for the full input schema. This release exposes grouped tools, not one tool for every Blender operator.

## Edit and verify

- Use `blender_execute(session, operation, args, request_id, revision)`. Generate a stable UUID per logical operation. Use the just-inspected revision for mutations, previews, saves and exports. Do not silently refresh a stale revision and retry a write; inspect the intervening change first.
- All `bpy` operations execute on the Blender main thread. Calls may return `queued` or `running`. Query `blender_job` until terminal. A timeout or disconnect is an unknown outcome: query the original ID. Do not resubmit using a new ID.
- Work in short, reviewable edits. Inspect actual mesh vertices/faces before editing; topology operations invalidate indices. Re-read after extrude/inset/bevel/subdivide/apply. Shared mesh data is deliberately rejected for direct edits.
- Make a `scene.save(copy=true)` checkpoint before applying modifiers or significant topology changes. This is a file checkpoint, not automatic rollback. Report failures as potentially partial; inspect before repair. Do not revert without authorization.
- Use `preview.render` with explicit subject `objects` and a named review camera; inspect the image with `blender_view_image`. The viewport screenshot is separate evidence of the live GUI. Render completion alone says nothing about reference fidelity.
- End with an explicit source save, relevant mesh/weight/UV checks, source readback and selected-object export if requested. Files stay inside configured output root. Existing paths require explicit `overwrite=true`, which preserves a backup first. Do not mass-save unrelated Blender data into an unapproved destination.
- `python.execute` is a trusted unrestricted fallback, disabled by default. It is not a sandbox, cannot be interrupted safely, and bypasses typed-operation path protections. Use only for a justified missing capability within existing authorization; prefer adding a typed operation with a real Blender test.

## Report honestly

List changed objects/files, saved versus unsaved state, session/PID, actual validation and untested limitations. Keep technical validation separate from artistic acceptance. Use `$blender-reference-modeling` when turning an approved concept into an asset. UE import remains a separate UnrealBridge/project workflow.

