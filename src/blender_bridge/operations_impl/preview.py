"""Reproducible real scene renders, with exact camera and source provenance."""
from contextlib import contextmanager
import math
import uuid
import bpy
from mathutils import Vector
from .common import resolve, fingerprint, matrix_values, identify, node_tree_state
from ..core import BridgeError


class PreviewOps:
    def _environment_record(self,style):
        scene=bpy.context.scene;view=scene.view_settings
        result={'frame':scene.frame_current,'style':style}
        if style in ('material','normal'):
            result.update(lights={o.name:fingerprint(o) for o in scene.objects if o.type=='LIGHT'},world=node_tree_state(scene.world.node_tree) if scene.world and scene.world.use_nodes else list(scene.world.color) if scene.world else None)
        if style not in ('normal','silhouette'):result['view']=[view.view_transform,view.look,view.exposure,view.gamma]
        return result
    def preview_validate(self,artifact_ids):
        for aid in artifact_ids:self._image_camera(aid)
        return {'state':'passed','artifact_ids':artifact_ids,'session':self.state.session,'revision':self.state.revision}

    def _camera_record(self, cam, width, height):
        return {'name':cam.name, 'matrix_world':matrix_values(cam.matrix_world),
                'type':cam.data.type, 'lens':cam.data.lens, 'ortho_scale':cam.data.ortho_scale,
                'sensor_width':cam.data.sensor_width, 'sensor_fit':cam.data.sensor_fit,
                'shift_x':cam.data.shift_x, 'shift_y':cam.data.shift_y,
                'clip_start':cam.data.clip_start, 'clip_end':cam.data.clip_end,
                'width':width, 'height':height}

    def _new_camera(self, name, center, direction, scale, distance=None):
        if name in bpy.data.objects: raise ValueError('Camera name already exists: '+name)
        direction=Vector(direction)
        if direction.length < 1e-8: raise ValueError('Camera direction cannot be zero')
        data=bpy.data.cameras.new(name+'_Data');data.type='ORTHO';data.ortho_scale=scale
        ob=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(ob)
        ob.location=Vector(center)+direction.normalized()*(distance or scale*3)
        ob.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler()
        identify(ob);bpy.context.view_layer.update()
        return ob

    def preview_camera_set(self, name, center, scale, distance=None):
        directions={'front':(0,-1,0),'left':(-1,0,0),'back':(0,1,0),'right':(1,0,0),'three_quarter':(1,-1,.65)}
        if any(name+'_'+label in bpy.data.objects for label in directions): raise ValueError('Camera set name conflict')
        return {'views':[{'label':label,'camera':self._new_camera(name+'_'+label,center,d,scale,distance).name} for label,d in directions.items()],
                'coordinate_convention':'+Z up; front looks from -Y; +X right'}

    @contextmanager
    def _preview_settings(self, objects, style):
        scene=bpy.context.scene; render=scene.render; shade=scene.display.shading
        saved={k:getattr(render,k) for k in ('engine','resolution_x','resolution_y','resolution_percentage','filepath','film_transparent','pixel_aspect_x','pixel_aspect_y')}
        shading={k:getattr(shade,k) for k in ('light','color_type','single_color','show_shadows','show_cavity','show_specular_highlight','background_type','background_color','show_object_outline')}
        shading={k:tuple(v) if hasattr(v,'__len__') and not isinstance(v,str) else v for k,v in shading.items()}
        visibility={o:o.hide_render for o in scene.objects if o.type not in ('CAMERA','LIGHT','EMPTY','ARMATURE')}
        old_camera=scene.camera; fmt=render.image_settings.file_format
        view=scene.view_settings; view_saved=(view.view_transform,view.look,view.exposure,view.gamma)
        layer=bpy.context.view_layer; override=layer.material_override
        samples=scene.cycles.samples; device=scene.cycles.device
        material=None; wire=[]
        try:
            for ob in visibility: ob.hide_render=ob not in objects
            render.resolution_percentage=100;render.film_transparent=False
            render.pixel_aspect_x=render.pixel_aspect_y=1
            render.image_settings.file_format='PNG'
            scene.cycles.samples=32;scene.cycles.device='CPU'
            if style in ('clay','parts','silhouette','wireframe'):
                render.engine='BLENDER_WORKBENCH'
                shade.light='FLAT' if style=='silhouette' else 'STUDIO'
                shade.color_type='MATERIAL' if style=='parts' else 'SINGLE'
                shade.single_color=(.02,.02,.02) if style=='silhouette' else (.57,.61,.67)
                shade.show_shadows=shade.show_cavity=style not in ('silhouette','wireframe')
                shade.show_specular_highlight=style!='silhouette';shade.show_object_outline=False
                shade.background_type='VIEWPORT';shade.background_color=(.9,.9,.9) if style=='silhouette' else (.07,.08,.1)
                if style=='wireframe':
                    for ob in objects:
                        if ob.type=='MESH':
                            m=ob.modifiers.new('__bb_preview_wire','WIREFRAME');m.thickness=.0015;m.use_replace=True;wire.append((ob,m))
            else:
                render.engine='CYCLES'
                if style=='normal':
                    material=bpy.data.materials.new('__bb_normals_'+uuid.uuid4().hex);material.use_nodes=True
                    nodes=material.node_tree.nodes;nodes.clear()
                    geo=nodes.new('ShaderNodeNewGeometry');mathnode=nodes.new('ShaderNodeVectorMath');mathnode.operation='MULTIPLY_ADD'
                    mathnode.inputs[1].default_value=(.5,.5,.5);mathnode.inputs[2].default_value=(.5,.5,.5)
                    emit=nodes.new('ShaderNodeEmission');out=nodes.new('ShaderNodeOutputMaterial');links=material.node_tree.links
                    links.new(geo.outputs['Normal'],mathnode.inputs[0]);links.new(mathnode.outputs[0],emit.inputs['Color']);links.new(emit.outputs[0],out.inputs['Surface'])
                    layer.material_override=material
            if style in ('normal','silhouette'): view.view_transform='Standard';view.look='None';view.exposure=0;view.gamma=1
            yield
        finally:
            for ob,mod in wire: ob.modifiers.remove(mod)
            layer.material_override=override
            if material: bpy.data.materials.remove(material)
            for ob,value in visibility.items(): ob.hide_render=value
            scene.camera=old_camera;render.image_settings.file_format=fmt
            scene.cycles.samples=samples;scene.cycles.device=device
            for key,value in saved.items(): setattr(render,key,value)
            for key,value in shading.items(): setattr(shade,key,value)
            view.view_transform,view.look,view.exposure,view.gamma=view_saved

    def preview_render(self, camera, path, width=960, height=540, style='clay', overwrite=False, objects=None):
        cam=resolve(camera,'CAMERA');scene=bpy.context.scene
        obs=[resolve(o) for o in objects] if objects else [o for o in scene.objects if o.type in ('MESH','CURVE') and not o.hide_render]
        if not obs: raise ValueError('No render subjects')
        output=self.state.output_path(path,'.png',overwrite)
        before={ob.name:fingerprint(ob) for ob in obs}
        meta={'camera':cam.name,'camera_state':self._camera_record(cam,width,height),'object_hashes':before,'object_ids':{o.name:o.get('bb_object_id') for o in obs},
              'width':width,'height':height,'style':style,'frame':scene.frame_current,'blender':bpy.app.version_string,'environment':self._environment_record(style),'fingerprint_version':2}
        with self._preview_settings(obs,style):
            scene.camera=cam;scene.render.resolution_x=width;scene.render.resolution_y=height;scene.render.filepath=str(output)
            bpy.ops.render.render(write_still=True)
        if before!={ob.name:fingerprint(ob) for ob in obs}: raise BridgeError('RENDER_CHANGED_SOURCE','Temporary preview state was not restored')
        artifact=self.state.artifact(output,'image/png',meta)
        self.state.preview_metadata[artifact['id']]=meta
        return artifact

    def preview_multiview(self, objects, views, directory, style='clay', width=960, height=540):
        if len({v['label'] for v in views})!=len(views): raise ValueError('View labels must be unique')
        for view in views:
            if any(c in view['label'] for c in '/\\:'): raise ValueError('View label must be a filename stem')
            resolve(view['camera'],'CAMERA')
        return {'images':[dict(self.preview_render(v['camera'],f"{directory}/{v['label']}_{style}.png",width,height,style,objects=objects),label=v['label']) for v in views]}

    def preview_turntable(self, objects, center, scale, directory, frames=12, width=960, height=540, style='clay'):
        images=[];cam=self._new_camera('__bb_turntable_'+uuid.uuid4().hex,center,(1,-1,.35),scale)
        try:
            for i in range(frames):
                angle=i*2*math.pi/frames;direction=Vector((math.sin(angle),-math.cos(angle),.3))
                cam.location=Vector(center)+direction.normalized()*scale*3;cam.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler();bpy.context.view_layer.update()
                images.append(self.preview_render(cam.name,f'{directory}/frame_{i:03d}.png',width,height,style,objects=objects))
        finally:
            data=cam.data;bpy.data.objects.remove(cam,do_unlink=True);bpy.data.cameras.remove(data)
        return {'images':images,'camera_is_temporary':True}

    def preview_region(self, objects, center, scale, path, direction=(1,-1,.5), width=960, height=540):
        cam=self._new_camera('__bb_region_'+uuid.uuid4().hex,center,direction,scale)
        try: return self.preview_render(cam.name,path,width,height,objects=objects)
        finally:
            data=cam.data;bpy.data.objects.remove(cam,do_unlink=True);bpy.data.cameras.remove(data)
