import json
from pathlib import Path
import uuid
from PIL import Image
import pytest
from blender_bridge.host.storage import Store,sha
from blender_bridge.host.operations import HostOperations
from blender_bridge.host.jobs import HostJobs
from blender_bridge.host.gateway import Gateway
from blender_bridge.core import BridgeError


@pytest.fixture
def host(tmp_path):
    source=tmp_path/'input';source.mkdir();out=tmp_path/'output'
    store=Store(out,{'output_root':str(out),'read_roots':[str(source)],'blender':'missing-blender'})
    return HostOperations(store,{'request_id':'unit-host-001'}),source


def test_reference_rgba_is_not_a_mask_and_original_is_preserved(host):
    host,source=host;path=source/'ref.png';Image.new('RGBA',(80,60),(120,50,40,255)).save(path);digest=sha(path)
    host.reference_register('test',[{'label':'front','path':str(path)}],approval_status='fixture_only')
    with pytest.raises(BridgeError,match='fully opaque'):host.reference_mask('test','front','alpha')
    masked=host.reference_mask('test','front','polygon',polygon=[[10,10],[60,10],[60,50],[10,50]])
    assert masked['revision']==2 and masked['views'][0]['effective_mask']
    assert sha(path)==digest


def test_reference_crop_calibration_landmarks_and_freeze(host):
    host,source=host;path=source/'ref.png';Image.new('RGBA',(100,50),(10,20,30,255)).save(path)
    host.reference_register('test',[{'label':'three_quarter','path':str(path),'landmarks':{'eye':[40,20]}}],approval_status='fixture_only',unknown_regions=['back'])
    crop=host.reference_crop('test','three_quarter',[20,10,80,40]);assert crop['views'][0]['landmarks']['eye']==[20,10]
    calibrated=host.reference_calibrate('test','three_quarter',120,120,ground_line=30,center_line=30)
    assert calibrated['views'][0]['landmarks']['eye']==[40,50]
    frozen=host.reference_freeze('test');assert frozen['frozen']
    Image.new('RGBA',(100,50),(200,10,50,255)).save(path)
    assert host.reference_validate('test')['state']=='valid_with_unknowns'
    assert host.reference_freeze('test')['frozen_sha256']==frozen['frozen_sha256']
    assert any(w['code']=='INCOMPLETE_ORTHOGRAPHIC_SET' for w in frozen['validation']['warnings'])


def test_conflicting_views_are_not_silently_padded(host):
    host,source=host;path=source/'ref.png';Image.new('RGB',(64,64),'red').save(path)
    host.reference_register('duplicate',[{'label':'left','path':str(path),'pose_id':'pose1'},{'label':'right','path':str(path),'pose_id':'pose2'}])
    errors=host.reference_validate('duplicate')['errors']
    assert {e['code'] for e in errors}=={'DUPLICATE_VIEW_CONTENT','POSE_CONFLICT'}
    with pytest.raises(BridgeError):host.reference_freeze('duplicate')


def test_artifacts_detect_changed_file_and_record_delivery_not_acceptance(host):
    host,source=host;path=host.store.output('image.png');Image.new('RGB',(20,20),'blue').save(path);artifact=host.store.artifact(path,'image/png')
    assert not host.store.was_read(artifact['id'],artifact['sha256'])
    meta,data=host.store.read_image(artifact['id']);assert data.startswith(b'\x89PNG') and host.store.was_read(meta['id'],meta['sha256'])
    assert 'user_visual_acceptance' not in meta
    Image.new('RGB',(20,20),'red').save(path)
    with pytest.raises(BridgeError,match='changed'):host.store.read_image(artifact['id'])


def test_host_ids_deduplicate_and_reject_conflicts(host):
    host,source=host;jobs=HostJobs(host.store)
    first=jobs.submit('system.capabilities',{},'stable-host-job')
    assert first['state']=='succeeded'
    assert jobs.submit('system.capabilities',{},'stable-host-job')==first
    with pytest.raises(BridgeError,match='different request'):jobs.submit('system.doctor',{},'stable-host-job')


def test_path_escape_and_compare_metric_applicability(host):
    host,source=host
    with pytest.raises(BridgeError):host.store.output('../escape.png')
    images=[]
    for name,color in [('a','red'),('b','blue')]:
        path=host.store.output(name+'.png');Image.new('RGB',(32,32),color).save(path);images.append(host.store.artifact(path,'image/png')['id'])
    result=host.compare_views(images[:1],images[1:],'compare.png')
    assert result['metrics'][0]['state']=='not_applicable' and result['metrics'][0]['art_score'] is None
    with pytest.raises(ValueError,match='Overlay requires'):host.compare_views(images[:1],images[1:],'overlay.png',overlay=True)


def test_gateway_native_context_cannot_be_omitted(host):
    host,source=host;gateway=Gateway(host.store.root,host.store.config)
    with pytest.raises(BridgeError,match='session'):gateway.execute('mesh.create',{'name':'Mesh','vertices':[[0,0,0],[1,0,0],[0,1,0]],'faces':[[0,1,2]]},'missing-context')


def test_cancelled_worker_is_not_a_successful_host_job(host,monkeypatch):
    host,source=host
    def controlled_cancel(self,name,args):raise BridgeError('WORKER_CANCELLED','exact owned cancellation')
    monkeypatch.setattr(HostOperations,'execute',controlled_cancel)
    job=HostJobs(host.store).submit('system.capabilities',{},'controlled-cancel-status')
    assert job['state']=='cancelled' and 'result' not in job


def test_doctor_does_not_require_neural_models_and_reports_missing_blender(host):
    host,source=host;result=host.system_doctor()
    assert result['state']=='missing_required_dependency'
    assert not result['neural_3d_required'] and not result['weights_downloaded']


def test_reconnect_preserves_record_when_current_evidence_rejects(host,monkeypatch):
    host,source=host
    previous={'modeling_id':'pending','phase':'awaiting_visual_review','session':'old','revision':9,'images':[{'id':'image1'}],'history':[],'open_issues':[{'issue_id':'retain-me'}]}
    host.store.put('modeling','pending',previous);host.request.update(session='replacement',revision=0)
    monkeypatch.setattr(host,'_client_context',lambda s,r:(None,{}))
    def reject(*args,**kwargs):raise BridgeError('REVIEW_STALE','Current source changed')
    monkeypatch.setattr(host,'_validate_model_images',reject)
    with pytest.raises(BridgeError,match='Current source changed'):host.modeling_reconnect('pending')
    assert host.store.get('modeling','pending')==previous
