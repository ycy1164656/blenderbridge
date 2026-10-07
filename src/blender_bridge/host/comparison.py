"""Labelled real-image comparisons. Metrics are conditional, never art scores."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageChops, ImageStat
from .storage import sha


class ComparisonOps:
    def compare_region(self,artifact_id,rectangle,path):
        source=self.store.get_artifact(artifact_id)
        with Image.open(source['path']) as image:
            x0,y0,x1,y1=rectangle
            if not 0<=x0<x1<=image.width or not 0<=y0<y1<=image.height:raise ValueError('Crop rectangle outside image')
            out=self.store.output(path,'.png');image.crop(rectangle).save(out)
        return self.store.artifact(out,'image/png',{'source_id':artifact_id,'source_sha256':source['sha256'],'rectangle':rectangle,'pixel_offset':[x0,y0]})

    def compare_views(self,reference_artifacts,candidate_artifacts,path,alignment=None,overlay=False):
        if len(reference_artifacts)!=len(candidate_artifacts):raise ValueError('Explicit equal-length reference/candidate pairing required')
        rows=[];metrics=[];sources=[]
        for index,(refid,candidateid) in enumerate(zip(reference_artifacts,candidate_artifacts)):
            ref=self.store.get_artifact(refid);candidate=self.store.get_artifact(candidateid);sources.append({'reference':ref,'candidate':candidate})
            with Image.open(ref['path']) as raw:a=raw.convert('RGBA')
            with Image.open(candidate['path']) as raw:b=raw.convert('RGBA')
            original_a=a.copy();original_b=b.copy()
            panel_width=720;panel_height=max(320,min(720,round(max(a.height/a.width,b.height/b.width)*panel_width)))
            panels=[]
            for im,label in [(a,'REFERENCE '+str(index+1)),(b,'CANDIDATE '+str(index+1))]:
                panel=Image.new('RGB',(panel_width,panel_height+32),(35,38,43));im.thumbnail((panel_width,panel_height),Image.Resampling.LANCZOS)
                panel.paste(im,((panel_width-im.width)//2,32+(panel_height-im.height)//2),im);ImageDraw.Draw(panel).text((12,10),label,fill=(245,245,245));panels.append(panel)
            metric={'pair':index,'state':'not_applicable','reason':'calibrated equal-size alpha silhouettes required','art_score':None}
            if alignment and alignment.get('calibrated') and original_a.size==original_b.size and original_a.getchannel('A').getextrema()[0]<255 and original_b.getchannel('A').getextrema()[0]<255:
                ma=original_a.getchannel('A').point(lambda v:255 if v>127 else 0);mb=original_b.getchannel('A').point(lambda v:255 if v>127 else 0)
                intersect=ImageChops.darker(ma,mb);union=ImageChops.lighter(ma,mb);count_union=sum(union.histogram()[128:])
                metric={'pair':index,'state':'measured','silhouette_iou':sum(intersect.histogram()[128:])/count_union if count_union else None,'art_score':None,'alignment':alignment}
            if overlay:
                if not alignment or not alignment.get('calibrated') or original_a.size!=original_b.size:raise ValueError('Overlay requires explicit calibrated equal-size images; arbitrary stretching is not allowed')
                mixed=Image.blend(original_a,original_b,.5);mixed.thumbnail((panel_width,panel_height),Image.Resampling.LANCZOS)
                panel=Image.new('RGB',(panel_width,panel_height+32),(35,38,43));panel.paste(mixed,((panel_width-mixed.width)//2,32+(panel_height-mixed.height)//2),mixed);ImageDraw.Draw(panel).text((12,10),'EXPLICIT ALIGNED OVERLAY',fill='white');panels.append(panel)
            row=Image.new('RGB',(panel_width*len(panels),panel_height+32))
            for i,panel in enumerate(panels):row.paste(panel,(i*panel_width,0))
            rows.append(row);metrics.append(metric)
        output=Image.new('RGB',(max(r.width for r in rows),sum(r.height for r in rows)),(35,38,43));y=0
        for row in rows:output.paste(row,(0,y));y+=row.height
        target=self.store.output(path,'.png');output.save(target)
        artifact=self.store.artifact(target,'image/png',{'pairs':sources,'metrics':metrics,'overlay':overlay})
        return {'image':artifact,'metrics':metrics,'visual_judgment':'requires_actual_image_review'}

    def texture_pack_channels(self,sources,path,fill=(0,0,0,1)):
        channels=[None]*4;size=None;records=[]
        if len({s['output'] for s in sources})!=len(sources):raise ValueError('Each output channel may be assigned once')
        for source in sources:
            target=self.store.input(source['path'])
            with Image.open(target) as image:
                if size is None:size=image.size
                elif image.size!=size:raise ValueError('Channel textures must have identical dimensions')
                channels['RGBA'.index(source['output'])]=image.convert('RGBA').getchannel(source['channel'])
            records.append({**source,'sha256':sha(target)})
        for index,channel in enumerate(channels):
            if channel is None:channels[index]=Image.new('L',size,round(max(0,min(1,fill[index]))*255))
        output=self.store.output(path,'.png');Image.merge('RGBA',channels).save(output)
        return self.store.artifact(output,'image/png',{'sources':records,'fill':fill,'color_conversion':'none; raw 8-bit channel values'})
