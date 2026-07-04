"""Re-export only the featured viz graphs (fast) using the improved community layout."""
import pymysql, collections, itertools, json, math
import networkx as nx

ITEM_CAP = 40
conn = pymysql.connect(host="127.0.0.1", port=3399, user="root", db="alkabor",
                       unix_socket="/home/kevin/eq/db/mysql.sock")
cur = conn.cursor()
def q(s): cur.execute(s); return cur.fetchall()

zone_npcs = collections.defaultdict(set)
for z, n in q("SELECT DISTINCT s2.zone, se.npcID FROM spawn2 s2 JOIN spawnentry se ON se.spawngroupID=s2.spawngroupID"):
    zone_npcs[z].add(n)
npc_info = {i:(name,bool(iq)) for i,name,iq in q("SELECT id,name,isquest FROM npc_types")}
npc_fac = collections.defaultdict(set); fac_npcs = collections.defaultdict(set)
for n,f in q("""SELECT nt.id,fe.faction_id FROM npc_types nt JOIN npc_faction_entries fe
                ON fe.npc_faction_id=nt.npc_faction_id WHERE nt.npc_faction_id>0"""):
    npc_fac[n].add(f); fac_npcs[f].add(n)
fac_size={f:len(s) for f,s in fac_npcs.items()}
fac_name={f:nm for f,nm in q("SELECT id,name FROM faction_list")}
npc_item=collections.defaultdict(set); item_npcs=collections.defaultdict(set)
for n,i in q("""SELECT DISTINCT nt.id,lde.item_id FROM npc_types nt
                JOIN loottable_entries lte ON lte.loottable_id=nt.loottable_id
                JOIN lootdrop_entries lde ON lde.lootdrop_id=lte.lootdrop_id WHERE nt.loottable_id>0"""):
    npc_item[n].add(i); item_npcs[i].add(n)
for n,i in q("SELECT DISTINCT nt.id,ml.item FROM npc_types nt JOIN merchantlist ml ON ml.merchantid=nt.merchant_id WHERE nt.merchant_id>0"):
    npc_item[n].add(i); item_npcs[i].add(n)
item_freq={i:len(s) for i,s in item_npcs.items()}

def build_zone_graph(npcs):
    npcs=[n for n in npcs if n in npc_info]; G=nx.Graph(); G.add_nodes_from(npcs)
    fm=collections.defaultdict(list)
    for n in npcs:
        for f in npc_fac.get(n,()): fm[f].append(n)
    ew=collections.defaultdict(float)
    for f,mem in fm.items():
        if len(mem)<2: continue
        w=1.0/fac_size[f]
        for a,b in itertools.combinations(sorted(mem),2): ew[(a,b)]+=w
    im=collections.defaultdict(list)
    for n in npcs:
        for it in npc_item.get(n,()):
            if item_freq.get(it,0)<=ITEM_CAP: im[it].append(n)
    iw=collections.defaultdict(float)
    for it,mem in im.items():
        if len(mem)<2: continue
        w=1.0/item_freq[it]
        for a,b in itertools.combinations(sorted(mem),2): iw[(a,b)]+=w
    for pr in set(ew)|set(iw):
        fw=ew.get(pr,0.0); iv=iw.get(pr,0.0)
        G.add_edge(pr[0],pr[1],weight=fw+iv,fac=fw,item=iv)
    return G

def export_viz(name, G, path):
    if G.number_of_nodes()==0: return
    try: comm=list(nx.community.greedy_modularity_communities(G,weight="weight"))
    except Exception: comm=[set(G.nodes)]
    node2comm={}
    for ci,cset in enumerate(comm):
        for n in cset: node2comm[n]=ci
    # phyllotaxis packing: communities sorted big->small, largest centred,
    # spiralled evenly outward so the frame fills and clusters stay countable.
    order=sorted(range(len(comm)), key=lambda i:-len(comm[i]))
    maxc=max(len(c) for c in comm)
    GOLD=2.399963229728653
    # per-community render radius (bigger comm = bigger disc)
    def crad(sz): return 0.10+0.55*math.sqrt(sz/maxc)
    # spiral step scaled so discs don't overlap much
    SPREAD=0.62
    pos={}
    for rank,ci in enumerate(order):
        cset=comm[ci]
        r=SPREAD*math.sqrt(rank); th=rank*GOLD
        cx,cy=r*math.cos(th), r*math.sin(th)
        if len(cset)==1:
            (only,)=tuple(cset); pos[only]=(cx,cy); continue
        sub=G.subgraph(cset)
        sp=nx.spring_layout(sub,k=1.0/math.sqrt(len(cset)),iterations=80,weight="weight",seed=1)
        rad=crad(len(cset))
        xs=[p[0] for p in sp.values()]; ys=[p[1] for p in sp.values()]
        x0,x1=min(xs),max(xs); y0,y1=min(ys),max(ys)
        spanx=(x1-x0) or 1; spany=(y1-y0) or 1
        for n,(px,py) in sp.items():
            pos[n]=(cx+(px-(x0+x1)/2)/spanx*2*rad, cy+(py-(y0+y1)/2)/spany*2*rad)
    def prim_fac(n):
        fs=npc_fac.get(n,set())
        if not fs: return ""
        f=min(fs,key=lambda x:fac_size.get(x,1e9)); return fac_name.get(f,str(f))
    nodes=[]
    for n in G.nodes:
        nm,iq=npc_info.get(n,(str(n),False)); nm=(nm or str(n)).replace("_"," ").strip("#")
        nodes.append(dict(id=int(n),name=nm,quest=bool(iq),comm=node2comm.get(n,0),
                          deg=G.degree(n),fac=prim_fac(n),
                          x=round(float(pos[n][0]),4),y=round(float(pos[n][1]),4)))
    edges=[dict(s=int(a),t=int(b),w=round(float(d["weight"]),4),
                typ=("fac" if d["item"]==0 else ("item" if d["fac"]==0 else "both")))
           for a,b,d in G.edges(data=True)]
    json.dump(dict(name=name,n_comm=len(comm),nodes=nodes,edges=edges),open(path,"w"))
    print(f"  {name}: {len(nodes)} nodes, {len(edges)} edges, {len(comm)} comms -> {path}")

FEAT={"qeynos":"South Qeynos","freportw":"West Freeport","shadowhaven":"Shadow Haven","rivervale":"Rivervale"}
for z,nm in FEAT.items():
    export_viz(nm, build_zone_graph(zone_npcs[z]), f"/home/kevin/eq/analysis/viz_{z}.json")
metro=set()
for z in ["qeynos","qeynos2","qcat"]: metro|=zone_npcs.get(z,set())
export_viz("Qeynos (city, combined)", build_zone_graph(metro), "/home/kevin/eq/analysis/viz_qeynos_metro.json")
