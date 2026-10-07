"""Readonly originals, explicit derived transforms, immutable reference inputs."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import time
from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageStat
from .storage import sha
from ..core import BridgeError, atomic_json


def safe_id(value):
    if not value or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.' for c in value) or value in ('.','..'):
        raise ValueError('IDs require letters, digits, underscore, dot or dash')
    return value


def image_info(path):
    with Image.open(path) as image:
        image.load();rgba=image.convert('RGBA');extrema=rgba.getchannel('A').getextrema()
        return {'width':image.width,'height':image.height,'mode':image.mode,'alpha_range':list(extrema),'effective_mask':extrema[0]<255,
                'fully_transparent':extrema[1]==0,'sha256':sha(path)}


def multiply(a,b):return [[sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def transform_landmarks(landmarks,matrix):
    result={}
    for name,value in landmarks.items():
        if isinstance(value,(list,tuple)) and len(value)==2:result[name]=[matrix[0][0]*value[0]+matrix[0][1]*value[1]+matrix[0][2],matrix[1][0]*value[0]+matrix[1][1]*value[1]+matrix[1][2]]
        else:raise ValueError('Landmarks must be named pixel [x,y] pairs')
    return result


class ReferenceOps:
    def _reference(self,identity):return self.store.get('reference',identity)

    def _publish_reference(self,record,create=False):
        revision=record['revision'];identity=record['reference_id']
        manifest=self.store.json_artifact(f'references/{safe_id(identity)}/r{revision:04d}/reference.json',record)
        record['manifest']=manifest
        self.store.put('reference_version',identity+':'+str(revision),record,create=True)
        return self.store.put('reference',identity,record,create=create)

    def reference_register(self,reference_id,views,approval_status='pending_user_review',approval_evidence=None,pose_id=None,height_m=None,unknown_regions=(),asset_type='unspecified'):
        safe_id(reference_id)
        try:self._reference(reference_id)
        except BridgeError as exc:
            if exc.code!='RECORD_NOT_FOUND':raise
        else:raise BridgeError('ID_CONFLICT','Reference already exists')
        if approval_status=='approved' and not approval_evidence:raise ValueError('Approved reference requires explicit approval provenance')
        labels=[v['label'] for v in views]
        if len(labels)!=len(set(labels)):raise ValueError('Reference view labels must be unique; use a separate reference ID for detail sets')
        prepared=[]
        for view in views:
            source=self.store.input(view['path']);metadata=image_info(source)
            prepared.append((view,source,metadata))
        entries=[]
        for view,source,metadata in prepared:
            target=self.store.output(f'references/{reference_id}/r0001/{view["label"]}{source.suffix.lower()}')
            shutil.copy2(source,target)
            kind={'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}.get(Image.open(target).format)
            if not kind:raise ValueError('PNG/JPEG/WebP references required')
            artifact=self.store.artifact(target,kind,{'original_path':str(source),'original_sha256':metadata['sha256']})
            entries.append({**view,**metadata,'path':str(target),'original_path':str(source),'original_sha256':metadata['sha256'],'artifact':artifact,
                            'pose_id':view.get('pose_id',pose_id),'transforms':[],'original_to_current':[[1,0,0],[0,1,0],[0,0,1]],'landmarks':view.get('landmarks',{})})
        record={'reference_id':reference_id,'revision':1,'views':entries,'approval_status':approval_status,'approval_evidence':approval_evidence,
                'pose_id':pose_id,'height_m':height_m,'unknown_regions':list(unknown_regions),'asset_type':asset_type,'created':time.time(),
                'coordinates':{'pixel_origin':'top_left','x':'image_right','y':'image_down','view_labels':'subject anatomical/world views; not image side'},'frozen':False}
        return self._publish_reference(record,True)

    def _derive_reference(self,reference_id,view,operation,params,transformer):
        record=copy.deepcopy(self._reference(reference_id));record.pop('manifest',None);record.pop('frozen_manifest',None);record.pop('frozen_sha256',None)
        record['revision']+=1;record['frozen']=False
        selected=next((v for v in record['views'] if v['label']==view),None)
        if not selected:raise ValueError('Reference view not found')
        source=self.store.get_artifact(selected['artifact']['id'])
        with Image.open(source['path']) as raw:image=raw.convert('RGBA')
        output,matrix,extra=transformer(image,selected)
        target=self.store.output(f'references/{safe_id(reference_id)}/r{record["revision"]:04d}/{safe_id(view)}.png','.png');output.save(target)
        selected.update(extra);selected.update(image_info(target));selected['path']=str(target)
        selected['original_to_current']=multiply(matrix,selected['original_to_current']);selected['landmarks']=transform_landmarks(selected.get('landmarks',{}),matrix)
        selected['transforms'].append({'operation':operation,'parameters':params,'matrix':matrix,'source_sha256':source['sha256']})
        selected['artifact']=self.store.artifact(target,'image/png',{'reference_id':reference_id,'reference_revision':record['revision'],'operation':operation,'source_artifact':source['id'],'source_sha256':source['sha256']})
        return self._publish_reference(record)

    def reference_crop(self,reference_id,view,rectangle):
        def apply(image,record):
            left,top,right,bottom=rectangle
            if not 0<=left<right<=image.width or not 0<=top<bottom<=image.height:raise ValueError('Crop must be a nonempty rectangle inside image')
            return image.crop(rectangle),[[1,0,-left],[0,1,-top],[0,0,1]],{}
        return self._derive_reference(reference_id,view,'crop',{'rectangle':rectangle},apply)

    def reference_mask(self,reference_id,view,mode,color=None,tolerance=15,polygon=None,path=None):
        def apply(image,record):
            if mode=='alpha':mask=image.getchannel('A')
            elif mode=='color':
                if color is None:raise ValueError('Explicit background color required')
                target=Image.new('RGB',image.size,tuple(color));difference=ImageChops.difference(image.convert('RGB'),target)
                channels=difference.split();maximum=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2]);mask=maximum.point(lambda v:0 if v<=tolerance else 255)
                mask=ImageChops.multiply(mask,image.getchannel('A'))
            elif mode=='polygon':
                if not polygon:raise ValueError('Explicit polygon required')
                mask=Image.new('L',image.size,0);ImageDraw.Draw(mask).polygon([tuple(p) for p in polygon],fill=255)
            else:
                if not path:raise ValueError('Mask image path required')
                with Image.open(self.store.input(path)) as source:mask=source.convert('L')
                if mask.size!=image.size:raise ValueError('Mask size must match current view')
            lo,hi=mask.getextrema()
            if lo==255:raise BridgeError('MASK_INEFFECTIVE','Image is still fully opaque; RGBA mode alone is not background removal')
            if hi==0:raise BridgeError('MASK_EMPTY','Mask removes the entire image')
            result=image.copy();result.putalpha(mask)
            return result,[[1,0,0],[0,1,0],[0,0,1]],{'mask_method':mode,'mask_effective':True}
        return self._derive_reference(reference_id,view,'mask',{'mode':mode,'color':color,'tolerance':tolerance,'polygon':polygon,'path':path},apply)

    def reference_calibrate(self,reference_id,view,width,height,ground_line=None,center_line=None,landmarks=None,camera=None):
        if not 16<=width<=8192 or not 16<=height<=8192:raise ValueError('Calibration size must be 16..8192')
        def apply(image,record):
            scale=min(width/image.width,height/image.height);size=(round(image.width*scale),round(image.height*scale));left=(width-size[0])//2;top=(height-size[1])//2
            result=Image.new('RGBA',(width,height),(0,0,0,0));result.paste(image.resize(size,Image.Resampling.LANCZOS),(left,top))
            matrix=[[size[0]/image.width,0,left],[0,size[1]/image.height,top],[0,0,1]]
            if landmarks is not None:record['landmarks']=landmarks
            extra={'calibration':{'scale':scale,'ground_line':ground_line*matrix[1][1]+top if ground_line is not None else None,'center_line':center_line*matrix[0][0]+left if center_line is not None else None,'padding':[left,top]}}
            if camera is not None:extra['camera']=camera
            return result,matrix,extra
        return self._derive_reference(reference_id,view,'calibrate',{'width':width,'height':height,'ground_line':ground_line,'center_line':center_line},apply)

    def reference_validate(self,reference_id=None,manifest=None):
        if (reference_id is None)==(manifest is None):raise ValueError('Specify reference_id or manifest')
        record=self._reference(reference_id) if reference_id else json.loads(self.store.input(manifest).read_text(encoding='utf-8-sig'))
        errors=[];warnings=[];digests={};poses=set();labels=set()
        for view in record['views']:
            labels.add(view['label']);poses.add(view.get('pose_id'))
            try:
                path=self.store.input(view['path']);current=image_info(path)
                if current['sha256']!=view['sha256']:errors.append({'code':'REFERENCE_CHANGED','view':view['label']})
                if current['fully_transparent']:errors.append({'code':'EMPTY_VIEW','view':view['label']})
                if view.get('mask_effective') and not current['effective_mask']:errors.append({'code':'MASK_INEFFECTIVE','view':view['label']})
                if not current['effective_mask']:warnings.append({'code':'BACKGROUND_PRESENT','view':view['label']})
                if current['sha256'] in digests:errors.append({'code':'DUPLICATE_VIEW_CONTENT','views':[digests[current['sha256']],view['label']]})
                digests[current['sha256']]=view['label']
            except (BridgeError,OSError,ValueError) as exc:errors.append({'code':'INPUT_INVALID','view':view['label'],'message':str(exc)})
            if not view.get('camera'):warnings.append({'code':'CAMERA_UNKNOWN','view':view['label']})
        poses.discard(None)
        if len(poses)>1:errors.append({'code':'POSE_CONFLICT','poses':sorted(poses)})
        missing=sorted({'front','left','right','back'}-labels)
        if missing:warnings.append({'code':'INCOMPLETE_ORTHOGRAPHIC_SET','missing':missing,'mode':'explicit_partial_reference'})
        if not record.get('height_m'):warnings.append({'code':'PHYSICAL_SCALE_UNKNOWN'})
        return {'reference_id':record['reference_id'],'revision':record['revision'],'state':'invalid' if errors else 'valid_with_unknowns' if warnings else 'valid','errors':errors,'warnings':warnings,'unknown_regions':record.get('unknown_regions',[]),'approved':record.get('approval_status')=='approved','frozen':record.get('frozen',False)}

    def reference_freeze(self,reference_id):
        record=copy.deepcopy(self._reference(reference_id))
        if record.get('frozen'):
            manifest=self.store.get_artifact(record['frozen_manifest']['id'])
            if manifest['sha256']!=record['frozen_sha256']:raise BridgeError('REFERENCE_CHANGED','Frozen manifest changed')
            return record
        validation=self.reference_validate(reference_id)
        if validation['errors']:raise BridgeError('REFERENCE_INVALID',json.dumps(validation['errors']))
        record.pop('manifest',None);record['frozen']=True;record['validation']=validation
        for view in record['views']:
            artifact=self.store.get_artifact(view['artifact']['id']);source=Path(artifact['path'])
            target=self.store.output(f'references/{safe_id(reference_id)}/r{record["revision"]:04d}/frozen/{view["label"]}{source.suffix}')
            shutil.copy2(source,target);view['path']=str(target);view['artifact']=self.store.artifact(target,artifact['kind'],{'frozen_reference':reference_id,'revision':record['revision'],'source_artifact':artifact['id']})
        manifest=self.store.json_artifact(f'references/{reference_id}/r{record["revision"]:04d}/frozen/manifest.json',record)
        record['frozen_manifest']=manifest;record['frozen_sha256']=manifest['sha256']
        self.store.put('reference_frozen',reference_id+':'+str(record['revision']),record,create=True)
        self.store.put('reference',reference_id,record)
        return record

    def reference_view(self,reference_id,view=None):
        record=self._reference(reference_id);views=[v for v in record['views'] if view is None or v['label']==view]
        if not views:raise ValueError('View not found')
        return {'reference_id':reference_id,'revision':record['revision'],'images':[self.store.get_artifact(v['artifact']['id']) for v in views],'requires_image_read':True,'reading_is_not_review':True}
