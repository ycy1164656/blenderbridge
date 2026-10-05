from pathlib import Path
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
            self.layout.operator('blender_bridge.stop')
        else:
            self.layout.operator('blender_bridge.start')


CLASSES = (BBPreferences, BBStart, BBStop, BBPanel)


def register():
    for cls in CLASSES: bpy.utils.register_class(cls)


def unregister():
    runtime.stop()
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)

