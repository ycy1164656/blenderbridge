import json
import math
import bpy
import bmesh
from mathutils import Vector, Matrix, Euler
from ..core import BridgeError
from ..geometry_algorithms import loft, validate_ring
from .common import Base, resolve, info, new_mesh, snapshot_recipe, bm_edit, guarded, index_check, topology, collection, identify, geometry_node_input


class GeometryOps(Base):
    def geometry_profile(self,name,points,depth=0,direction=(0,0,1),collection=None):
        normal=validate_ring(points)
        axis=Vector(direction)
        if axis.length<1e-8: raise ValueError('Extrusion direction must be nonzero')
        if abs(depth)>1e-9:
            if abs(Vector(normal).dot(axis.normalized()))<1e-5: raise ValueError('Extrusion must leave contour plane')
            offset=axis.normalized()*depth
            vertices,faces=loft([points,[list(Vector(p)+offset) for p in points]],True,False)
        else: vertices,faces=points,[list(range(len(points)))]
        ob=new_mesh(name,vertices,faces,collection)
        snapshot_recipe(ob,'geometry.profile',dict(name=name,points=points,depth=depth,direction=list(direction),collection=collection))
        return info(ob)

    def geometry_loft(self,name,sections,cap=True,align=True,collection=None):
        vertices,faces=loft(sections,cap,align)
        ob=new_mesh(name,vertices,faces,collection)
        snapshot_recipe(ob,'geometry.loft',dict(name=name,sections=sections,cap=cap,align=align,collection=collection))
        return info(ob)

    def geometry_sweep(self,name,profile,path,up=(0,0,1),cap=True,collection=None):
        validate_ring([[p[0],p[1],0] for p in profile])
        centers=[Vector(p) for p in path]
        if any((b-a).length<1e-7 for a,b in zip(centers,centers[1:])): raise ValueError('Path has coincident consecutive points')
        tangents=[]
        for i in range(len(centers)):
            t=centers[min(i+1,len(centers)-1)]-centers[max(0,i-1)]
            if t.length<1e-7: raise ValueError('Path has a reversing cusp')
            tangents.append(t.normalized())
        u=Vector(up); u-=tangents[0]*u.dot(tangents[0])
        if u.length<1e-7:
            u=Vector((1,0,0));u-=tangents[0]*u.dot(tangents[0])
        if u.length<1e-7: u=Vector((0,1,0))
        u.normalize(); sections=[]
        for i,(center,tangent) in enumerate(zip(centers,tangents)):
            if i: u=tangents[i-1].rotation_difference(tangent)@u
            u=(u-tangent*u.dot(tangent)).normalized();v=tangent.cross(u).normalized()
            sections.append([list(center+u*p[0]+v*p[1]) for p in profile])
        vertices,faces=loft(sections,cap,False)
        ob=new_mesh(name,vertices,faces,collection)
        snapshot_recipe(ob,'geometry.sweep',dict(name=name,profile=profile,path=path,up=list(up),cap=cap,collection=collection))
        return info(ob)

    def geometry_curve(self,name,points,kind='POLY',closed=False,radius=0,collection=None):
        if name in bpy.data.objects: raise BridgeError('NAME_CONFLICT',name)
        dest=globals()['collection'](collection)
        data=bpy.data.curves.new(name+'_Curve','CURVE');data.dimensions='3D';data.resolution_u=12
        spline=data.splines.new(kind)
        if kind=='BEZIER':
            spline.bezier_points.add(len(points)-1)
            for point,co in zip(spline.bezier_points,points):
                point.co=co;point.handle_left_type=point.handle_right_type='AUTO'
        else:
            spline.points.add(len(points)-1)
            for point,co in zip(spline.points,points):point.co=(*co,1)
        spline.use_cyclic_u=closed;data.bevel_depth=radius;data.bevel_resolution=3;data.use_fill_caps=True
        ob=bpy.data.objects.new(name,data);dest.objects.link(ob);identify(ob)
        snapshot_recipe(ob,'geometry.curve',dict(name=name,points=points,kind=kind,closed=closed,radius=radius,collection=collection))
        return info(ob)

    def mesh_inspect(self,object,offset=0,limit=200,mode='base'):
        ob=resolve(object,'MESH');evaluated=None
        if mode=='base':
            result=self.legacy.mesh_inspect(ob.name,offset,limit)
            result.update(info(ob))
        else:
            evaluated=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh()
            try:
                mesh.calc_loop_triangles()
                result={'name':ob.name,'vertices':len(mesh.vertices),'edges':len(mesh.edges),'faces':len(mesh.polygons),'triangles':len(mesh.loop_triangles),
                        'vertex_data':[{'index':v.index,'co':list(v.co)} for v in mesh.vertices[offset:offset+limit]],
                        'face_data':[{'index':p.index,'vertices':list(p.vertices),'normal':list(p.normal)} for p in mesh.polygons[offset:offset+limit]],
                        'indices_editable':False,'topology_revision':topology(mesh)}
                bm=bmesh.new()
                try:
                    bm.from_mesh(mesh)
                    result['health']={'zero_area_faces':sum(f.calc_area()<=1e-12 for f in bm.faces),'boundary_edges':sum(e.is_boundary for e in bm.edges),'non_manifold_edges':sum(not e.is_manifold for e in bm.edges),'loose_vertices':sum(not v.link_edges for v in bm.verts)}
                finally:bm.free()
            finally:evaluated.to_mesh_clear()
        result.update(mode=mode,frame=bpy.context.scene.frame_current,self_intersections='not_checked',object_id=ob.get('bb_object_id'))
        return result

    def _region(self,object,indices=None,selection_id=None,center=None,radius=None,space='local',mask_group=None,falloff='constant',protected_parts=(),**unused):
        ob=resolve(object,'MESH',True)
        if selection_id:
            saved=self._selection(selection_id)
            if saved['object_id']!=ob.get('bb_object_id'):raise BridgeError('INVALID_SELECTION','Selection belongs to another object')
            if indices is not None:raise ValueError('Use indices or selection_id, not both')
            indices=saved['indices']
        if indices is None:
            if center is None or radius is None:raise ValueError('Explicit indices, selection_id, or spatial radius required')
            c=Vector(center)
            indices=[v.index for v in ob.data.vertices if ((ob.matrix_world@v.co if space=='world' else v.co)-c).length<=radius]
        index_check(indices,len(ob.data.vertices))
        if not indices:raise BridgeError('EMPTY_SELECTION','No vertices selected')
        guarded(ob,indices,False,protected_parts)
        to_space=ob.matrix_world if space=='world' else Matrix.Identity(4)
        from_space=to_space.inverted()
        points={i:to_space@ob.data.vertices[i].co for i in indices}
        pivot=Vector(center) if center is not None else sum(points.values(),Vector())/len(points)
        group=ob.vertex_groups.get(mask_group) if mask_group else None
        if mask_group and group is None:raise ValueError('Mask group not found')
        weights={}
        for i,p in points.items():
            t=min(1,(p-pivot).length/radius) if radius else 0
            w=1 if falloff=='constant' else 1-t if falloff=='linear' else .5*(1+math.cos(math.pi*t))
            if radius and (p-pivot).length>radius:w=0
            if group:
                try:w*=group.weight(i)
                except RuntimeError:w=0
            weights[i]=w
        return ob,points,pivot,from_space,weights

    def mesh_region_transform(self,object,delta=None,scale=None,rotation=None,**options):
        if all(x is None for x in (delta,scale,rotation)):raise ValueError('Specify a transform')
        ob,points,pivot,inverse,weights=self._region(object,**options)
        r=Euler(rotation or (0,0,0),'XYZ').to_matrix();s=Vector(scale or (1,1,1));translation=Vector(delta or (0,0,0))
        changed=[]
        for i,p in points.items():
            local=p-pivot;desired=pivot+r@Vector((local.x*s.x,local.y*s.y,local.z*s.z))+translation
            new=inverse@(p+(desired-p)*weights[i]);changed.append((i,new))
        for i,p in changed:ob.data.vertices[i].co=p
        ob.data.update();return {'object':ob.name,'edited_vertices':sum(w>0 for w in weights.values()),'topology_revision':topology(ob.data)}

    def mesh_flatten(self,object,normal,strength=1,**options):
        n=Vector(normal)
        if n.length<1e-8:raise ValueError('Plane normal must be nonzero')
        n.normalize();ob,points,pivot,inverse,weights=self._region(object,**options)
        for i,p in points.items():ob.data.vertices[i].co=inverse@(p-n*(p-pivot).dot(n)*weights[i]*strength)
        ob.data.update();return {'object':ob.name,'edited_vertices':len(points)}

    def mesh_smooth(self,object,iterations=1,strength=.5,**options):
        ob,points,pivot,inverse,weights=self._region(object,**options)
        adjacent={i:[] for i in range(len(ob.data.vertices))}
        for edge in ob.data.edges:
            a,b=edge.vertices;adjacent[a].append(b);adjacent[b].append(a)
        coordinates=[v.co.copy() for v in ob.data.vertices]
        for _ in range(iterations):
            changes={}
            for i in points:
                if adjacent[i]:
                    mean=sum((coordinates[j] for j in adjacent[i]),Vector())/len(adjacent[i])
                    changes[i]=coordinates[i].lerp(mean,strength*weights[i])
            for i,p in changes.items():coordinates[i]=p
        for i in points:ob.data.vertices[i].co=coordinates[i]
        ob.data.update();return {'object':ob.name,'edited_vertices':len(points),'iterations':iterations}

    def mesh_bridge_loops(self,object,first,second,closed=True,align=False):
        ob=resolve(object,'MESH',True)
        index_check(first+second,len(ob.data.vertices))
        if len(first)!=len(second) or len(first)<2:raise ValueError('Loops must have matching point counts')
        if align and closed:
            shift=min(range(len(second)),key=lambda k:sum((ob.data.vertices[a].co-ob.data.vertices[second[(i+k)%len(second)]].co).length_squared for i,a in enumerate(first)))
            second=second[shift:]+second[:shift]
        with bm_edit(ob) as bm:
            for i in range(len(first) if closed else len(first)-1):
                j=(i+1)%len(first);bm.faces.new([bm.verts[first[i]],bm.verts[first[j]],bm.verts[second[j]],bm.verts[second[i]]])
        return info(ob)

    def mesh_slide(self,object,indices,towards,factor=.5):
        ob=resolve(object,'MESH',True);index_check(indices,len(ob.data.vertices));index_check(towards,len(ob.data.vertices))
        if len(indices)!=len(towards):raise ValueError('Pair lengths differ')
        guarded(ob,indices)
        edges={frozenset(e.vertices) for e in ob.data.edges}
        if any(frozenset((a,b)) not in edges for a,b in zip(indices,towards)):raise ValueError('Slide targets must be directly connected neighbors')
        changes=[ob.data.vertices[a].co.lerp(ob.data.vertices[b].co,factor) for a,b in zip(indices,towards)]
        for i,p in zip(indices,changes):ob.data.vertices[i].co=p
        ob.data.update();return info(ob)

    def mesh_cut(self,object,point,normal,clear_inner=False,clear_outer=False,fill=False):
        ob=resolve(object,'MESH',True)
        if Vector(normal).length<1e-8:raise ValueError('Plane normal must be nonzero')
        with bm_edit(ob) as bm:
            result=bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),dist=1e-6,plane_co=Vector(point),plane_no=Vector(normal).normalized(),clear_inner=clear_inner,clear_outer=clear_outer)
            if fill:
                edges=[e for e in result['geom_cut'] if isinstance(e,bmesh.types.BMEdge) and e.is_boundary]
                if edges:bmesh.ops.holes_fill(bm,edges=edges,sides=0)
        return info(ob)

    def sculpt_grab(self,object,strength=1,**options):
        delta=options.pop('delta',None)
        if delta is None:raise ValueError('Grab needs a delta')
        options.pop('normal',None);options.pop('iterations',None)
        result=self.mesh_region_transform(object,delta=list(Vector(delta)*strength),**options);result['implementation']='geometry';return result

    def sculpt_inflate(self,object,strength=.05,**options):
        ob,points,pivot,inverse,weights=self._region(object,**options)
        for i in points:ob.data.vertices[i].co+=ob.data.vertices[i].normal*strength*weights[i]
        ob.data.update();return {'object':ob.name,'edited_vertices':len(points),'implementation':'geometry'}

    def sculpt_smooth(self,object,strength=.5,iterations=1,**options):
        options.pop('normal',None)
        result=self.mesh_smooth(object,iterations,max(0,min(1,strength)),**options);result['implementation']='geometry';return result

    def sculpt_flatten(self,object,normal=(0,0,1),strength=1,**options):
        options.pop('iterations',None)
        result=self.mesh_flatten(object,normal,max(0,min(1,strength)),**options);result['implementation']='geometry';return result

    def sculpt_mask(self,object,name,indices,weight=1,clear=False):
        ob=resolve(object,'MESH',True);index_check(indices,len(ob.data.vertices));guarded(ob,indices)
        group=ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
        if clear:group.remove(indices)
        else:group.add(indices,weight,'REPLACE')
        return {'object':ob.name,'mask':group.name,'count':len(indices)}

    def sculpt_symmetrize(self,object,axis='X',direction='positive_to_negative',tolerance=.001):
        from mathutils.kdtree import KDTree
        ob=resolve(object,'MESH',True);axis_index='XYZ'.index(axis);sign=1 if direction=='positive_to_negative' else -1
        source=[v for v in ob.data.vertices if v.co[axis_index]*sign>tolerance]
        tree=KDTree(len(ob.data.vertices))
        for v in ob.data.vertices:tree.insert(v.co,v.index)
        tree.balance();changes=[];unmatched=0
        for v in source:
            p=v.co.copy();p[axis_index]*=-1;_,index,distance=tree.find(p)
            if distance<=tolerance:changes.append((index,p))
            else:unmatched+=1
        guarded(ob,[i for i,p in changes])
        for i,p in changes:ob.data.vertices[i].co=p
        ob.data.update();return {'object':ob.name,'matched_vertices':len(changes),'unmatched_vertices':unmatched}

    def recipe_inspect(self,object):
        ob=resolve(object)
        if not ob.get('bb_recipe'):raise BridgeError('RECIPE_NOT_FOUND',ob.name)
        return {'object':info(ob),'recipe':json.loads(ob['bb_recipe'])}

    def recipe_replay(self,object,name,parameters=None,collection=None):
        recipe=self.recipe_inspect(object)['recipe'];args={**recipe['args'],**(parameters or {}),'name':name}
        if collection is not None:args['collection']=collection
        args={k:v for k,v in args.items() if v is not None}
        from ..catalog import OPS,validate
        validate(args,OPS[recipe['operation']]['inputSchema'])
        return self.execute(recipe['operation'],args)

    def geometry_nodes_inspect(self,object,modifier):
        ob=resolve(object);mod=ob.modifiers.get(modifier)
        if not mod or mod.type!='NODES' or not mod.node_group:raise ValueError('Geometry Nodes modifier not found')
        sockets=[]
        for item in mod.node_group.interface.items_tree:
            if item.item_type=='SOCKET' and item.in_out=='INPUT':
                value=geometry_node_input(mod,item.identifier)
                if hasattr(value,'to_list'):value=value.to_list()
                elif hasattr(value,'__len__') and not isinstance(value,str):value=list(value)
                sockets.append({'name':item.name,'identifier':item.identifier,'socket_type':item.socket_type,'value':value if isinstance(value,(str,int,float,bool,list,type(None))) else str(value)})
        return {'object':ob.name,'modifier':mod.name,'node_group':mod.node_group.name,'inputs':sockets,'evaluated':self.mesh_inspect(object,limit=1,mode='evaluated') if ob.type=='MESH' else None}

    def geometry_nodes_set_input(self,object,modifier,identifier,value):
        ob=resolve(object,writable=True);guarded(ob,topology_change=True)
        details=self.geometry_nodes_inspect(object,modifier);socket=next((s for s in details['inputs'] if s['identifier']==identifier),None)
        if not socket or socket['socket_type'] not in ('NodeSocketFloat','NodeSocketInt','NodeSocketBool','NodeSocketVector'):
            raise BridgeError('UNSUPPORTED_CAPABILITY','Only exposed numeric/bool/vector inputs supported')
        kind=socket['socket_type']
        if kind=='NodeSocketVector' and (not isinstance(value,list) or len(value)!=3):raise ValueError('Vector needs three components')
        if kind=='NodeSocketBool' and not isinstance(value,bool):raise ValueError('Boolean required')
        if kind in ('NodeSocketFloat','NodeSocketInt','NodeSocketVector'):
            values=value if kind=='NodeSocketVector' else [value]
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):raise ValueError('Finite numeric socket value required')
            if kind=='NodeSocketInt' and not isinstance(value,int):raise ValueError('Integer socket value required')
            interface=next(i for i in ob.modifiers[modifier].node_group.interface.items_tree if i.item_type=='SOCKET' and i.identifier==identifier)
            if hasattr(interface,'min_value') and any(v<interface.min_value or v>interface.max_value for v in values):raise ValueError('Socket value outside declared range')
        mod=ob.modifiers[modifier]
        if hasattr(mod,'properties'):
            input_socket=getattr(mod.properties.inputs,identifier,None)
            if not input_socket or not hasattr(input_socket,'value'):raise BridgeError('UNSUPPORTED_CAPABILITY','Socket has no editable value in this Blender version')
            if getattr(input_socket,'type','VALUE')!='VALUE':raise BridgeError('UNSUPPORTED_CAPABILITY','Attribute-driven sockets require an explicit attribute workflow')
            input_socket.value=value
        else:mod[identifier]=value
        ob.update_tag();bpy.context.view_layer.update()
        return self.geometry_nodes_inspect(object,modifier)
