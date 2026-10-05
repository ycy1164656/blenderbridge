"""Fast main-thread geometry regression; uses the same Operations implementation."""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from blender_bridge.core import RuntimeState
from blender_bridge.operations import Operations

ops = Operations(RuntimeState(Path(tempfile.gettempdir())/'blender-bridge-geometry'))
for label,indices in [('Single',[5]),('Adjacent',[1,5]),('All',list(range(6)))]:
    ops.execute('mesh.create',{'name':label,'vertices':[[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]],
                'faces':[[0,3,2,1],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7],[4,5,6,7]]})
    ops.execute('mesh.edit',{'object':label,'action':'extrude_faces','indices':indices,'offset':[.15,-.2,.5]})
    h = ops.execute('mesh.inspect',{'object':label})['health']
    assert h['zero_area_faces'] == 0 and h['non_manifold_edges'] == 0 and h['loose_vertices'] == 0, (label,h)
    print('GEOMETRY_PASS',label,h)
