import json,uuid
from blender_bridge.client import connect
c=connect();h=c.call('health');j=c.wait(c.submit('scene.save',{'path':'session/full-upgrade-before-installed-restart.blend','copy':True},h['revision'],str(uuid.uuid4()))['id'],60)
assert j['state']=='succeeded',j
print(json.dumps({'session':h['session'],'result':j['result']}))
