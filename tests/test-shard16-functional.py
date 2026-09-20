#!/usr/bin/env python3
import importlib.util,json,pathlib,subprocess,sys,tempfile
rt=pathlib.Path(sys.argv[1])
s=importlib.util.spec_from_file_location("r",rt);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
assert len(m.COMMANDS)==50 and len(set(m.COMMANDS))==50
def run(cmd,*args):
    r=subprocess.run([sys.executable,str(rt),cmd,*map(str,args)],text=True,capture_output=True)
    if r.returncode!=0: raise AssertionError((cmd,r.returncode,r.stdout,r.stderr))
    if not r.stdout.strip(): raise AssertionError((cmd,"empty output"))
    return r.stdout
cases={
"bigint-modular-power":("2","10","17"),
"bigint-extended-gcd":("240","46"),
"bigfloat-sqrt-calc":("2","40"),
"bigfloat-pi-chudnovsky":("40",),
"matrix-determinant-2d":('[[1,2],[3,4]]',),
"matrix-inverse-3d":('[[4,7],[2,6]]',),
"matrix-eigen-evaluator":('[[2,0],[0,1]]',),
"vector-dot-cross-prod":("[1,2,3]","[4,5,6]"),
"linear-regression-ols":("[1,2,3]","[2,4,6]"),
"polynomial-root-finder":("[1,0,-1]",),
"runge-kutta-integrator":("x+y","0","1","0.1","4"),
"simpson-integral-calc":("sin(x)","0","3.141592653589793","100"),
"fft-fourier-transform":("[1,2,3,4]",),
"dft-discrete-fourier":("[1,2,3]",),
"complex-number-calc":("+","1+2j","3+4j"),
"quaternion-rotation":("[1,0,0,0]","[1,2,3]"),
"normal-distribution-cdf":("1.96",),
"poisson-prob-calc":("2.5","3"),
"binomial-distribution":("10","3","0.5"),
"chi-square-statistic":("[10,20,30]","[12,18,30]"),
"student-t-distribution":("2.0","10"),
"standard-deviation-calc":("[1,2,3,4]",),
"covariance-matrix-cli":('[[1,2],[2,4],[3,6]]',),
"spearman-rank-calc":("[1,2,3]","[3,2,1]"),
"pearson-correlation":("[1,2,3]","[2,4,6]"),
"k-means-clustering-cli":('[[0,0],[0,1],[10,10],[10,11]]',"2"),
"dijkstra-shortest-path":('{"A":{"B":1,"C":4},"B":{"C":2},"C":{}}',"A","C"),
"a-star-path-finder":('[[0,0,0],[1,1,0],[0,0,0]]','[0,0]','[2,2]'),
"bellman-ford-detector":("3",'[[0,1,1],[1,2,2],[0,2,5]]',"0"),
"topological-sorter":('{"A":["B"],"B":["C"],"C":[]}',),
"bipartite-graph-match":('{"u1":["v1","v2"],"u2":["v2"]}',),
"spanning-tree-kruskal":("4",'[[0,1,1],[1,2,2],[2,3,1],[0,3,5]]'),
"convex-hull-graham":('[[0,0],[1,0],[1,1],[0,1],[0.5,0.5]]',),
"voronoi-diagram-cli":('[[0,0],[1,0]]','[-2,-2,2,2]'),
"delaunay-triangulate":('[[0,0],[1,0],[0,1],[1,1]]',),
"geodesic-distance-vin":("0","0","1","1"),
"haversine-distance-cli":("0","0","1","1"),
"utm-lat-long-converter":("28.6139","77.2090"),
"coordinate-proj-proj4":("EPSG:4326","EPSG:3857","77.209","28.6139"),
"astronomical-julian":("2026-09-20T00:00:00+00:00",),
"sidereal-time-calc":("2026-09-20T00:00:00+00:00",),
"solar-zenith-angle":("28.6","77.2","2026-09-20T06:30:00+00:00"),
"temperature-scale-conv":("100","c","f"),
"pressure-unit-calc":("1","atm","pa"),
"energy-joule-kwh-conv":("1","kwh","j"),
"speed-of-sound-calc":("20",),
"doppler-shift-calc":("440","10","0","343"),
"signal-to-noise-ratio":("100","1"),
"boolean-logic-solver":("a and (not b)",),
"truth-table-generator":("a or b",)
}
assert set(cases)==set(m.COMMANDS), (set(m.COMMANDS)-set(cases),set(cases)-set(m.COMMANDS))
for cmd,args in cases.items(): run(cmd,*args)
assert "1024" in run("bigint-modular-power","2","10","2000")
print("SUCCESS: exercised 50/50 shard-16 scientific/math commands")
