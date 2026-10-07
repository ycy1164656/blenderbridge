"""Deterministic contour/loft calculations, independent of Blender and devices."""
import math


def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def norm(a): return math.sqrt(dot(a,a))


def validate_ring(points, tolerance=1e-7):
    if len(points)<3 or any(len(p)!=3 or not all(math.isfinite(x) for x in p) for p in points):
        raise ValueError('A finite 3D ring needs at least three points')
    if any(norm(sub(points[i],points[(i+1)%len(points)])) <= tolerance for i in range(len(points))):
        raise ValueError('Contour has coincident adjacent points')
    normal = [0.0,0.0,0.0]
    for a,b in zip(points,points[1:]+points[:1]):
        c=cross(a,b)
        normal=[normal[i]+c[i] for i in range(3)]
    length=norm(normal)
    if length<=tolerance: raise ValueError('Contour has zero area')
    normal=[x/length for x in normal]
    extent=max(norm(sub(p,points[0])) for p in points)
    if any(abs(dot(sub(p,points[0]),normal)) > tolerance*max(1,extent)*10 for p in points):
        raise ValueError('Each contour must be planar')
    axis=max(range(3),key=lambda i:abs(normal[i]))
    xy=[tuple(p[i] for i in range(3) if i!=axis) for p in points]
    def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def intersects(a,b,c,d):
        oa,ob,oc,od=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
        if oa*ob < -tolerance and oc*od < -tolerance: return True
        def on(p,q,r): return abs(orient(p,q,r))<=tolerance and all(min(p[i],q[i])-tolerance<=r[i]<=max(p[i],q[i])+tolerance for i in (0,1))
        return on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b)
    for i in range(len(xy)):
        for j in range(i+1,len(xy)):
            if j in (i,(i+1)%len(xy)) or i==(j+1)%len(xy): continue
            if intersects(xy[i],xy[(i+1)%len(xy)],xy[j],xy[(j+1)%len(xy)]):
                raise ValueError('Contour self-intersects')
    return normal


def align_ring(previous,current):
    n=len(current)
    shift=min(range(n),key=lambda k:sum(dot(sub(previous[i],current[(i+k)%n]),sub(previous[i],current[(i+k)%n])) for i in range(n)))
    return current[shift:]+current[:shift]


def loft(sections,cap=True,align=True):
    if len(sections)<2 or len({len(s) for s in sections})!=1:
        raise ValueError('Loft requires at least two equally sampled rings')
    rings=[[tuple(p) for p in s] for s in sections]
    normals=[validate_ring(s) for s in rings]
    for i in range(1,len(rings)):
        if dot(normals[i-1],normals[i]) < -0.95:
            raise ValueError('Cross-section winding reverses; fix the declared contour order')
        if align: rings[i]=align_ring(rings[i-1],rings[i])
        if max(norm(sub(a,b)) for a,b in zip(rings[i-1],rings[i])) <= 1e-7:
            raise ValueError('Consecutive sections overlap exactly')
    n=len(rings[0]); faces=[]
    for j in range(len(rings)-1):
        for i in range(n):
            k=(i+1)%n; faces.append([j*n+i,j*n+k,(j+1)*n+k,(j+1)*n+i])
    if cap:
        faces.insert(0,list(reversed(range(n))))
        faces.append(list(range((len(rings)-1)*n,len(rings)*n)))
    return [list(p) for s in rings for p in s],faces
