#!/usr/bin/env python3
from __future__ import annotations
import ast, cmath, datetime as dt, heapq, json, math, operator, sys
from decimal import Decimal, getcontext
from pathlib import Path

COMMANDS=[
"bigint-modular-power","bigint-extended-gcd","bigfloat-sqrt-calc","bigfloat-pi-chudnovsky","matrix-determinant-2d","matrix-inverse-3d","matrix-eigen-evaluator","vector-dot-cross-prod","linear-regression-ols","polynomial-root-finder","runge-kutta-integrator","simpson-integral-calc","fft-fourier-transform","dft-discrete-fourier","complex-number-calc","quaternion-rotation","normal-distribution-cdf","poisson-prob-calc","binomial-distribution","chi-square-statistic","student-t-distribution","standard-deviation-calc","covariance-matrix-cli","spearman-rank-calc","pearson-correlation","k-means-clustering-cli","dijkstra-shortest-path","a-star-path-finder","bellman-ford-detector","topological-sorter","bipartite-graph-match","spanning-tree-kruskal","convex-hull-graham","voronoi-diagram-cli","delaunay-triangulate","geodesic-distance-vin","haversine-distance-cli","utm-lat-long-converter","coordinate-proj-proj4","astronomical-julian","sidereal-time-calc","solar-zenith-angle","temperature-scale-conv","pressure-unit-calc","energy-joule-kwh-conv","speed-of-sound-calc","doppler-shift-calc","signal-to-noise-ratio","boolean-logic-solver","truth-table-generator"
]

def emit(x):
    if isinstance(x,(dict,list,tuple)): print(json.dumps(x,indent=2,default=lambda z:[z.real,z.imag] if isinstance(z,complex) else str(z)))
    else: print(x)
def need(a,n):
    if len(a)<n: raise SystemExit(f"expected at least {n} arguments")
def seq(s):
    try:
        v=json.loads(s)
        if isinstance(v,list): return [float(x) for x in v]
    except Exception: pass
    return [float(x) for x in s.replace(";"," ").replace(","," ").split()]
def matrix(s):
    try:
        v=json.loads(Path(s).read_text() if Path(s).exists() else s)
        return [[float(x) for x in r] for r in v]
    except Exception:
        return [seq(r) for r in s.split(";") if r.strip()]
def points(s):
    return [tuple(map(float,p)) for p in matrix(s)]
def egcd(a,b):
    if b==0:return (abs(a),1 if a>=0 else -1,0)
    g,x1,y1=egcd(b,a%b); return g,y1,x1-(a//b)*y1
def det(a):
    n=len(a)
    if any(len(r)!=n for r in a): raise ValueError("matrix must be square")
    a=[r[:] for r in a]; d=1.0
    for i in range(n):
        p=max(range(i,n),key=lambda r:abs(a[r][i]))
        if abs(a[p][i])<1e-15:return 0.0
        if p!=i:a[i],a[p]=a[p],a[i];d*=-1
        piv=a[i][i];d*=piv
        for r in range(i+1,n):
            f=a[r][i]/piv
            for c in range(i+1,n): a[r][c]-=f*a[i][c]
    return d
def inv(a):
    n=len(a); aug=[a[i][:]+[1.0 if i==j else 0.0 for j in range(n)] for i in range(n)]
    for i in range(n):
        p=max(range(i,n),key=lambda r:abs(aug[r][i]))
        if abs(aug[p][i])<1e-15: raise ValueError("singular")
        aug[i],aug[p]=aug[p],aug[i]; q=aug[i][i]; aug[i]=[x/q for x in aug[i]]
        for r in range(n):
            if r==i:continue
            f=aug[r][i]; aug[r]=[aug[r][c]-f*aug[i][c] for c in range(2*n)]
    return [r[n:] for r in aug]
def safe_expr(expr,**vals):
    allowed={k:getattr(math,k) for k in ("sin","cos","tan","sqrt","exp","log","log10","fabs","pi","e")}
    allowed.update(vals)
    tree=ast.parse(expr,mode="eval")
    ok=(ast.Expression,ast.BinOp,ast.UnaryOp,ast.Constant,ast.Name,ast.Load,ast.Call,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow,ast.Mod,ast.USub,ast.UAdd)
    for n in ast.walk(tree):
        if not isinstance(n,ok): raise ValueError("unsupported expression")
        if isinstance(n,ast.Name) and n.id not in allowed: raise ValueError("unknown name")
        if isinstance(n,ast.Call) and (not isinstance(n.func,ast.Name) or n.func.id not in allowed): raise ValueError("unsafe call")
    return float(eval(compile(tree,"<expr>","eval"),{"__builtins__":{}},allowed))
def fft(a):
    n=len(a)
    if n<=1:return a
    if n&(n-1): return [sum(a[t]*cmath.exp(-2j*math.pi*k*t/n) for t in range(n)) for k in range(n)]
    e=fft(a[0::2]);o=fft(a[1::2]);return [e[k]+cmath.exp(-2j*math.pi*k/n)*o[k] for k in range(n//2)]+[e[k]-cmath.exp(-2j*math.pi*k/n)*o[k] for k in range(n//2)]
def corr(a,b):
    if len(a)!=len(b) or len(a)<2: raise ValueError("equal-length series required")
    ma=sum(a)/len(a);mb=sum(b)/len(b)
    num=sum((x-ma)*(y-mb) for x,y in zip(a,b)); den=math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
    return num/den if den else 0.0
def ranks(v):
    order=sorted(range(len(v)),key=v.__getitem__); out=[0.0]*len(v);i=0
    while i<len(order):
        j=i+1
        while j<len(order) and v[order[j]]==v[order[i]]:j+=1
        r=(i+j-1)/2+1
        for k in order[i:j]:out[k]=r
        i=j
    return out
def betacf(a,b,x):
    qab=a+b;qap=a+1;qam=a-1;c=1;d=1-qab*x/qap;d=1e-30 if abs(d)<1e-30 else d;d=1/d;h=d
    for m in range(1,201):
        m2=2*m; aa=m*(b-m)*x/((qam+m2)*(a+m2)); d=1+aa*d;d=1e-30 if abs(d)<1e-30 else d;c=1+aa/c;c=1e-30 if abs(c)<1e-30 else c;d=1/d;h*=d*c
        aa=-(a+m)*(qab+m)*x/((a+m2)*(qap+m2));d=1+aa*d;d=1e-30 if abs(d)<1e-30 else d;c=1+aa/c;c=1e-30 if abs(c)<1e-30 else c;d=1/d;delta=d*c;h*=delta
        if abs(delta-1)<3e-12:break
    return h
def ibeta(a,b,x):
    if x<=0:return 0.0
    if x>=1:return 1.0
    bt=math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log(1-x))
    return bt*betacf(a,b,x)/a if x<(a+1)/(a+b+2) else 1-bt*betacf(b,a,1-x)/b
def t_two_tail(t,df):
    x=df/(df+t*t);return ibeta(df/2,0.5,x)
def poly_eval(c,x):
    y=0
    for a in c:y=y*x+a
    return y
def roots_durand(c):
    while c and abs(c[0])<1e-15:c=c[1:]
    n=len(c)-1
    if n<=0:return []
    c=[z/c[0] for z in c]; rs=[cmath.rect(0.4+0.9*i/n,2*math.pi*i/n) for i in range(n)]
    for _ in range(200):
        nr=[]
        for i,r in enumerate(rs):
            den=1
            for j,s in enumerate(rs):
                if i!=j:den*=r-s
            nr.append(r-poly_eval(c,r)/(den or 1e-15))
        if max(abs(nr[i]-rs[i]) for i in range(n))<1e-12:rs=nr;break
        rs=nr
    return rs
def parse_graph(s):
    return json.loads(Path(s).read_text() if Path(s).exists() else s)
def dijkstra(g,start,end):
    q=[(0,start,[])];seen=set()
    while q:
        d,u,path=heapq.heappop(q)
        if u in seen:continue
        seen.add(u);path=path+[u]
        if u==end:return d,path
        for v,w in g.get(u,{}).items():
            if v not in seen:heapq.heappush(q,(d+float(w),v,path))
    return math.inf,[]
def astar(grid,start,end):
    H=len(grid);W=len(grid[0]);s=tuple(start);e=tuple(end);q=[(0,s)];g={s:0};prev={}
    h=lambda p:abs(p[0]-e[0])+abs(p[1]-e[1])
    while q:
        _,u=heapq.heappop(q)
        if u==e:break
        for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
            v=(u[0]+dy,u[1]+dx)
            if 0<=v[0]<H and 0<=v[1]<W and not grid[v[0]][v[1]]:
                nd=g[u]+1
                if nd<g.get(v,1e99):g[v]=nd;prev[v]=u;heapq.heappush(q,(nd+h(v),v))
    if e not in g:return []
    p=[e]
    while p[-1]!=s:p.append(prev[p[-1]])
    return p[::-1]
def bellman(n,edges,start):
    d=[math.inf]*n;d[start]=0
    for _ in range(n-1):
        changed=False
        for u,v,w in edges:
            u=int(u);v=int(v);w=float(w)
            if d[u]+w<d[v]:d[v]=d[u]+w;changed=True
        if not changed:break
    neg=any(d[int(u)]+float(w)<d[int(v)] for u,v,w in edges if d[int(u)]<math.inf)
    return d,neg
def topo(g):
    indeg={str(k):0 for k in g}
    for u,vs in g.items():
        for v in vs:indeg[str(v)]=indeg.get(str(v),0)+1
    q=[k for k,v in indeg.items() if v==0];out=[]
    while q:
        u=q.pop(0);out.append(u)
        for v in g.get(u,[]):v=str(v);indeg[v]-=1;q.append(v) if indeg[v]==0 else None
    return out if len(out)==len(indeg) else []
def hopcroft(g):
    U=list(g);pairU={u:None for u in U}; V={v for vs in g.values() for v in vs};pairV={v:None for v in V};dist={}
    def bfs():
        q=[];found=False
        for u in U:
            if pairU[u] is None:dist[u]=0;q.append(u)
            else:dist[u]=1e9
        while q:
            u=q.pop(0)
            for v in g[u]:
                pu=pairV[v]
                if pu is None:found=True
                elif dist[pu]==1e9:dist[pu]=dist[u]+1;q.append(pu)
        return found
    def dfs(u):
        for v in g[u]:
            pu=pairV[v]
            if pu is None or (dist.get(pu)==dist[u]+1 and dfs(pu)):pairU[u]=v;pairV[v]=u;return True
        dist[u]=1e9;return False
    while bfs():
        for u in U:
            if pairU[u] is None:dfs(u)
    return {u:v for u,v in pairU.items() if v is not None}
class DSU:
    def __init__(self,n):self.p=list(range(n))
    def f(self,x):
        while self.p[x]!=x:self.p[x]=self.p[self.p[x]];x=self.p[x]
        return x
    def u(self,a,b):
        a=self.f(a);b=self.f(b)
        if a==b:return False
        self.p[b]=a;return True
def hull(ps):
    ps=sorted(set(ps))
    if len(ps)<=1:return ps
    cross=lambda o,a,b:(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo=[]
    for p in ps:
        while len(lo)>=2 and cross(lo[-2],lo[-1],p)<=0:lo.pop()
        lo.append(p)
    hi=[]
    for p in reversed(ps):
        while len(hi)>=2 and cross(hi[-2],hi[-1],p)<=0:hi.pop()
        hi.append(p)
    return lo[:-1]+hi[:-1]
def clip(poly,a,b,c):
    out=[]
    def inside(p):return a*p[0]+b*p[1]<=c+1e-12
    def inter(p,q):
        dp=a*(q[0]-p[0])+b*(q[1]-p[1])
        if abs(dp)<1e-15:return p
        t=(c-a*p[0]-b*p[1])/dp;return (p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1]))
    for i,p in enumerate(poly):
        q=poly[(i+1)%len(poly)];ip,iq=inside(p),inside(q)
        if ip and iq:out.append(q)
        elif ip and not iq:out.append(inter(p,q))
        elif not ip and iq:out.extend([inter(p,q),q])
    return out
def voronoi(ps,bbox):
    x0,y0,x1,y1=bbox; base=[(x0,y0),(x1,y0),(x1,y1),(x0,y1)];cells=[]
    for i,p in enumerate(ps):
        poly=base[:]
        for j,q in enumerate(ps):
            if i==j:continue
            a=2*(q[0]-p[0]);b=2*(q[1]-p[1]);c=q[0]**2+q[1]**2-p[0]**2-p[1]**2
            poly=clip(poly,a,b,c)
            if not poly:break
        cells.append(poly)
    return cells
def circum(a,b,c):
    d=2*(a[0]*(b[1]-c[1])+b[0]*(c[1]-a[1])+c[0]*(a[1]-b[1]))
    if abs(d)<1e-12:return None
    ux=((a[0]**2+a[1]**2)*(b[1]-c[1])+(b[0]**2+b[1]**2)*(c[1]-a[1])+(c[0]**2+c[1]**2)*(a[1]-b[1]))/d
    uy=((a[0]**2+a[1]**2)*(c[0]-b[0])+(b[0]**2+b[1]**2)*(a[0]-c[0])+(c[0]**2+c[1]**2)*(b[0]-a[0]))/d
    return (ux,uy),(ux-a[0])**2+(uy-a[1])**2
def delaunay(ps):
    n=len(ps); tris=[]
    for i in range(n):
        for j in range(i+1,n):
            for k in range(j+1,n):
                cc=circum(ps[i],ps[j],ps[k])
                if not cc:continue
                o,r2=cc
                if all(m in (i,j,k) or (ps[m][0]-o[0])**2+(ps[m][1]-o[1])**2>=r2-1e-10 for m in range(n)):tris.append((i,j,k))
    return tris
def vincenty(lat1,lon1,lat2,lon2):
    a=6378137.0;f=1/298.257223563;b=(1-f)*a
    p1=math.radians(lat1);p2=math.radians(lat2);L=math.radians(lon2-lon1);U1=math.atan((1-f)*math.tan(p1));U2=math.atan((1-f)*math.tan(p2));lam=L
    for _ in range(200):
        sl=math.sin(lam);cl=math.cos(lam);ss=math.sqrt((math.cos(U2)*sl)**2+(math.cos(U1)*math.sin(U2)-math.sin(U1)*math.cos(U2)*cl)**2)
        if ss==0:return 0.0
        cs=math.sin(U1)*math.sin(U2)+math.cos(U1)*math.cos(U2)*cl;sigma=math.atan2(ss,cs);sa=math.cos(U1)*math.cos(U2)*sl/ss;ca2=1-sa*sa
        c2sm=0 if ca2==0 else cs-2*math.sin(U1)*math.sin(U2)/ca2;C=f/16*ca2*(4+f*(4-3*ca2));prev=lam;lam=L+(1-C)*f*sa*(sigma+C*ss*(c2sm+C*cs*(-1+2*c2sm*c2sm)))
        if abs(lam-prev)<1e-12:break
    u2=ca2*(a*a-b*b)/(b*b);A=1+u2/16384*(4096+u2*(-768+u2*(320-175*u2)));B=u2/1024*(256+u2*(-128+u2*(74-47*u2)))
    ds=B*ss*(c2sm+B/4*(cs*(-1+2*c2sm*c2sm)-B/6*c2sm*(-3+4*ss*ss)*(-3+4*c2sm*c2sm)))
    return b*A*(sigma-ds)
def utm(lat,lon):
    zone=int((lon+180)/6)+1; lon0=math.radians((zone-1)*6-180+3); latr=math.radians(lat);lonr=math.radians(lon);a=6378137.0;e2=0.00669437999014;k0=.9996
    ep2=e2/(1-e2);N=a/math.sqrt(1-e2*math.sin(latr)**2);T=math.tan(latr)**2;C=ep2*math.cos(latr)**2;A=math.cos(latr)*(lonr-lon0)
    M=a*((1-e2/4-3*e2**2/64-5*e2**3/256)*latr-(3*e2/8+3*e2**2/32+45*e2**3/1024)*math.sin(2*latr)+(15*e2**2/256+45*e2**3/1024)*math.sin(4*latr)-(35*e2**3/3072)*math.sin(6*latr))
    E=k0*N*(A+(1-T+C)*A**3/6+(5-18*T+T*T+72*C-58*ep2)*A**5/120)+500000
    Nn=k0*(M+N*math.tan(latr)*(A*A/2+(5-T+9*C+4*C*C)*A**4/24+(61-58*T+T*T+600*C-330*ep2)*A**6/720))
    if lat<0:Nn+=10000000
    return zone,"N" if lat>=0 else "S",E,Nn
def julian(t):
    if t.tzinfo is None:t=t.replace(tzinfo=dt.timezone.utc)
    return t.timestamp()/86400+2440587.5
def bool_eval(expr,vals):
    tree=ast.parse(expr,mode="eval")
    ok=(ast.Expression,ast.Name,ast.Load,ast.Constant,ast.BoolOp,ast.UnaryOp,ast.And,ast.Or,ast.Not,ast.BinOp,ast.BitAnd,ast.BitOr,ast.BitXor)
    for n in ast.walk(tree):
        if not isinstance(n,ok):raise ValueError("boolean operators only")
        if isinstance(n,ast.Name) and n.id not in vals:raise ValueError("unknown variable")
    return bool(eval(compile(tree,"<bool>","eval"),{"__builtins__":{}},vals))
def main(cmd,a):
    if cmd not in COMMANDS:raise SystemExit("unknown command")
    if cmd=="bigint-modular-power":need(a,3);emit(pow(int(a[0]),int(a[1]),int(a[2])));return
    if cmd=="bigint-extended-gcd":need(a,2);g,x,y=egcd(int(a[0]),int(a[1]));emit({"gcd":g,"x":x,"y":y});return
    if cmd=="bigfloat-sqrt-calc":need(a,1);getcontext().prec=int(a[1]) if len(a)>1 else 50;emit(str(Decimal(a[0]).sqrt()));return
    if cmd=="bigfloat-pi-chudnovsky":
        digits=int(a[0]) if a else 50;getcontext().prec=digits+10;C=Decimal(426880)*Decimal(10005).sqrt();M=Decimal(1);L=Decimal(13591409);X=Decimal(1);K=Decimal(6);S=L
        for i in range(1,digits//14+2):M=(K**3-16*K)*M/(Decimal(i)**3);L+=Decimal(545140134);X*=Decimal(-262537412640768000);S+=M*L/X;K+=12
        emit(str(+(C/S))[:digits+2]);return
    if cmd=="matrix-determinant-2d":need(a,1);emit(det(matrix(a[0])));return
    if cmd=="matrix-inverse-3d":need(a,1);emit(inv(matrix(a[0])));return
    if cmd=="matrix-eigen-evaluator":
        need(a,1);m=matrix(a[0]);v=[1.0]*len(m)
        for _ in range(100):
            w=[sum(m[i][j]*v[j] for j in range(len(v))) for i in range(len(v))];n=math.sqrt(sum(x*x for x in w)) or 1;w=[x/n for x in w]
            if max(abs(w[i]-v[i]) for i in range(len(v)))<1e-10:v=w;break
            v=w
        lam=sum(v[i]*sum(m[i][j]*v[j] for j in range(len(v))) for i in range(len(v)));emit({"eigenvalue":lam,"eigenvector":v});return
    if cmd=="vector-dot-cross-prod":need(a,2);u=seq(a[0]);v=seq(a[1]);emit({"dot":sum(x*y for x,y in zip(u,v)),"cross":[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]],"norm_u":math.sqrt(sum(x*x for x in u))});return
    if cmd=="linear-regression-ols":need(a,2);x=seq(a[0]);y=seq(a[1]);mx=sum(x)/len(x);my=sum(y)/len(y);s=sum((z-mx)**2 for z in x);b=sum((z-mx)*(q-my) for z,q in zip(x,y))/s;emit({"slope":b,"intercept":my-b*mx});return
    if cmd=="polynomial-root-finder":need(a,1);emit([{"real":r.real,"imag":r.imag} for r in roots_durand(seq(a[0]))]);return
    if cmd=="runge-kutta-integrator":
        need(a,4);expr=a[0];x=float(a[1]);y=float(a[2]);h=float(a[3]);steps=int(a[4]) if len(a)>4 else 1
        for _ in range(steps):
            k1=safe_expr(expr,x=x,y=y);k2=safe_expr(expr,x=x+h/2,y=y+h*k1/2);k3=safe_expr(expr,x=x+h/2,y=y+h*k2/2);k4=safe_expr(expr,x=x+h,y=y+h*k3);y+=h*(k1+2*k2+2*k3+k4)/6;x+=h
        emit({"x":x,"y":y});return
    if cmd=="simpson-integral-calc":
        need(a,4);expr=a[0];lo=float(a[1]);hi=float(a[2]);n=int(a[3]);n+=n%2;h=(hi-lo)/n;s=safe_expr(expr,x=lo)+safe_expr(expr,x=hi)
        s+=4*sum(safe_expr(expr,x=lo+i*h) for i in range(1,n,2))+2*sum(safe_expr(expr,x=lo+i*h) for i in range(2,n,2));emit(s*h/3);return
    if cmd in ("fft-fourier-transform","dft-discrete-fourier"):need(a,1);z=[complex(x) for x in seq(a[0])];r=fft(z) if cmd.startswith("fft") else [sum(z[t]*cmath.exp(-2j*math.pi*k*t/len(z)) for t in range(len(z))) for k in range(len(z))];emit([{"real":x.real,"imag":x.imag} for x in r]);return
    if cmd=="complex-number-calc":need(a,3);op=a[0];x=complex(a[1]);y=complex(a[2]);r={"+":x+y,"-":x-y,"*":x*y,"/":x/y}[op];emit({"real":r.real,"imag":r.imag,"magnitude":abs(r),"phase":cmath.phase(r)});return
    if cmd=="quaternion-rotation":need(a,2);q=seq(a[0]);v=seq(a[1]);w,x,y,z=q;n=math.sqrt(sum(t*t for t in q));w,x,y,z=[t/n for t in q];m=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]];emit([sum(m[i][j]*v[j] for j in range(3)) for i in range(3)]);return
    if cmd=="normal-distribution-cdf":need(a,1);x=float(a[0]);mu=float(a[1]) if len(a)>1 else 0;s=float(a[2]) if len(a)>2 else 1;emit(.5*(1+math.erf((x-mu)/(s*math.sqrt(2)))));return
    if cmd=="poisson-prob-calc":need(a,2);la=float(a[0]);k=int(a[1]);emit(math.exp(-la)*la**k/math.factorial(k));return
    if cmd=="binomial-distribution":need(a,3);n=int(a[0]);k=int(a[1]);p=float(a[2]);emit(math.comb(n,k)*p**k*(1-p)**(n-k));return
    if cmd=="chi-square-statistic":need(a,2);o=seq(a[0]);e=seq(a[1]);emit(sum((x-y)**2/y for x,y in zip(o,e)));return
    if cmd=="student-t-distribution":need(a,2);emit({"two_tail_p":t_two_tail(abs(float(a[0])),int(a[1]))});return
    if cmd=="standard-deviation-calc":need(a,1);x=seq(a[0]);m=sum(x)/len(x);var=sum((z-m)**2 for z in x)/(len(x)-1 if len(x)>1 else 1);emit({"mean":m,"variance":var,"stddev":math.sqrt(var)});return
    if cmd=="covariance-matrix-cli":need(a,1);rows=matrix(a[0]);cols=list(zip(*rows));means=[sum(c)/len(c) for c in cols];emit([[sum((x-means[i])*(y-means[j]) for x,y in zip(cols[i],cols[j]))/(len(rows)-1) for j in range(len(cols))] for i in range(len(cols))]);return
    if cmd=="spearman-rank-calc":need(a,2);emit(corr(ranks(seq(a[0])),ranks(seq(a[1]))));return
    if cmd=="pearson-correlation":need(a,2);emit(corr(seq(a[0]),seq(a[1])));return
    if cmd=="k-means-clustering-cli":
        need(a,2);ps=points(a[0]);k=int(a[1]);cent=[list(ps[i%len(ps)]) for i in range(k)]
        for _ in range(100):
            groups=[[] for _ in range(k)]
            for p in ps:groups[min(range(k),key=lambda i:sum((p[d]-cent[i][d])**2 for d in range(len(p))))].append(p)
            nc=[[sum(p[d] for p in g)/len(g) for d in range(len(g[0]))] if g else cent[i] for i,g in enumerate(groups)]
            if max(sum((nc[i][d]-cent[i][d])**2 for d in range(len(nc[i]))) for i in range(k))<1e-12:cent=nc;break
            cent=nc
        emit({"centroids":cent,"clusters":[len(g) for g in groups]});return
    if cmd=="dijkstra-shortest-path":need(a,3);d,p=dijkstra(parse_graph(a[0]),a[1],a[2]);emit({"distance":d,"path":p});return
    if cmd=="a-star-path-finder":need(a,3);emit(astar(json.loads(a[0]),json.loads(a[1]),json.loads(a[2])));return
    if cmd=="bellman-ford-detector":need(a,3);d,n=bellman(int(a[0]),json.loads(a[1]),int(a[2]));emit({"distance":d,"negative_cycle":n});return
    if cmd=="topological-sorter":need(a,1);emit(topo(parse_graph(a[0])));return
    if cmd=="bipartite-graph-match":need(a,1);emit(hopcroft(parse_graph(a[0])));return
    if cmd=="spanning-tree-kruskal":need(a,2);n=int(a[0]);ed=sorted(json.loads(a[1]),key=lambda x:float(x[2]));ds=DSU(n);tree=[];cost=0
    if cmd=="spanning-tree-kruskal":
        for u,v,w in ed:
            if ds.u(int(u),int(v)):tree.append([u,v,w]);cost+=float(w)
        emit({"cost":cost,"edges":tree});return
    if cmd=="convex-hull-graham":need(a,1);emit(hull(points(a[0])));return
    if cmd=="voronoi-diagram-cli":need(a,2);emit(voronoi(points(a[0]),seq(a[1])));return
    if cmd=="delaunay-triangulate":need(a,1);emit(delaunay(points(a[0])));return
    if cmd=="geodesic-distance-vin":need(a,4);emit(vincenty(*map(float,a[:4])));return
    if cmd=="haversine-distance-cli":need(a,4);la1,lo1,la2,lo2=map(math.radians,map(float,a[:4]));h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2;emit(6371008.8*2*math.asin(math.sqrt(h)));return
    if cmd=="utm-lat-long-converter":need(a,2);z,h,E,N=utm(float(a[0]),float(a[1]));emit({"zone":z,"hemisphere":h,"easting":E,"northing":N});return
    if cmd=="coordinate-proj-proj4":
        need(a,4);src=a[0].lower();dst=a[1].lower();x=float(a[2]);y=float(a[3]);R=6378137.0
        if "4326" in src and "3857" in dst:emit({"x":R*math.radians(x),"y":R*math.log(math.tan(math.pi/4+math.radians(y)/2))})
        elif "3857" in src and "4326" in dst:emit({"lon":math.degrees(x/R),"lat":math.degrees(2*math.atan(math.exp(y/R))-math.pi/2)})
        else:raise SystemExit("supports EPSG:4326 <-> EPSG:3857")
        return
    if cmd=="astronomical-julian":need(a,1);t=dt.datetime.fromisoformat(a[0].replace("Z","+00:00"));j=julian(t);emit({"jd":j,"mjd":j-2400000.5});return
    if cmd=="sidereal-time-calc":need(a,1);t=dt.datetime.fromisoformat(a[0].replace("Z","+00:00"));J=julian(t);T=(J-2451545.0)/36525;gmst=(280.46061837+360.98564736629*(J-2451545)+0.000387933*T*T-T*T*T/38710000)%360;emit({"gmst_degrees":gmst,"gmst_hours":gmst/15});return
    if cmd=="solar-zenith-angle":
        need(a,3);lat=float(a[0]);lon=float(a[1]);t=dt.datetime.fromisoformat(a[2].replace("Z","+00:00"));n=t.timetuple().tm_yday;hour=t.hour+t.minute/60+t.second/3600;g=2*math.pi/365*(n-1+(hour-12)/24);eq=229.18*(0.000075+0.001868*math.cos(g)-0.032077*math.sin(g)-0.014615*math.cos(2*g)-0.040849*math.sin(2*g));dec=(0.006918-0.399912*math.cos(g)+0.070257*math.sin(g)-0.006758*math.cos(2*g)+0.000907*math.sin(2*g)-0.002697*math.cos(3*g)+0.00148*math.sin(3*g));mins=t.hour*60+t.minute+t.second/60+eq+4*lon;ha=math.radians(mins/4-180);lr=math.radians(lat);cz=math.sin(lr)*math.sin(dec)+math.cos(lr)*math.cos(dec)*math.cos(ha);emit({"zenith_deg":math.degrees(math.acos(max(-1,min(1,cz))))});return
    unitsT={"c":lambda x:x,"f":lambda x:(x-32)*5/9,"k":lambda x:x-273.15,"r":lambda x:(x-491.67)*5/9,"d":lambda x:100-x*2/3}
    if cmd=="temperature-scale-conv":need(a,3);c=unitsT[a[1].lower()](float(a[0]));to=a[2].lower();emit({"c":c,"f":c*9/5+32,"k":c+273.15,"r":(c+273.15)*9/5,"d":(100-c)*3/2}[to]);return
    if cmd=="pressure-unit-calc":need(a,3);f={"pa":1,"bar":1e5,"atm":101325,"torr":101325/760,"psi":6894.757293168};emit(float(a[0])*f[a[1].lower()]/f[a[2].lower()]);return
    if cmd=="energy-joule-kwh-conv":need(a,3);f={"j":1,"wh":3600,"kwh":3.6e6,"cal":4.184,"btu":1055.05585262};emit(float(a[0])*f[a[1].lower()]/f[a[2].lower()]);return
    if cmd=="speed-of-sound-calc":need(a,1);emit(331.3*math.sqrt(1+float(a[0])/273.15));return
    if cmd=="doppler-shift-calc":need(a,4);f,vs,vo,c=map(float,a[:4]);emit(f*(c+vo)/(c-vs));return
    if cmd=="signal-to-noise-ratio":need(a,2);s=float(a[0]);n=float(a[1]);emit({"ratio":s/n,"db":10*math.log10(s/n)});return
    if cmd in ("boolean-logic-solver","truth-table-generator"):
        need(a,1);expr=a[0];vars=sorted({n.id for n in ast.walk(ast.parse(expr,mode="eval")) if isinstance(n,ast.Name)});rows=[]
        for mask in range(1<<len(vars)):
            vals={v:bool(mask&(1<<i)) for i,v in enumerate(vars)};rows.append({**vals,"result":bool_eval(expr,vals)})
        emit({"satisfiable":any(r["result"] for r in rows),"rows":rows} if cmd.startswith("boolean") else rows);return
    raise SystemExit("implementation missing")
if __name__=="__main__":
    if len(sys.argv)<2:raise SystemExit("usage: runtime COMMAND [args...]")
    try:main(sys.argv[1],sys.argv[2:])
    except (ValueError,KeyError,ZeroDivisionError,OverflowError) as e:raise SystemExit(str(e))
