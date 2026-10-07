"""Native UV and PBR editing with measurable UV coverage."""
from contextlib import contextmanager
import math
import bpy
from mathutils import Vector
from .common import resolve, guarded, index_check, material_state
from ..core import BridgeError
from ..operations import selected


def uv_triangles(ob):
    mesh=ob.data;mesh.calc_loop_triangles()
    if not mesh.uv_layers.active: raise BridgeError('UV_MISSING',ob.name)
    uv=mesh.uv_layers.active.data
    for tri in mesh.loop_triangles:
        yield tri, [Vector(uv[i].uv) for i in tri.loops]


def raster_triangle(points, resolution):
    """Yield pixel-center barycentric coordinates. Edge ownership uses face sets."""
    import numpy as np
    a,b,c=[np.array(p[:2],dtype=float)*resolution for p in points]
    lo=np.maximum(0,np.floor(np.minimum(np.minimum(a,b),c)).astype(int))
    hi=np.minimum(resolution-1,np.ceil(np.maximum(np.maximum(a,b),c)).astype(int))
    if np.any(hi<lo): return
    den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(den)<1e-12: return
    xx,yy=np.meshgrid(np.arange(lo[0],hi[0]+1)+.5,np.arange(lo[1],hi[1]+1)+.5)
    u=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den
    v=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den;w=1-u-v
    rows,cols=np.where((u>=1e-7)&(v>=1e-7)&(w>=1e-7))
    for row,col in zip(rows.tolist(),cols.tolist()):
        yield int(lo[0]+col),int(lo[1]+row),(float(u[row,col]),float(v[row,col]),float(w[row,col]))


@contextmanager
def uv_context(ob):
    mesh=ob.data
    flags=([v.select for v in mesh.vertices],[e.select for e in mesh.edges],[p.select for p in mesh.polygons])
    try:
        with selected([ob]):
            for p in mesh.polygons:p.select=True
            bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
            try:yield
            finally:
                if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
    finally:
        for elements,values in zip((mesh.vertices,mesh.edges,mesh.polygons),flags):
            for element,value in zip(elements,values):element.select=value


def uv_islands(mesh):
    if not mesh.uv_layers.active: return []
    uv=mesh.uv_layers.active.data;owners={};adj={p.index:set() for p in mesh.polygons}
    for p in mesh.polygons:
        loops=list(p.loop_indices)
        for a,b in zip(loops,loops[1:]+loops[:1]):
            va,vb=mesh.loops[a].vertex_index,mesh.loops[b].vertex_index
            edge=tuple(sorted((va,vb)))
            key=(edge,tuple(round(x,6) for i in ((a,b) if va<vb else (b,a)) for x in uv[i].uv))
            for other in owners.get(key,[]):adj[p.index].add(other);adj[other].add(p.index)
            owners.setdefault(key,[]).append(p.index)
    remaining=set(adj);islands=[]
    while remaining:
        stack=[remaining.pop()];component=[]
        while stack:
            face=stack.pop();component.append(face);next_faces=adj[face]&remaining;remaining-=next_faces;stack.extend(next_faces)
        islands.append(component)
    return islands


class SurfaceOps:
    def uv_unwrap(self, object, method='smart', margin=.02):
        ob=resolve(object,'MESH',True);guarded(ob)
        with uv_context(ob):
            if method=='smart':bpy.ops.uv.smart_project(island_margin=margin)
            else:bpy.ops.uv.unwrap(method='ANGLE_BASED' if method=='angle_based' else 'CONFORMAL',margin=margin)
        return self.uv_inspect(object)

    def uv_mark_seams(self, object, edges=None, angle_degrees=None, clear=False):
        ob=resolve(object,'MESH',True);guarded(ob);mesh=ob.data
        if edges is None and angle_degrees is None and not clear:raise ValueError('Explicit edges, angle, or clear required')
        chosen=set(edges or []);index_check(list(chosen),len(mesh.edges))
        if angle_degrees is not None:
            owners={e.index:[] for e in mesh.edges}
            for p in mesh.polygons:
                for loop in p.loop_indices:owners[mesh.loops[loop].edge_index].append(p)
            for edge,faces in owners.items():
                if len(faces)!=2 or math.degrees(faces[0].normal.angle(faces[1].normal))>=angle_degrees:chosen.add(edge)
        if clear:
            for edge in mesh.edges:edge.use_seam=False
        for index in chosen:mesh.edges[index].use_seam=True
        return {'object':ob.name,'seam_edges':[e.index for e in mesh.edges if e.use_seam]}

    def uv_pack(self, object, margin=.02, rotate=True):
        ob=resolve(object,'MESH',True);guarded(ob)
        if not ob.data.uv_layers.active:raise BridgeError('UV_MISSING',ob.name)
        with uv_context(ob):
            bpy.ops.uv.select_all(action='SELECT');bpy.ops.uv.pack_islands(margin=margin,rotate=rotate,margin_method='FRACTION')
        return self.uv_inspect(object)

    def uv_inspect(self, object, resolution=1024):
        ob=resolve(object,'MESH');mesh=ob.data
        if not mesh.uv_layers.active:return {'object':ob.name,'state':'missing','islands':0}
        area=0;uv_area=0
        for tri,points in uv_triangles(ob):
            a,b,c=[ob.matrix_world@mesh.vertices[i].co for i in tri.vertices]
            area+=(b-a).cross(c-a).length/2
            a,b,c=points;uv_area+=abs((b-a).x*(c-a).y-(b-a).y*(c-a).x)/2
        scale=bpy.context.scene.unit_settings.scale_length
        return {'object':ob.name,'state':'present','layers':[l.name for l in mesh.uv_layers],
                'islands':len(uv_islands(mesh)),'surface_area_m2':area*scale*scale,'uv_area':uv_area,
                'pixels_per_meter':resolution*math.sqrt(uv_area/(area*scale*scale)) if area else None,'resolution':resolution}

    def uv_set_density(self, object, pixels_per_meter, resolution):
        ob=resolve(object,'MESH',True);guarded(ob);current=self.uv_inspect(object,resolution)
        density=current.get('pixels_per_meter')
        if not density:raise ValueError('Nonzero surface/UV area required')
        factor=pixels_per_meter/density;uv=ob.data.uv_layers.active.data
        for faces in uv_islands(ob.data):
            loops=[i for p in faces for i in ob.data.polygons[p].loop_indices]
            center=sum((uv[i].uv for i in loops),Vector((0,0)))/len(loops)
            for i in loops:uv[i].uv=center+(uv[i].uv-center)*factor
        return {**self.uv_inspect(object,resolution),'bounds_must_be_revalidated':True}

    def uv_transform(self, object, faces=None, offset=(0,0), scale=(1,1), rotation=0):
        ob=resolve(object,'MESH',True);guarded(ob);mesh=ob.data
        indices=faces if faces is not None else list(range(len(mesh.polygons)));index_check(indices,len(mesh.polygons))
        if not mesh.uv_layers.active:raise BridgeError('UV_MISSING',ob.name)
        loops=[i for f in indices for i in mesh.polygons[f].loop_indices];uv=mesh.uv_layers.active.data
        for i in loops:
            x,y=uv[i].uv;x*=scale[0];y*=scale[1]
            uv[i].uv=(x*math.cos(rotation)-y*math.sin(rotation)+offset[0],x*math.sin(rotation)+y*math.cos(rotation)+offset[1])
        return self.uv_inspect(object)

    def uv_validate(self, object, resolution=256, allow_overlap=False, padding_pixels=2):
        if not 16<=resolution<=2048:raise ValueError('Validation raster resolution must be 16..2048')
        if not 0<=padding_pixels<=32:raise ValueError('Padding must be 0..32 pixels')
        ob=resolve(object,'MESH');mesh=ob.data;islands=uv_islands(mesh)
        if not mesh.uv_layers.active:return {'state':'failed','reason':'UV_MISSING'}
        import numpy as np
        face_island={f:i for i,faces in enumerate(islands) for f in faces};owner=np.full((resolution,resolution),-1,dtype=np.int32)
        overlap=set();coverage=0
        for tri,points in uv_triangles(ob):
            for x,y,weights in raster_triangle(points,resolution):
                previous=int(owner[y,x]);face=tri.polygon_index
                if previous>=0 and previous!=face:overlap.add((x,y))
                elif previous<0:coverage+=1
                owner[y,x]=face
        island_grid=np.full_like(owner,-1)
        for face,island in face_island.items():island_grid[owner==face]=island
        collisions=0
        for dy in range(-padding_pixels,padding_pixels+1):
            for dx in range(-padding_pixels,padding_pixels+1):
                if dx==dy==0 or dx*dx+dy*dy>padding_pixels*padding_pixels:continue
                a=island_grid[max(0,dy):min(resolution,resolution+dy),max(0,dx):min(resolution,resolution+dx)]
                b=island_grid[max(0,-dy):min(resolution,resolution-dy),max(0,-dx):min(resolution,resolution-dx)]
                collisions+=int(np.count_nonzero((a>=0)&(b>=0)&(a!=b)))
        coords=[v.uv for v in mesh.uv_layers.active.data]
        outside=sum(any(c<0 or c>1 for c in p) for p in coords)
        passed=not outside and (allow_overlap or not overlap) and not collisions
        return {'state':'passed' if passed else 'failed','out_of_bounds_loops':outside,'overlap_pixels':len(overlap),
                'overlap_policy':'intentional_allowed' if allow_overlap else 'disallowed','padding_conflicts':collisions,
                'padding_pixels':padding_pixels,'coverage_ratio':coverage/(resolution*resolution),'raster_resolution':resolution,
                'subpixel_overlap':'not_measured','islands':len(islands)}

    def _material(self,name):
        material=bpy.data.materials.get(name)
        if not material:raise ValueError('Material not found: '+name)
        return material

    def _material_guard(self, material):
        for ob in bpy.context.scene.objects:
            if any(s.material==material for s in ob.material_slots):guarded(ob)

    def material_inspect(self,material):return material_state(self._material(material))

    def material_update(self, material, color=None, metallic=None, roughness=None, emission=None, emission_strength=None, opacity=None, noise_scale=None, bump_strength=None):
        mat=self._material(material);self._material_guard(mat);mat.use_nodes=True
        node=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
        if not node:raise ValueError('Principled BSDF required')
        values={'Base Color':color,'Metallic':metallic,'Roughness':roughness,'Emission Color':emission,'Emission Strength':emission_strength,'Alpha':opacity}
        for key,value in values.items():
            if value is not None:node.inputs[key].default_value=value
        if color is not None:mat.diffuse_color=color
        if metallic is not None:mat.metallic=metallic
        if roughness is not None:mat.roughness=roughness
        if noise_scale is not None:
            noise=mat.node_tree.nodes.get('BridgeNoise') or mat.node_tree.nodes.new('ShaderNodeTexNoise');noise.name='BridgeNoise';noise.inputs['Scale'].default_value=noise_scale
            bump=mat.node_tree.nodes.get('BridgeBump') or mat.node_tree.nodes.new('ShaderNodeBump');bump.name='BridgeBump'
            bump.inputs['Strength'].default_value=bump_strength if bump_strength is not None else .1
            mat.node_tree.links.new(noise.outputs['Fac'],bump.inputs['Height']);mat.node_tree.links.new(bump.outputs['Normal'],node.inputs['Normal'])
        return self.material_inspect(material)

    def material_copy(self,material,name):
        if name in bpy.data.materials:raise ValueError('Material name conflict')
        mat=self._material(material).copy();mat.name=name
        return self.material_inspect(name)

    def material_relink(self,material,channel,path,flip_normal_y=False):
        mat=self._material(material);self._material_guard(mat);mat.use_nodes=True
        principled=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
        if not principled:raise ValueError('Principled BSDF required')
        source=self.state.input_path(path);image=bpy.data.images.load(str(source),check_existing=False)
        image.colorspace_settings.name='sRGB' if channel in ('BaseColor','Emissive') else 'Non-Color'
        tree=mat.node_tree;node=tree.nodes.get('Bridge_'+channel) or tree.nodes.new('ShaderNodeTexImage');node.name='Bridge_'+channel;node.image=image
        output=node.outputs['Color']
        if channel=='Normal':
            if flip_normal_y:
                separate=tree.nodes.get('BridgeNormalSeparate') or tree.nodes.new('ShaderNodeSeparateColor');separate.name='BridgeNormalSeparate'
                combine=tree.nodes.get('BridgeNormalCombine') or tree.nodes.new('ShaderNodeCombineColor');combine.name='BridgeNormalCombine'
                invert=tree.nodes.get('BridgeNormalInvertY') or tree.nodes.new('ShaderNodeMath');invert.name='BridgeNormalInvertY';invert.operation='SUBTRACT';invert.inputs[0].default_value=1
                tree.links.new(output,separate.inputs[0]);tree.links.new(separate.outputs['Red'],combine.inputs['Red']);tree.links.new(separate.outputs['Blue'],combine.inputs['Blue'])
                tree.links.new(separate.outputs['Green'],invert.inputs[1]);tree.links.new(invert.outputs[0],combine.inputs['Green']);output=combine.outputs[0]
            normal=tree.nodes.get('BridgeNormalMap') or tree.nodes.new('ShaderNodeNormalMap');normal.name='BridgeNormalMap'
            tree.links.new(output,normal.inputs['Color']);output=normal.outputs['Normal']
        keys={'BaseColor':'Base Color','Normal':'Normal','Roughness':'Roughness','Metallic':'Metallic','Emissive':'Emission Color','Opacity':'Alpha'}
        if channel=='AO':
            # AO is retained as a separate data texture. Principled has no AO socket.
            node.label='AO data texture; multiply explicitly when target workflow needs it'
        else:tree.links.new(output,principled.inputs[keys[channel]])
        return {'material':material,'channel':channel,'image':image.name,'colorspace':image.colorspace_settings.name,'normal_y_flipped':bool(flip_normal_y and channel=='Normal'),'connected':channel!='AO'}
