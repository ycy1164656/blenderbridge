import argparse
import json
from pathlib import Path
import sys
from .client import connect, discover


def main():
    p = argparse.ArgumentParser(description='Blender Bridge: discover, inspect catalog, submit and query jobs')
    p.add_argument('--session')
    p.add_argument('--sessions-dir')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('discover','health','catalog','artifacts'): sub.add_parser(name)
    for name in ('job','cancel'):
        sub.add_parser(name).add_argument('id')
    s = sub.add_parser('execute')
    s.add_argument('operation')
    s.add_argument('--args', default='{}', help='JSON object, or @path.json')
    s.add_argument('--revision', type=int)
    s.add_argument('--request-id')
    s.add_argument('--wait', type=float, default=30)
    a = p.parse_args()
    try:
        if a.command == 'discover':
            result = [h for c,h in discover(a.sessions_dir)]
        else:
            c = connect(a.session, a.sessions_dir)
            if a.command == 'execute':
                args = json.loads(Path(a.args[1:]).read_text(encoding='utf-8-sig') if a.args.startswith('@') else a.args)
                result = c.submit(a.operation, args, a.revision, a.request_id)
                if a.wait: result = c.wait(result['id'], max(0,min(a.wait,60)))
            else:
                result = c.call(a.command, {'id':a.id} if a.command in ('job','cancel') else {})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if isinstance(result, dict) and result.get('state') == 'failed': sys.exit(1)
    except Exception as exc:
        print(json.dumps({'error': {'code':getattr(exc,'code','CLIENT_ERROR'), 'message':str(exc)}}))
        sys.exit(1)


if __name__ == '__main__': main()

