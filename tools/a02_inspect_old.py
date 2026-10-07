import json
import uuid
from pathlib import Path
from blender_bridge.host.gateway import Gateway
from blender_bridge.host.storage import sha
from blender_bridge.core import atomic_json
source=Path('C:/dev/ShooterRoyal_5_8_DirectUpgrade/SourceArt/AtlasV3_20261004/Revision02/UpperBodyStudy/COLOSSUS_R3_UpperBody.blend')
job=Gateway().execute('worker.submit',{'blend':str(source),'expected_sha256':sha(source),'operation':'scene.inspect','args':{'limit':500},'directory':'a02/old-inspect'},str(uuid.uuid4()),None,None,60)
atomic_json(Path('artifacts/native-modeling/a02/old-inspect-job.json'),job)
print(json.dumps(job if job['state']!='succeeded' else job['result']['result'],ensure_ascii=False))
