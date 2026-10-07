"""Independent process file reopen/import measurement. No prior scene state reused."""
import json
from pathlib import Path
import sys
import traceback


def main():
    spec=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
    sys.path.insert(0,spec['package_parent'])
    import bpy
    from mathutils import Vector
    from blender_bridge.core import atomic_json
    from blender_bridge.operations import object_info
    path=Path(spec['path']);result={'path':str(path),'state':'running','blender':bpy.app.version_string}
    try:
        if path.suffix=='.blend':bpy.ops.wm.open_mainfile(filepath=str(path),load_ui=False,use_scripts=False)
        else:
            scene=bpy.data.scenes.new('IndependentReadback');bpy.context.window.scene=scene
            if path.suffix=='.fbx':bpy.ops.import_scene.fbx(filepath=str(path),use_anim=True,anim_offset=0)
            elif path.suffix=='.glb':bpy.ops.import_scene.gltf(filepath=str(path))
            elif path.suffix=='.obj':bpy.ops.wm.obj_import(filepath=str(path),forward_axis='NEGATIVE_Y',up_axis='Z')
            else:raise ValueError('Unsupported readback format')
        bpy.context.view_layer.update();scene=bpy.context.scene
        helpers={b.custom_shape for ob in scene.objects if ob.type=='ARMATURE' for b in ob.pose.bones if b.custom_shape}
        objects=[ob for ob in scene.objects if ob not in helpers]
        result['excluded_bone_display_helpers']=[o.name for o in helpers]
        records=[]
        for ob in objects:
            record=object_info(ob)
            if ob.type=='MESH':
                ev=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
                try:mesh.calc_loop_triangles();record['evaluated_triangles']=len(mesh.loop_triangles)
                finally:ev.to_mesh_clear()
            data=ob.animation_data;action=data.action if data else None
            record['action']=action.name if action else None;record['action_range']=list(action.frame_range) if action else None
            records.append(record)
        textures=[]
        used={s.material for ob in objects for s in ob.material_slots if s.material}
        for mat in used:
            if not mat.use_nodes:continue
            for node in mat.node_tree.nodes:
                if node.type=='TEX_IMAGE' and node.image:
                    image=node.image;filepath=Path(bpy.path.abspath(image.filepath))
                    textures.append({'material':mat.name,'image':image.name,'path':str(filepath),'packed':bool(image.packed_file),'exists':filepath.is_file() or bool(image.packed_file),'size':list(image.size),'colorspace':image.colorspace_settings.name})
        points=[ob.matrix_world@Vector(v) for ob in objects if ob.type=='MESH' for v in ob.bound_box]
        bounds={'min':[min(p[i] for p in points) for i in range(3)],'max':[max(p[i] for p in points) for i in range(3)]} if points else None
        result.update(state='succeeded',objects=records,bounds=bounds,scene_frame_range=[scene.frame_start,scene.frame_end],fps=scene.render.fps/scene.render.fps_base,
                      scale_length=scene.unit_settings.scale_length,textures=textures,code_origin=str(Path(sys.modules['blender_bridge'].__file__).resolve()))
    except Exception as exc:
        result.update(state='failed',error=str(exc),traceback=traceback.format_exc());raise
    finally:atomic_json(spec['result'],result)


if __name__=='__main__':main()
