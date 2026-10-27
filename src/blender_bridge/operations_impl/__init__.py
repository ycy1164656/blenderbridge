"""Typed native implementation assembled only inside Blender's main thread."""
from .objects import ObjectOps
from .geometry import GeometryOps
from .selection import SelectionOps
from .modifiers import ModifierOps
from .preview import PreviewOps
from .checkpoints import CheckpointOps
from .surface import SurfaceOps
from .rigging import RigOps
from .game import GameOps
from .textures import TextureOps
from .node_graph import NodeGraphOps


class NativeOperations(ObjectOps, GeometryOps, SelectionOps, ModifierOps, PreviewOps, CheckpointOps, SurfaceOps, RigOps, GameOps, TextureOps, NodeGraphOps):
    pass
