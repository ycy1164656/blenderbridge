"""Persistent agent-authored modeling loop. No automatic visual pass."""
import copy
import hashlib
import json
import time
from .storage import sha
from .references import safe_id
from ..client import connect
from ..catalog import OPS,validate
from ..core import BridgeError


class ModelingOps:
    def _model(self,identity):return self.store.get('modeling',identity)

    def _client_context(self,session,revision):
        if not session or type(revision) is not int:raise BridgeError('CONTEXT_REQUIRED','Exact session and revision required for modeling')
        client=connect(session,self.store.config.get('sessions_dir'));health=client.call('health')
        if health['revision']!=revision:raise BridgeError('STALE_REVISION',f"Expected revision {revision}; current {health['revision']}. Inspect before submitting new work.")
        return client,health

    def _native_wait(self,client,operation,args,revision,rid,model=None,phase=None):
        if model is not None:
            model.update(phase=phase or model['phase'],active_native_request={'id':rid,'operation':operation,'session':client.session,'revision':revision})
            self.store.put('modeling',model['modeling_id'],model)
        job=client.submit(operation,args,revision,rid)
        while job['state'] in ('queued','running'):
            time.sleep(.15);job=client.call('job',{'id':rid})
        if job['state']!='succeeded':
            error=BridgeError('NATIVE_JOB_'+job['state'].upper(),json.dumps(job.get('error',job),ensure_ascii=False));error.details={'native_job':job};raise error
        return job

    def modeling_plan(self,modeling_id,asset_id,reference_id,reference_revision,reference_sha256,objects,steps,views,directory,candidate_revision=1,protected_parts=(),width=960,height=540,assumptions=()):
        safe_id(modeling_id);safe_id(asset_id)
        frozen=self.store.get('reference_frozen',reference_id+':'+str(reference_revision))
        if frozen['frozen_sha256']!=reference_sha256:raise BridgeError('REFERENCE_VERSION_CONFLICT','Reference hash/revision mismatch')
        self.store.get_artifact(frozen['frozen_manifest']['id'])
        if not all(self.store.was_read(v['artifact']['id'],v['artifact']['sha256']) for v in frozen['views']):
            raise BridgeError('REFERENCE_NOT_READ','Read the actual frozen reference images before authoring a modeling plan')
        client,health=self._client_context(self.request.get('session'),self.request.get('revision'))
        for step in steps:
            spec=OPS.get(step['operation'])
            if not spec or spec['execution_domain']!='blender_main_thread' or step['operation'] in ('python.execute','batch.execute','checkpoint.restore'):raise ValueError('Unsupported modeling step')
            validate(step['args'],spec['inputSchema'])
        if not 16<=width<=2000 or not 16<=height<=2000:raise ValueError('Modeling previews must be 16..2000 pixels')
        plan={'modeling_id':modeling_id,'asset_id':asset_id,'reference_id':reference_id,'reference_revision':reference_revision,'reference_sha256':reference_sha256,
              'candidate_revision':candidate_revision,'objects':objects,'steps':steps,'views':views,'directory':directory,'protected_parts':list(protected_parts),
              'width':width,'height':height,'assumptions':list(assumptions),'session':health['session'],'revision':health['revision'],'phase':'planned','history':[],
              'created':time.time(),'open_issues':[],'user_visual_acceptance':'pending','ue_validation':'not_run','output_root':health['output_root']}
        artifact=self.store.json_artifact(f'modeling/{modeling_id}/plan.json',plan)
        plan['plan_artifact']=artifact;self.store.put('modeling',modeling_id,plan,create=True)
        self._publish_ui(plan)
        return plan

    def _publish_ui(self,model):
        # Small read-only summary consumed by Blender sidebar; no host bpy access.
        from pathlib import Path
        from ..core import atomic_json
        root=Path(model['output_root']).resolve()
        if root==self.store.root or root in [Path(v.get('output_root','')).resolve() for v in self.store.records('modeling')]:
            atomic_json(root/'.bridge'/'modeling-status.json',{k:model.get(k) for k in ('modeling_id','asset_id','reference_id','candidate_revision','phase','open_issues','images','directory','user_visual_acceptance')})

    def _render_model(self,model,client,revision,round_id):
        directory=f"{model['directory']}/r{model['candidate_revision']:04d}"
        result=self._native_wait(client,'preview.multiview',{'objects':model['objects'],'views':model['views'],'directory':directory,'width':model['width'],'height':model['height'],'style':'clay'},revision,round_id+':views',model,'rendering')
        images=result['result']['images'];self.store.import_artifacts(images,model['output_root'])
        model.update(phase='awaiting_visual_review',images=images,revision=result['revision'],session=result['session'],active_native_request=None)
        model['history'].append({'event':'rendered','candidate_revision':model['candidate_revision'],'native_request':result['id'],'images':[a['id'] for a in images],'at':time.time()})
        self.store.put('modeling',model['modeling_id'],model);self._publish_ui(model)
        return model

    def modeling_submit(self,modeling_id):
        model=self._model(modeling_id)
        if model['phase']!='planned':raise BridgeError('MODELING_PHASE','Submit accepts only planned tasks; inspect the original job after disconnect')
        if self.request.get('session')!=model['session'] or self.request.get('revision')!=model['revision']:raise BridgeError('CONTEXT_CONFLICT','Submit context must match the saved plan')
        client,health=self._client_context(model['session'],model['revision'])
        rid=self.request['request_id']
        try:
            result=self._native_wait(client,'batch.execute',{'steps':model['steps'],'protected_parts':model['protected_parts']},model['revision'],rid+':batch',model,'modeling')
            model['history'].append({'event':'batch','native_request':result['id'],'result':result['result'],'at':time.time()});model['revision']=result['revision']
            return self._render_model(model,client,result['revision'],rid)
        except Exception as exc:
            model.update(phase='needs_diagnosis',error={'code':getattr(exc,'code','ERROR'),'message':str(exc)})
            self.store.put('modeling',modeling_id,model);self._publish_ui(model);raise

    def modeling_inspect(self,modeling_id):
        model=self._model(modeling_id)
        if model.get('active_native_request'):
            record=model['active_native_request']
            try:model['active_native_job']=connect(record['session'],self.store.config.get('sessions_dir')).call('job',{'id':record['id']})
            except Exception as exc:model['active_native_job']={'state':'unreachable','message':str(exc),'retry_write':False}
        return model

    def modeling_reconnect(self,modeling_id):
        model=self._model(modeling_id)
        if model['phase']!='awaiting_visual_review' or model.get('active_native_request'):raise BridgeError('MODELING_PHASE','Reconnect requires a completed pending render set; diagnose in-flight/unknown writes separately')
        session=self.request.get('session');revision=self.request.get('revision')
        self._client_context(session,revision)
        candidate=copy.deepcopy(model);candidate.update(session=session,revision=revision)
        self._validate_model_images(candidate,[a['id'] for a in candidate['images']],require_read=False)
        candidate['history'].append({'event':'reconnected_without_replay','previous_session':model['session'],'previous_revision':model['revision'],'session':session,'revision':revision,'at':time.time(),'open_issue_ids':[i['issue_id'] for i in model.get('open_issues',[])]})
        self.store.put('modeling',modeling_id,candidate);self._publish_ui(candidate)
        return candidate

    def _validate_model_images(self,model,artifact_ids,require_read=True):
        expected={a['id']:a for a in model.get('images',[])}
        if set(artifact_ids)!=set(expected):raise BridgeError('REVIEW_IMAGE_MISMATCH','Review must contain exactly this candidate fixed-view image set')
        client,health=self._client_context(model['session'],model['revision'])
        result=self._native_wait(client,'scene.fingerprint',{'objects':model['objects']},model['revision'],self.request['request_id']+':reviewhash')
        hashes={value['name']:value['sha256'] for name,value in result['result']['objects'].items()}
        for aid in artifact_ids:
            artifact=self.store.get_artifact(aid)
            if require_read and not self.store.was_read(aid,artifact['sha256']):raise BridgeError('IMAGE_NOT_READ','Deliver actual images before recording visual observations')
            if artifact['sha256']!=expected[aid]['sha256']:raise BridgeError('REVIEW_STALE','Candidate image changed')
            for name,digest in artifact['provenance']['object_hashes'].items():
                if hashes.get(name)!=digest:raise BridgeError('REVIEW_STALE','Model changed after rendering')
        self._native_wait(client,'preview.validate',{'artifact_ids':artifact_ids},model['revision'],self.request['request_id']+':cameras')
        return expected

    def review_record(self,modeling_id,review_id,candidate_revision,artifact_ids,issues,summary,decision,reviewer):
        safe_id(review_id);model=self._model(modeling_id)
        if model['phase']!='awaiting_visual_review':raise BridgeError('REVIEW_PHASE','Task is not awaiting visual review')
        if candidate_revision!=model['candidate_revision']:raise BridgeError('REVIEW_STALE','Candidate revision mismatch')
        if not summary.strip():raise ValueError('Actual visual observations are required')
        expected=self._validate_model_images(model,artifact_ids)
        if decision=='self_review_passed' and any(i['status']=='open' for i in issues):raise ValueError('Self pass cannot retain open differences')
        old_open={i['issue_id'] for i in model.get('open_issues',[]) if i['status']=='open'}
        if old_open-set(i['issue_id'] for i in issues):raise BridgeError('ISSUE_DROPPED','Carry over or explicitly resolve every existing open issue')
        record={'review_id':review_id,'modeling_id':modeling_id,'candidate_revision':candidate_revision,'artifact_ids':artifact_ids,
                'artifact_hashes':{i:a['sha256'] for i,a in expected.items()},'reference_sha256':model['reference_sha256'],'issues':issues,'summary':summary,
                'decision':decision,'reviewer':reviewer,'created':time.time(),'user_visual_acceptance':'pending','fixture_review_is_art_acceptance':False}
        artifact=self.store.json_artifact(f'modeling/{modeling_id}/reviews/{review_id}.json',record);record['manifest']=artifact
        self.store.put('review',review_id,record,create=True);model['latest_review']=review_id;model['open_issues']=[i for i in issues if i['status']=='open']
        model['history'].append({'event':'review','review_id':review_id,'at':time.time()});self.store.put('modeling',modeling_id,model);self._publish_ui(model)
        return record

    def modeling_resume(self,modeling_id,review_id,steps=()):
        model=self._model(modeling_id);review=self.store.get('review',review_id)
        if model['phase']!='awaiting_visual_review' or model.get('latest_review')!=review_id:raise BridgeError('REVIEW_STALE','Only the latest review of the pending candidate can resume')
        if review['modeling_id']!=modeling_id or review['candidate_revision']!=model['candidate_revision']:raise BridgeError('REVIEW_STALE','Review version mismatch')
        if self.request.get('session')!=model['session'] or self.request.get('revision')!=model['revision']:raise BridgeError('CONTEXT_CONFLICT','Resume requires the exact current task session/revision')
        self._validate_model_images(model,review['artifact_ids'])
        client,health=self._client_context(model['session'],model['revision'])
        if review['decision']=='self_review_passed':
            if steps:raise ValueError('Passed review may advance without edits; create a new iteration explicitly before further changes')
            model['phase']='ready_for_technical_validation';model['visual_self_review']='fixture_protocol_only' if review['reviewer']=='fixture_protocol' else 'passed'
            self.store.put('modeling',modeling_id,model);self._publish_ui(model);return model
        if not steps:raise ValueError('Needs-work review requires explicit corrective native steps')
        result=self._native_wait(client,'batch.execute',{'steps':list(steps),'protected_parts':model['protected_parts']},model['revision'],self.request['request_id']+':fix',model,'refining')
        model['history'].append({'event':'fix','review_id':review_id,'native_request':result['id'],'result':result['result'],'at':time.time()})
        model['candidate_revision']+=1;model['revision']=result['revision'];model.pop('latest_review',None)
        return self._render_model(model,client,result['revision'],self.request['request_id'])
