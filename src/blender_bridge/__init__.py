"""Host imports do not load bpy. This package also installs as a Blender add-on."""
__version__ = "0.3.0"
bl_info = {"name": "Blender Bridge", "author": "BlenderBridge contributors",
           "version": (0, 3, 0), "blender": (4, 2, 0), "location": "View3D > Sidebar > Bridge",
           "description": "Native visual modeling loop and game asset tools", "category": "Interface"}


def register():
    from .addon import register as impl
    impl()


def unregister():
    from .addon import unregister as impl
    impl()

