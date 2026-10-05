import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid
from .core import BridgeError, default_sessions


class Client:
    def __init__(self, descriptor):
        self.descriptor = descriptor
        self.session = descriptor['session']
        endpoint = descriptor['endpoint']
        from urllib.parse import urlparse
        parsed = urlparse(endpoint)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path not in ('', '/') or not parsed.port:
            raise BridgeError('BAD_DISCOVERY', 'Only loopback HTTP runtime endpoints are accepted')
        self.endpoint = endpoint.rstrip('/')

    def call(self, route, data=None, timeout=5):
        request = urllib.request.Request(self.endpoint + '/' + route, json.dumps(data or {}).encode(),
                   headers={'Content-Type':'application/json', 'Authorization':'Bearer ' + self.descriptor['token']})
        # Avoid environment proxies for the local runtime.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=timeout) as response: result = json.load(response)
        except urllib.error.HTTPError as exc:
            result = json.load(exc)
        if not result['ok']:
            raise BridgeError(result['error']['code'], result['error']['message'])
        return result['result']

    def submit(self, operation, args, revision=None, request_id=None):
        rid = request_id or str(uuid.uuid4())
        body = {'operation':operation, 'args':args, 'session':self.session, 'request_id':rid}
        if revision is not None: body['revision'] = revision
        try:
            return self.call('submit', body)
        except (TimeoutError, urllib.error.URLError, ConnectionError) as exc:
            raise BridgeError('OUTCOME_UNKNOWN', f'Submit may have been accepted. Query job {rid}; do not create a new request ID. {exc}') from exc

    def wait(self, rid, timeout=30):
        deadline = time.monotonic() + timeout
        while True:
            job = self.call('job', {'id':rid})
            if job['state'] not in ('queued','running') or time.monotonic() >= deadline: return job
            time.sleep(0.1)


def discover(directory=None):
    found = []
    for path in sorted(Path(directory or default_sessions()).glob('*.json')):
        try:
            descriptor = json.loads(path.read_text(encoding='utf-8'))
            client = Client(descriptor)
            health = client.call('health', timeout=0.6)
            if health['session'] == descriptor['session'] and health['pid'] == descriptor['pid']:
                found.append((client, health))
        except (OSError, ValueError, KeyError, BridgeError):
            continue
    return found


def connect(session=None, directory=None):
    found = discover(directory)
    matches = [pair for pair in found if session is None or pair[1]['session'] == session]
    if len(matches) != 1:
        raise BridgeError('SESSION_SELECTION', f'Expected one matching session, found {len(matches)}. Discover and select the exact session.')
    return matches[0][0]

