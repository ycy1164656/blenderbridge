import argparse
import json
from pathlib import Path
import sys
import uuid
from .client import connect, discover
from .host.gateway import Gateway
from .host.storage import configuration


def main():
    p = argparse.ArgumentParser(description='Blender Bridge: one typed native/Host catalog, durable jobs and visual review workflow')
    p.add_argument('--session')
    p.add_argument('--sessions-dir')
    p.add_argument('--config')
    p.add_argument('--output-root')
    p.add_argument('--revision',type=int)
    p.add_argument('--request-id')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('discover','health','catalog','artifacts'): sub.add_parser(name)
    for name in ('doctor','capabilities'):
        sub.add_parser(name).add_argument('--json',action='store_true')
    job=sub.add_parser('job');job.add_argument('action_or_id');job.add_argument('--id',dest='job_id')
    sub.add_parser('cancel').add_argument('id')
    s = sub.add_parser('execute')
    s.add_argument('operation')
    s.add_argument('--args', default='{}', help='JSON object, or @path.json')
    s.add_argument('--revision', type=int,default=argparse.SUPPRESS)
    s.add_argument('--request-id',default=argparse.SUPPRESS)
    s.add_argument('--wait', type=float, default=30)
    for group in ('reference','modeling','review','worker','delivery'):
        parser=sub.add_parser(group);parser.add_argument('action');parser.add_argument('--request');parser.add_argument('--file');parser.add_argument('--plan');parser.add_argument('--manifest');parser.add_argument('--id');parser.add_argument('--review');parser.add_argument('--steps');parser.add_argument('--wait',type=float,default=30)
    verify=sub.add_parser('verify');verify.add_argument('--suite',default='native-modeling');verify.add_argument('--run-fixture',action='store_true');verify.add_argument('--wait',type=float,default=30)
    validate_parser=sub.add_parser('validate');validate_parser.add_argument('--asset',required=True);validate_parser.add_argument('--profile',required=True)
    report=sub.add_parser('report');report.add_argument('--asset',required=True);report.add_argument('--output',required=True)
    a = p.parse_args()
    try:
        config=configuration(a.config);gateway=Gateway(a.output_root,config,a.sessions_dir)
        def load_file(path):
            value=json.loads(Path(path.removeprefix('@')).read_text(encoding='utf-8-sig'))
            return value['result'] if isinstance(value,dict) and value.get('state')=='succeeded' and 'result' in value else value
        def execute(operation,args,wait=30):return gateway.execute(operation,args,a.request_id or str(uuid.uuid4()),a.session,a.revision,wait)
        if a.command == 'discover':
            result = [h for c,h in discover(a.sessions_dir)]
        elif a.command in ('doctor','capabilities'):result=execute('system.'+a.command,{})
        elif a.command=='catalog':result=gateway.catalog(a.session)
        elif a.command=='artifacts':result=gateway.artifacts(a.session)
        elif a.command=='health':result=gateway.client(a.session).call('health')
        elif a.command=='job':result=gateway.job(a.job_id if a.action_or_id=='inspect' else a.action_or_id,a.session)
        elif a.command=='cancel':result=gateway.job(a.id,a.session,True)
        elif a.command=='verify':result=execute('system.verify',{'suite':a.suite,'run_fixture':a.run_fixture},a.wait)
        elif a.command=='validate':
            asset=load_file(a.asset);objects=[o['name'] if isinstance(o,dict) else o for o in asset['objects']]
            result=execute('game.validate',{'objects':objects,'profile':load_file(a.profile)})
        elif a.command=='report':result=execute('delivery.report',{'manifest':str(Path(a.asset).resolve()),'path':a.output})
        elif a.command in ('reference','modeling','review','worker','delivery'):
            operation=a.command+'.'+a.action;args=load_file(a.request or a.file) if a.request or a.file else {}
            if a.plan:args['modeling_id']=load_file(a.plan)['modeling_id']
            if a.manifest:args['manifest']=str(Path(a.manifest).resolve())
            if a.id:args[{'reference':'reference_id','modeling':'modeling_id','review':'review_id','worker':'worker_id','delivery':'manifest'}[a.command]]=a.id
            if a.review:args['review_id']=load_file(a.review)['review_id']
            if a.steps:args['steps']=load_file(a.steps)
            result=execute(operation,args,a.wait)
        else:
            args = load_file(a.args) if a.args.startswith('@') else json.loads(a.args)
            result=execute(a.operation,args,a.wait)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if isinstance(result, dict) and result.get('state') == 'failed': sys.exit(1)
    except Exception as exc:
        print(json.dumps({'error': {'code':getattr(exc,'code','CLIENT_ERROR'), 'message':str(exc)}}))
        sys.exit(1)


if __name__ == '__main__': main()

