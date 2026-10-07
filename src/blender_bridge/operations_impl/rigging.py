"""Explicit deform-only weights and reversible pose measurements."""
import math
import bpy
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from .common import resolve, guarded, index_check, matrix_values, fingerprint
from ..operations import selected


def deform_names(rig):return {b.name for b in rig.data.bones if b.use_deform}


def vertex_weights(ob,vertex,names):
    return {ob.vertex_groups[g.group].name:g.weight for g in vertex.groups if ob.vertex_groups[g.group].name in names and g.weight>1e-8}


def surface_bvh(ob):
    mesh=ob.data;mesh.calc_loop_triangles()
    triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
    vertices=[ob.matrix_world@v.co for v in mesh.vertices]
    return BVHTree.FromPolygons(vertices,triangles,all_triangles=True),vertices,triangles


def barycentric(point,a,b,c):
    v0=b-a;v1=c-a;v2=point-a;d00=v0.dot(v0);d01=v0.dot(v1);d11=v1.dot(v1);d20=v2.dot(v0);d21=v2.dot(v1)
    den=d00*d11-d01*d01
    if abs(den)<1e-14:return (1,0,0)
    v=(d11*d20-d01*d21)/den;w=(d00*d21-d01*d20)/den
    return (1-v-w,v,w)


class RigOps:
    def rig_inspect(self,armature):
        rig=resolve(armature,'ARMATURE')
        return {'armature':rig.name,'matrix_world':matrix_values(rig.matrix_world),'pose_position':rig.data.pose_position,
                'bones':[{'name':b.name,'parent':b.parent.name if b.parent else None,'head':list(b.head_local),'tail':list(b.tail_local),'deform':b.use_deform,'pose_matrix':matrix_values(rig.pose.bones[b.name].matrix),'basis':matrix_values(rig.pose.bones[b.name].matrix_basis)} for b in rig.data.bones]}

    def rig_fit(self,armature,bones):
        rig=resolve(armature,'ARMATURE',True);guarded(rig)
        for spec in bones:
            if spec['name'] not in rig.data.bones:raise ValueError('Unknown bone: '+spec['name'])
            if spec.get('parent') and spec['parent'] not in rig.data.bones:raise ValueError('Unknown parent')
            head=Vector(spec.get('head',rig.data.bones[spec['name']].head_local));tail=Vector(spec.get('tail',rig.data.bones[spec['name']].tail_local))
            if (tail-head).length<1e-6:raise ValueError('Zero length bone')
        with selected([rig]):
            bpy.ops.object.mode_set(mode='EDIT')
            try:
                for spec in bones:
                    bone=rig.data.edit_bones[spec['name']]
                    for key in ('head','tail','roll'):
                        if key in spec:setattr(bone,key,spec[key])
                    if 'deform' in spec:bone.use_deform=spec['deform']
                    if 'parent' in spec:bone.parent=rig.data.edit_bones.get(spec['parent'])
            finally:
                if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        return self.rig_inspect(armature)

    def _ensure_binding(self,ob,rig):
        modifiers=[m for m in ob.modifiers if m.type=='ARMATURE']
        if any(m.object!=rig for m in modifiers):raise ValueError('Different armature modifier already exists')
        if ob.parent and ob.parent!=rig:raise ValueError('Explicitly resolve the existing parent hierarchy before armature binding')
        world=ob.matrix_world.copy();ob.parent=rig;ob.matrix_world=world
        if not modifiers:mod=ob.modifiers.new('BridgeArmature','ARMATURE');mod.object=rig
        for name in deform_names(rig):
            if name not in ob.vertex_groups:ob.vertex_groups.new(name=name)

    def rig_bind_rigid(self,armature,bindings):
        rig=resolve(armature,'ARMATURE');names=deform_names(rig)
        for bind in bindings:
            if bind['bone'] not in names:raise ValueError('Rigid binding requires a deform bone')
            guarded(resolve(bind['object'],'MESH',True))
        result=[]
        for bind in bindings:
            ob=resolve(bind['object'],'MESH',True);self._ensure_binding(ob,rig);indices=list(range(len(ob.data.vertices)))
            for group in ob.vertex_groups:
                if group.name in names:group.remove(indices)
            ob.vertex_groups[bind['bone']].add(indices,1,'REPLACE');result.append(self.rig_validate(ob.name,armature))
        return {'bindings':result,'mode':'rigid_one_bone'}

    def rig_bind_auto(self,objects,armature):
        rig=resolve(armature,'ARMATURE');obs=[resolve(o,'MESH',True) for o in objects]
        for ob in obs:guarded(ob)
        with selected([rig]+obs):
            bpy.context.view_layer.objects.active=rig;bpy.ops.object.parent_set(type='ARMATURE_AUTO')
        return {'objects':[self.rig_validate(o.name,armature) for o in obs],'automatic_weights_are_candidate':True}

    def rig_validate(self,object,armature,max_influences=4):
        ob=resolve(object,'MESH');rig=resolve(armature,'ARMATURE');names=deform_names(rig)
        weights=[vertex_weights(ob,v,names) for v in ob.data.vertices]
        unweighted=[i for i,w in enumerate(weights) if sum(w.values())<1e-7]
        non_normal=[i for i,w in enumerate(weights) if w and abs(sum(w.values())-1)>1e-4]
        excess=[i for i,w in enumerate(weights) if len(w)>max_influences]
        bound=any(m.type=='ARMATURE' and m.object==rig for m in ob.modifiers)
        return {'object':ob.name,'armature':rig.name,'state':'passed' if bound and not unweighted and not non_normal and not excess else 'failed',
                'bound':bound,'deform_bones':sorted(names),'non_deform_groups':[g.name for g in ob.vertex_groups if g.name not in names],
                'unweighted_count':len(unweighted),'unweighted_sample':unweighted[:32],'non_normalized_count':len(non_normal),'over_limit_count':len(excess),'max_influences':max((len(w) for w in weights),default=0)}

    def _write_weights(self,ob,index,weights,names):
        for name in names:
            group=ob.vertex_groups.get(name)
            if group:group.remove([index])
        for name,value in weights.items():
            if value>1e-8:
                group=ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name);group.add([index],min(1,max(0,value)),'REPLACE')

    def rig_weights_edit(self,object,armature,action,bone=None,indices=None,weight=1,iterations=1,axis='X',bone_map=None):
        ob=resolve(object,'MESH',True);rig=resolve(armature,'ARMATURE');names=deform_names(rig)
        region=indices if indices is not None else list(range(len(ob.data.vertices)));index_check(region,len(ob.data.vertices));guarded(ob,region)
        if action in ('set','add') and bone not in names:raise ValueError('Exact deform bone required')
        if bone and bone not in names:raise ValueError('Only deform groups may be edited')
        self._ensure_binding(ob,rig);weights=[vertex_weights(ob,v,names) for v in ob.data.vertices]
        if action=='smooth':
            neighbors={v.index:set() for v in ob.data.vertices}
            for edge in ob.data.edges:
                a,b=edge.vertices;neighbors[a].add(b);neighbors[b].add(a)
            for _ in range(iterations):
                updated=[dict(w) for w in weights]
                for i in region:
                    around=neighbors[i]|{i};updated[i]={name:sum(weights[j].get(name,0) for j in around)/len(around) for name in names}
                weights=updated
        elif action=='mirror':
            mapping=bone_map or {n:n for n in names}
            if set(mapping)-names or set(mapping.values())-names:raise ValueError('bone_map must map deform bones')
            tree=KDTree(len(ob.data.vertices))
            for vertex in ob.data.vertices:tree.insert(vertex.co,vertex.index)
            tree.balance();source=[dict(w) for w in weights];component='XYZ'.index(axis)
            for i in region:
                point=ob.data.vertices[i].co.copy();point[component]*=-1;_,index,distance=tree.find(point)
                if distance>max(1e-5,max(ob.dimensions)*.01):raise ValueError('Mirrored vertex outside 1 percent mesh tolerance')
                weights[i]={mapping.get(n,n):w for n,w in source[index].items()}
        else:
            for i in region:
                if action=='clear':
                    if bone:weights[i].pop(bone,None)
                    else:weights[i]={}
                elif action=='set':weights[i][bone]=weight
                elif action=='add':weights[i][bone]=min(1,weights[i].get(bone,0)+weight)
        for i in region:self._write_weights(ob,i,weights[i],names)
        return self.rig_validate(object,armature)

    def rig_weights_normalize(self,object,armature,max_influences=4,fallback_bone=None):
        ob=resolve(object,'MESH',True);rig=resolve(armature,'ARMATURE');guarded(ob);names=deform_names(rig)
        if fallback_bone and fallback_bone not in names:raise ValueError('Fallback must be a deform bone')
        for vertex in ob.data.vertices:
            weights=dict(sorted(vertex_weights(ob,vertex,names).items(),key=lambda p:p[1],reverse=True)[:max_influences]);total=sum(weights.values())
            if total:weights={n:w/total for n,w in weights.items()}
            elif fallback_bone:weights={fallback_bone:1}
            self._write_weights(ob,vertex.index,weights,names)
        return self.rig_validate(object,armature,max_influences)

    def rig_weights_transfer(self,object,source,armature,max_distance,indices=None):
        ob=resolve(object,'MESH',True);src=resolve(source,'MESH');rig=resolve(armature,'ARMATURE');names=deform_names(rig)
        region=indices if indices is not None else list(range(len(ob.data.vertices)));index_check(region,len(ob.data.vertices));guarded(ob,region)
        tree,vertices,triangles=surface_bvh(src);updates={};miss=[]
        for i in region:
            point,normal,face,distance=tree.find_nearest(ob.matrix_world@ob.data.vertices[i].co,max_distance)
            if point is None:miss.append(i);continue
            tri=triangles[face];mix=barycentric(point,*(vertices[j] for j in tri));weights={}
            for factor,j in zip(mix,tri):
                for name,value in vertex_weights(src,src.data.vertices[j],names).items():weights[name]=weights.get(name,0)+factor*value
            updates[i]=weights
        self._ensure_binding(ob,rig)
        for i,weights in updates.items():self._write_weights(ob,i,weights,names)
        return {**self.rig_validate(object,armature),'transferred':len(updates),'unmatched_count':len(miss),'unmatched_sample':miss[:32]}

    def animation_inspect(self,object):
        ob=resolve(object);data=ob.animation_data;action=data.action if data else None
        return {'object':ob.name,'frame':bpy.context.scene.frame_current,'action':action.name if action else None,
                'frame_range':list(action.frame_range) if action else None,'slots':[s.identifier for s in action.slots] if action and hasattr(action,'slots') else [],
                'nla_tracks':[t.name for t in data.nla_tracks] if data else []}

    def _evaluated_measure(self,ob):
        ev=ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        result={'object':ob.name,'bounds_world':[list(ev.matrix_world@Vector(v)) for v in ev.bound_box]}
        if ob.type=='MESH':
            mesh=ev.to_mesh()
            try:
                result['vertices']=len(mesh.vertices);result['edges']=[float((ev.matrix_world@mesh.vertices[e.vertices[0]].co-ev.matrix_world@mesh.vertices[e.vertices[1]].co).length) for e in mesh.edges]
            finally:ev.to_mesh_clear()
        if ob.type=='ARMATURE':result['bones']={b.name:matrix_values(b.matrix) for b in ev.pose.bones}
        return result

    def animation_sample(self,objects,frames):
        obs=[resolve(o) for o in objects];scene=bpy.context.scene;old=scene.frame_current;result=[]
        try:
            for frame in frames:
                scene.frame_set(frame);bpy.context.view_layer.update();result.append({'frame':frame,'objects':[self._evaluated_measure(o) for o in obs]})
        finally:scene.frame_set(old)
        return {'samples':result,'restored_frame':scene.frame_current}

    def animation_pose_test(self,armature,objects,poses,directory,camera=None,width=960,height=540):
        rig=resolve(armature,'ARMATURE');obs=[resolve(o) for o in objects]
        for pose in poses:
            if set(pose['bones'])-set(rig.pose.bones.keys()):raise ValueError('Unknown pose bones')
            for values in pose['bones'].values():
                if not isinstance(values,dict) or set(values)-{'rotation','location','scale'}:raise ValueError('Pose values require rotation/location/scale')
                if any(len(v)!=3 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in v) for v in values.values()):raise ValueError('Pose vectors must be finite triples')
        before=fingerprint(rig);saved={b.name:(b.matrix_basis.copy(),b.rotation_mode) for b in rig.pose.bones};result=[]
        baseline=[self._evaluated_measure(o) for o in obs]
        try:
            for index,pose in enumerate(poses):
                for b in rig.pose.bones:b.matrix_basis=saved[b.name][0]
                for name,values in pose['bones'].items():
                    bone=rig.pose.bones[name];bone.rotation_mode='XYZ'
                    for key,value in values.items():setattr(bone,'rotation_euler' if key=='rotation' else key,value)
                bpy.context.view_layer.update();measure=[self._evaluated_measure(o) for o in obs]
                for base,item in zip(baseline,measure):
                    if 'edges' in base:item['max_edge_length_change']=max((abs(a-b) for a,b in zip(base['edges'],item['edges'])),default=0)
                record={'label':pose['label'],'measurements':measure}
                if camera:record['image']=self.preview_render(camera,f'{directory}/pose_{index:03d}.png',width,height,objects=objects)
                result.append(record)
        finally:
            for bone in rig.pose.bones:bone.rotation_mode=saved[bone.name][1];bone.matrix_basis=saved[bone.name][0]
            bpy.context.view_layer.update()
        return {'poses':result,'restored':fingerprint(rig)==before,'baseline':baseline,'visual_acceptance':'pending_review'}
