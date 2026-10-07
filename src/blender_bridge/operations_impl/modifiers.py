import bpy
from ..core import BridgeError
from .common import Base, resolve, info, guarded

PARAMETERS={
 'BEVEL':{'width','segments','limit_method','angle_limit','affect','profile','harden_normals','use_clamp_overlap'},
 'MIRROR':{'use_axis','use_clip','use_mirror_merge','merge_threshold','mirror_object','use_bisect_axis','use_bisect_flip_axis'},
 'SOLIDIFY':{'thickness','offset','use_even_offset','use_quality_normals','use_rim','use_rim_only'},
 'SUBSURF':{'levels','render_levels','subdivision_type','show_only_control_edges'},
 'BOOLEAN':{'object','operation','solver','use_self','use_hole_tolerant'},
 'WEIGHTED_NORMAL':{'mode','weight','keep_sharp','thresh'},
 'SHRINKWRAP':{'target','wrap_method','wrap_mode','offset','use_project_x','use_project_y','use_project_z','use_positive_direction','use_negative_direction','project_limit'},
 'DECIMATE':{'decimate_type','ratio','iterations','angle_limit','use_collapse_triangulate','use_symmetry','symmetry_axis'},
 'REMESH':{'mode','voxel_size','octree_depth','scale','sharpness','use_remove_disconnected','threshold','use_smooth_shade'},
 'TRIANGULATE':{'quad_method','ngon_method','min_vertices','keep_custom_normals'},
 'ARRAY':{'count','fit_type','relative_offset_displace','constant_offset_displace','use_relative_offset','use_constant_offset','use_object_offset','offset_object','use_merge_vertices','merge_threshold'},
 'SIMPLE_DEFORM':{'deform_method','deform_axis','angle','factor','limits','origin','vertex_group'},
}
POINTERS={'object','mirror_object','target','offset_object','origin'}


def serial(value):
    if isinstance(value,(str,int,float,bool,type(None))):return value
    if isinstance(value,bpy.types.Object):return value.get('bb_object_id',value.name)
    try:return list(value)
    except TypeError:return str(value)


def current(mod):
    return {k:serial(getattr(mod,k)) for k in sorted(PARAMETERS.get(mod.type,set())) if k in mod.bl_rna.properties}


def validate_properties(mod,values):
    unknown=set(values)-PARAMETERS.get(mod.type,set())
    if unknown:raise BridgeError('UNSUPPORTED_CAPABILITY',f'Unsupported {mod.type} properties: {sorted(unknown)}')
    result={}
    for key,value in values.items():
        if key not in mod.bl_rna.properties:raise BridgeError('UNSUPPORTED_CAPABILITY',f'{key} is unavailable in this Blender version')
        prop=mod.bl_rna.properties[key]
        if prop.is_readonly:raise ValueError(f'{key} is read-only')
        if key in POINTERS:
            value=resolve(value) if value else None
        elif prop.type=='ENUM':
            allowed={x.identifier for x in prop.enum_items}
            if allowed and value not in allowed:raise ValueError(f'{key}: expected one of {sorted(allowed)}')
        elif prop.type in ('INT','FLOAT'):
            items=value if prop.is_array else [value]
            if prop.is_array and (not isinstance(value,list) or len(value)!=prop.array_length):raise ValueError(f'{key}: array length mismatch')
            for number in items:
                if isinstance(number,bool) or not isinstance(number,(float,int)) or not prop.hard_min<=number<=prop.hard_max:raise ValueError(f'{key}: invalid numeric value')
                if prop.type=='INT' and not isinstance(number,int):raise ValueError(f'{key}: integer required')
        elif prop.type=='BOOLEAN':
            items=value if prop.is_array else [value]
            if prop.is_array and (not isinstance(value,list) or len(value)!=prop.array_length):raise ValueError(f'{key}: array length mismatch')
            if any(type(x)!=bool for x in items):raise ValueError(f'{key}: boolean required')
        result[key]=value
    return result


class ModifierOps(Base):
    def modifier_inspect(self,object,name=None):
        ob=resolve(object)
        mods=[ob.modifiers.get(name)] if name else list(ob.modifiers)
        if any(m is None for m in mods):raise ValueError('Modifier not found')
        result=[]
        for mod in mods:
            fields={}
            for key in sorted(PARAMETERS.get(mod.type,set())):
                prop=mod.bl_rna.properties.get(key)
                if prop:
                    entry={'type':prop.type,'array_length':getattr(prop,'array_length',0)}
                    if prop.type=='ENUM':entry['enum']=[x.identifier for x in prop.enum_items]
                    if prop.type in ('INT','FLOAT'):entry.update(minimum=prop.hard_min,maximum=prop.hard_max)
                    fields[key]=entry
            result.append({'name':mod.name,'type':mod.type,'index':list(ob.modifiers).index(mod),'properties':current(mod),'parameter_schema':fields})
        return {'object':ob.name,'modifiers':result}

    def modifier_add(self,object,name,kind,properties=None,**values):
        ob=resolve(object,'MESH',True);guarded(ob,topology_change=True)
        if name in ob.modifiers:raise BridgeError('NAME_CONFLICT',name)
        parameters={**values,**(properties or {})}
        if 'operand' in parameters:parameters['object']=parameters.pop('operand')
        if kind not in PARAMETERS:raise BridgeError('UNSUPPORTED_CAPABILITY',kind)
        if kind=='BOOLEAN' and ('object' not in parameters or resolve(parameters['object'])==ob):raise ValueError('Boolean requires another explicit object')
        # Build on an unlinked probe object so invalid parameters cannot leave a real modifier behind.
        probe_mesh=bpy.data.meshes.new('__bb_modifier_probe_mesh')
        probe=bpy.data.objects.new('__bb_modifier_probe',probe_mesh)
        try:
            check=probe.modifiers.new(name,kind);parsed=validate_properties(check,parameters)
        finally:
            bpy.data.objects.remove(probe)
            bpy.data.meshes.remove(probe_mesh)
        mod=ob.modifiers.new(name,kind)
        for key,value in parsed.items():setattr(mod,key,value)
        return self.modifier_inspect(ob.name,name)

    def modifier_update(self,object,name,properties):
        ob=resolve(object,writable=True);guarded(ob,topology_change=True);mod=ob.modifiers.get(name)
        if mod is None:raise ValueError('Modifier not found')
        parsed=validate_properties(mod,properties)
        for key,value in parsed.items():
            if key in POINTERS and value==ob:raise ValueError('Modifier cannot target its own object')
        for key,value in parsed.items():setattr(mod,key,value)
        return self.modifier_inspect(ob.name,name)

    def modifier_remove(self,object,name):
        ob=resolve(object,writable=True);guarded(ob,topology_change=True);mod=ob.modifiers.get(name)
        if mod is None:raise ValueError('Modifier not found')
        ob.modifiers.remove(mod);return self.modifier_inspect(ob.name)

    def modifier_reorder(self,object,name,index):
        ob=resolve(object,writable=True);guarded(ob,topology_change=True)
        names=[m.name for m in ob.modifiers]
        if name not in names or index>=len(names):raise ValueError('Modifier/index not found')
        ob.modifiers.move(names.index(name),index);return self.modifier_inspect(ob.name)

    def modifier_copy(self,object,name,target,new_name=None):
        ob=resolve(object);mod=ob.modifiers.get(name)
        if mod is None:raise ValueError('Modifier not found')
        return self.modifier_add(target,new_name or name,mod.type,properties=current(mod))

    def modifier_apply(self,object,name):
        from ..operations import selected
        ob=resolve(object,'MESH',True);guarded(ob,topology_change=True)
        mod=ob.modifiers.get(name)
        if mod is None:raise ValueError('Modifier not found')
        if mod.type=='ARMATURE':raise BridgeError('UNSUPPORTED_CAPABILITY','Binding modifiers are not implicitly baked')
        checkpoint=self.checkpoint_create('before_modifier_'+name,objects=[ob.name])
        with selected([ob]):bpy.ops.object.modifier_apply(modifier=name)
        return {'object':info(ob),'checkpoint':checkpoint,'topology_changed':True,'dependent_bakes_stale':True}
