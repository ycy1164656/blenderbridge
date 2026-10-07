from pathlib import Path
import json
import uuid
import bpy
from bpy.props import StringProperty, IntProperty, BoolProperty
from . import runtime


class BBPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    output_root: StringProperty(name="Output root", subtype='DIR_PATH', default=str(Path.home() / 'BlenderBridgeOutput'))
    read_roots: StringProperty(name="Additional read roots (semicolon-separated)", default="")
    port: IntProperty(name="Loopback port (0 = automatic)", default=0, min=0, max=65535)
    allow_python: BoolProperty(name="Allow trusted unrestricted Python", default=False)

    def draw(self, context):
        for key in ('output_root', 'read_roots', 'port', 'allow_python'): self.layout.prop(self, key)


class BBStart(bpy.types.Operator):
    bl_idname = 'blender_bridge.start'
    bl_label = 'Start Blender Bridge'

    def execute(self, context):
        p = context.preferences.addons[__package__].preferences
        try:
            runtime.start(bpy.path.abspath(p.output_root), [r for r in p.read_roots.split(';') if r], p.port, p.allow_python)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class BBStop(bpy.types.Operator):
    bl_idname = 'blender_bridge.stop'
    bl_label = 'Stop Blender Bridge'

    def execute(self, context):
        runtime.stop()
        return {'FINISHED'}


class BBPanel(bpy.types.Panel):
    bl_label = 'Blender Bridge'
    bl_idname = 'VIEW3D_PT_blender_bridge'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bridge'

    def draw(self, context):
        if runtime._runtime:
            state = runtime._runtime.state
            self.layout.label(text=f"Session: {state.session[:8]}")
            self.layout.label(text=f"Revision: {state.revision}")
            self.layout.label(text=f"Port: {runtime._runtime.server.server_port}")
            from . import __version__
            self.layout.label(text=f"Native tools: {__version__}")
            self.layout.label(text=f"Active job: {state.active_job or 'none'}")
            summary=state.output_root/'.bridge'/'modeling-status.json'
            if summary.is_file():
                try:
                    model=json.loads(summary.read_text(encoding='utf-8'));box=self.layout.box()
                    box.label(text=f"Asset: {model.get('asset_id','-')} / R{model.get('candidate_revision','-')}")
                    box.label(text=f"Reference: {model.get('reference_id','-')}")
                    box.label(text=f"Phase: {model.get('phase','-')}")
                    box.label(text=f"Open differences: {len(model.get('open_issues') or [])}")
                    images=model.get('images') or [];box.label(text=f"Review images: {len(images)}")
                    if images:
                        button=box.operator('blender_bridge.open_artifact',text='Open latest review image');button.path=images[0]['path']
                    box.label(text='User acceptance remains separate')
                except (OSError,ValueError):self.layout.label(text='Modeling status unavailable')
            checkpoints=list((state.output_root/'checkpoints').glob('*/checkpoint.json'))
            self.layout.label(text=f"Checkpoints: {len(checkpoints)}")
            self.layout.operator('blender_bridge.checkpoint_selection')
            button=self.layout.operator('blender_bridge.open_artifact',text='Open output directory');button.path=str(state.output_root)
            self.layout.operator('blender_bridge.stop')
        else:
            self.layout.operator('blender_bridge.start')


class BBOpenArtifact(bpy.types.Operator):
    bl_idname='blender_bridge.open_artifact'
    bl_label='Open Blender Bridge Artifact'
    path:StringProperty()

    def execute(self,context):
        if not runtime._runtime:return {'CANCELLED'}
        path=Path(self.path).resolve();root=runtime._runtime.state.output_root
        if not path.is_relative_to(root) or not path.exists():self.report({'ERROR'},'Artifact outside current output root or missing');return {'CANCELLED'}
        bpy.ops.wm.path_open(filepath=str(path));return {'FINISHED'}


class BBCheckpointSelection(bpy.types.Operator):
    bl_idname='blender_bridge.checkpoint_selection'
    bl_label='Checkpoint Selected Objects'

    def execute(self,context):
        if not runtime._runtime or not context.selected_objects:self.report({'ERROR'},'Select exact objects in a running Bridge session');return {'CANCELLED'}
        state=runtime._runtime.state
        state.submit({'operation':'checkpoint.create','args':{'label':'Sidebar selection','objects':[o.name for o in context.selected_objects]},'session':state.session,'revision':state.revision,'request_id':str(uuid.uuid4())})
        return {'FINISHED'}


CLASSES = (BBPreferences, BBStart, BBStop, BBOpenArtifact, BBCheckpointSelection, BBPanel)


def register():
    for cls in CLASSES: bpy.utils.register_class(cls)


def unregister():
    runtime.stop()
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)

