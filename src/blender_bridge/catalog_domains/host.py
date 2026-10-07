"""Host CPU and isolated Blender workflow contracts. No implicit scene writes."""
from ..catalog import op, obj, arr, enum, S, N, I, B, V, IDS, OPS
from .native import MAP, UNIT, STRINGS, step, view

def host(name, description, props=None, required=(), artifacts=False, long_running=False):
    op(name, description, props, required, domain="host_cpu", artifacts=artifacts,
       long_running=long_running, cancellation="queued_only")

host("system.doctor", "Inspect configured local Blender/Host/dependencies/resources without changing an environment.")
host("system.capabilities", "Report typed implementation catalog and live Blender probe separately from verified test evidence.")
host("job.recover", "Explicitly requeue the original Host ID only when the durable record proves execution never started; running/unknown native writes are never replayed.", {"job_id":S}, ["job_id"])
host("system.verify", "Run installed native fixture in an owned background Blender; does not perform visual acceptance.", {"suite":enum("native-modeling"),"run_fixture":B}, artifacts=True, long_running=True)
host("worker.inspect", "Inspect only owned worker records, PID/start identity, logs and real task state.", {"worker_id":S})
host("worker.submit", "Run a registered native operation on an immutable blend snapshot in an isolated owned Blender. bake.execute also requires its exact prepared bake_plan manifest.", {"blend":S,"operation":S,"args":MAP,"directory":S,"expected_sha256":S,"bake_plan":S}, ["blend","operation","args","directory","expected_sha256"], True, True)
host("worker.cancel", "Stop an exact owned background Blender after validating PID and creation identity; reports partial output.", {"worker_id":S,"pid":I}, ["worker_id","pid"], True)
image=obj({"label":enum("front","left","back","right","three_quarter","detail"),"path":S,"pose_id":S,"camera":MAP,"landmarks":MAP}, ["label","path"])
host("reference.register", "Register images under allowed read roots with hashes, approval provenance, geometry assumptions and unknown regions.", {"reference_id":S,"views":arr(image,1,32),"approval_status":enum("fixture_only","pending_user_review","approved"),"approval_evidence":S,"pose_id":S,"height_m":N,"unknown_regions":STRINGS,"asset_type":S}, ["reference_id","views"], True)
host("reference.crop", "Create an explicit rectangle crop as a new reference revision; preserve original and transform chain.", {"reference_id":S,"view":S,"rectangle":arr(I,4,4)}, ["reference_id","view","rectangle"], True)
host("reference.mask", "Create an explicit alpha/color/polygon mask, reporting effective transparency rather than image mode alone.", {"reference_id":S,"view":S,"mode":enum("alpha","color","polygon","image"),"color":arr(I,3,3),"tolerance":I,"polygon":arr(arr(N,2,2),3,10000),"path":S}, ["reference_id","view","mode"], True)
host("reference.calibrate", "Isotropically scale and letterbox a view, preserving transform, landmarks and ground/center lines.", {"reference_id":S,"view":S,"width":I,"height":I,"ground_line":N,"center_line":N,"landmarks":MAP,"camera":MAP}, ["reference_id","view","width","height"], True)
host("reference.validate", "Check real files/hashes, view consistency, masks, pose and unknown/conflicting camera evidence.", {"reference_id":S,"manifest":S})
host("reference.freeze", "Publish immutable input images/manifest and hash; future source changes cannot silently alter a job.", {"reference_id":S}, ["reference_id"], True)
host("reference.view", "Return registered image/contact-sheet artifacts for actual image reading.", {"reference_id":S,"view":S}, ["reference_id"], True)

plan={"modeling_id":S,"asset_id":S,"reference_id":S,"reference_revision":I,"reference_sha256":S,"candidate_revision":I,"objects":IDS,"steps":arr(step,1,256),"views":arr(view,1,32),"protected_parts":STRINGS,"directory":S,"width":I,"height":I,"assumptions":STRINGS}
host("modeling.plan", "Register an agent-authored native plan against frozen references and exact session/revision. Does not infer geometry from file names.", plan, ["modeling_id","asset_id","reference_id","reference_revision","reference_sha256","objects","steps","views","directory"], True)
host("modeling.submit", "Execute a validated native batch, capture fixed views and stop at awaiting_visual_review.", {"modeling_id":S}, ["modeling_id"], True, True)
host("modeling.inspect", "Read durable modeling phase, artifacts, open differences and exact scene context.", {"modeling_id":S}, ["modeling_id"])
host("modeling.reconnect", "Bind a pending review to an explicitly observed replacement session only after exact source/image/camera validation. Preserves issues and never replays geometry writes.", {"modeling_id":S}, ["modeling_id"], True)
host("modeling.resume", "Resume only after version-matched actual image review; edit exact steps or advance to technical validation.", {"modeling_id":S,"review_id":S,"steps":arr(step,0,256)}, ["modeling_id","review_id"], True, True)
issue=obj({"issue_id":S,"part_id":S,"views":STRINGS,"category":S,"severity":enum("minor","major","critical"),"observation":S,"proposed_action":S,"protected_parts":STRINGS,"status":enum("open","resolved","not_applicable")},["issue_id","observation","status"])
host("review.record", "Record reviewer observations after image delivery; requires matching versions/hashes. Never grants user acceptance.", {"modeling_id":S,"review_id":S,"candidate_revision":I,"artifact_ids":IDS,"issues":arr(issue,0,1000),"summary":S,"decision":enum("needs_work","self_review_passed"),"reviewer":enum("codex","human","fixture_protocol")}, ["modeling_id","review_id","candidate_revision","artifact_ids","issues","summary","decision","reviewer"], True)
host("compare.views", "Compose real reference/candidate images into labelled comparison, optional aligned overlay and raw metrics.", {"reference_artifacts":IDS,"candidate_artifacts":IDS,"path":S,"alignment":MAP,"overlay":B}, ["reference_artifacts","candidate_artifacts","path"], True)
host("compare.region", "Crop a registered image into a new comparison artifact with source hash and explicit rectangle.", {"artifact_id":S,"rectangle":arr(I,4,4),"path":S}, ["artifact_id","rectangle","path"], True)
host("texture.pack_channels", "Pack explicit channel swizzles from registered local texture files without color conversion.", {"sources":arr(obj({"path":S,"channel":enum("R","G","B","A"),"output":enum("R","G","B","A")},["path","channel","output"]),1,4),"path":S,"fill":arr(N,4,4)}, ["sources","path"], True)
host("delivery.inspect", "Inspect the current delivery manifest, verify hashes and report independent validation states.", {"manifest":S}, ["manifest"])
host("delivery.verify", "Independently reopen source and reimport each exported format in owned background Blender processes; publish measurements and comparisons.", {"manifest":S}, ["manifest"], True, True)
host("delivery.report", "Write a Chinese report from recorded facts; missing technical/visual/UE checks remain unknown/not_run.", {"manifest":S,"path":S}, ["manifest","path"], True)

for _operation in ('modeling.plan','modeling.submit','modeling.resume','modeling.reconnect'):
    OPS[_operation]['requires_session']=True
    OPS[_operation]['requires_revision']=True
