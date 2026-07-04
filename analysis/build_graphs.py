"""
Reconstruct a per-zone 'content/quest connectivity' graph from the Alkabor (EQMac) DB.

Nodes  = distinct NPCs that spawn in the zone.
Edges  = ontological ties a quest designer relies on:
  - FACTION tie: two NPCs share a faction in their faction hit-list
                 (npc_faction_entries), weight += 1/faction_size  (rarity-weighted)
  - ITEM tie:    two NPCs share a non-commodity item (loot or merchant,
                 global freq <= ITEM_CAP), weight += 1/item_freq
Edge weight = sum of the above; an edge exists iff weight > 0.

Rarity weighting makes "dense connectivity" mean *tightly & meaningfully* linked,
not "everyone drops a diamond / is on universal faction".
"""
import pymysql, collections, itertools, json, math
import networkx as nx

ITEM_CAP = 40           # ignore items held by more than this many NPCs (commodities)
conn = pymysql.connect(host="127.0.0.1", port=3399, user="root", db="alkabor",
                       unix_socket="/home/kevin/eq/db/mysql.sock")
cur = conn.cursor()
def q(sql):
    cur.execute(sql); return cur.fetchall()

# ---- zone metadata ----
zmeta = {sn: {"long": ln, "zid": zid} for sn, zid, ln in
         q("SELECT short_name, zoneidnumber, long_name FROM zone")}

# ---- NPC -> zone ----
zone_npcs = collections.defaultdict(set)
for z, n in q("""SELECT DISTINCT s2.zone, se.npcID
                 FROM spawn2 s2 JOIN spawnentry se ON se.spawngroupID=s2.spawngroupID"""):
    zone_npcs[z].add(n)

# ---- NPC name + isquest ----
npc_info = {i: (name, bool(iq)) for i, name, iq in
            q("SELECT id, name, isquest FROM npc_types")}

# ---- factions: npc -> set(faction_id), and faction sizes ----
npc_fac = collections.defaultdict(set)
fac_npcs = collections.defaultdict(set)
for n, f in q("""SELECT nt.id, fe.faction_id FROM npc_types nt
                 JOIN npc_faction_entries fe ON fe.npc_faction_id=nt.npc_faction_id
                 WHERE nt.npc_faction_id>0"""):
    npc_fac[n].add(f); fac_npcs[f].add(n)
fac_size = {f: len(s) for f, s in fac_npcs.items()}
fac_name = {f: nm for f, nm in q("SELECT id, name FROM faction_list")}

# ---- items: npc -> set(item_id) (loot UNION merchant), + global freq ----
npc_item = collections.defaultdict(set)
item_npcs = collections.defaultdict(set)
for n, i in q("""SELECT DISTINCT nt.id, lde.item_id FROM npc_types nt
                 JOIN loottable_entries lte ON lte.loottable_id=nt.loottable_id
                 JOIN lootdrop_entries lde ON lde.lootdrop_id=lte.lootdrop_id
                 WHERE nt.loottable_id>0"""):
    npc_item[n].add(i); item_npcs[i].add(n)
for n, i in q("""SELECT DISTINCT nt.id, ml.item FROM npc_types nt
                 JOIN merchantlist ml ON ml.merchantid=nt.merchant_id
                 WHERE nt.merchant_id>0"""):
    npc_item[n].add(i); item_npcs[i].add(n)
item_freq = {i: len(s) for i, s in item_npcs.items()}
item_name = {i: nm for i, nm in q("SELECT id, Name FROM items")}

def build_zone_graph(npcs):
    """Build weighted graph over the given NPC id set."""
    npcs = [n for n in npcs if n in npc_info]
    G = nx.Graph()
    G.add_nodes_from(npcs)
    nset = set(npcs)
    # faction cliques (rarity weighted)
    fac_members = collections.defaultdict(list)
    for n in npcs:
        for f in npc_fac.get(n, ()):
            fac_members[f].append(n)
    fac_edge_w = collections.defaultdict(float)
    for f, mem in fac_members.items():
        if len(mem) < 2:
            continue
        w = 1.0 / fac_size[f]
        for a, b in itertools.combinations(sorted(mem), 2):
            fac_edge_w[(a, b)] += w
    # item cliques (rarity weighted, commodities excluded)
    item_members = collections.defaultdict(list)
    for n in npcs:
        for it in npc_item.get(n, ()):
            if item_freq.get(it, 0) <= ITEM_CAP:
                item_members[it].append(n)
    item_edge_w = collections.defaultdict(float)
    for it, mem in item_members.items():
        if len(mem) < 2:
            continue
        w = 1.0 / item_freq[it]
        for a, b in itertools.combinations(sorted(mem), 2):
            item_edge_w[(a, b)] += w
    # merge
    allpairs = set(fac_edge_w) | set(item_edge_w)
    for (a, b) in allpairs:
        fw = fac_edge_w.get((a, b), 0.0)
        iw = item_edge_w.get((a, b), 0.0)
        G.add_edge(a, b, weight=fw + iw, fac=fw, item=iw)
    return G

def graph_density(G):
    N = G.number_of_nodes(); E = G.number_of_edges()
    return (2 * E / (N * (N - 1))) if N > 1 else 0.0

def metrics(G, npcs):
    N = G.number_of_nodes(); E = G.number_of_edges()
    if N < 2:
        return None
    dens = 2 * E / (N * (N - 1))
    degs = [d for _, d in G.degree()]
    wdeg = [d for _, d in G.degree(weight="weight")]
    avg_deg = sum(degs) / N
    avg_wdeg = sum(wdeg) / N
    clus = nx.average_clustering(G)
    comps = list(nx.connected_components(G))
    lcc = max((len(c) for c in comps), default=0)
    qn = sum(1 for n in G.nodes if npc_info.get(n, ("", False))[1])
    tot_w = sum(d["weight"] for *_, d in G.edges(data=True))
    fac_w = sum(d["fac"] for *_, d in G.edges(data=True))
    item_w = sum(d["item"] for *_, d in G.edges(data=True))

    # faction diversity: distinct factions represented among zone NPCs
    facs = set()
    for n in npcs:
        facs |= npc_fac.get(n, set())
    n_fac = len(facs)

    # quest-giver subgraph (isquest NPCs only) -- the real "quest web"
    qnodes = [n for n in G.nodes if npc_info.get(n, ("", False))[1]]
    QG = G.subgraph(qnodes)
    q_dens = graph_density(QG)
    q_edges = QG.number_of_edges()
    q_avgdeg = (2 * q_edges / len(qnodes)) if len(qnodes) > 1 else 0.0
    q_lcc = max((len(c) for c in nx.connected_components(QG)), default=0)

    # community structure (on largest component of full graph)
    try:
        comm = list(nx.community.greedy_modularity_communities(G, weight="weight"))
        modularity = nx.community.modularity(G, comm, weight="weight")
        n_comm = len(comm)
    except Exception:
        modularity, n_comm = 0.0, len(comps)

    return dict(N=N, E=E, density=dens, avg_deg=avg_deg, avg_wdeg=avg_wdeg,
                clustering=clus, lcc=lcc, lcc_frac=lcc / N, quest_npcs=qn,
                tot_weight=tot_w, fac_weight=fac_w, item_weight=item_w,
                ncomp=len(comps), n_factions=n_fac,
                q_density=q_dens, q_edges=q_edges, q_avgdeg=q_avgdeg,
                q_lcc=q_lcc, modularity=modularity, n_comm=n_comm)

# ---- per zone ----
results = []
graphs = {}
for z, npcs in zone_npcs.items():
    if len(npcs) < 2:
        continue
    G = build_zone_graph(npcs)
    m = metrics(G, npcs)
    if not m:
        continue
    m["zone"] = z
    m["long"] = zmeta.get(z, {}).get("long", z)
    m["zid"] = zmeta.get(z, {}).get("zid")
    # QUEST-WEB score: a rich quest hub = many quest-givers, densely interlinked,
    # spanning many distinct factions (diverse ontology, not one monolithic clique).
    #   quest_npcs        -> raw quest presence
    #   (1+q_avgdeg)      -> how interconnected the quest-givers are
    #   sqrt(n_factions)  -> ontological/faction diversity
    m["quest_score"] = m["quest_npcs"] * (1 + m["q_avgdeg"]) * math.sqrt(max(m["n_factions"], 1))
    # naive raw-density score (kept for contrast — the "artifact" metric)
    m["raw_score"] = m["avg_wdeg"] * math.sqrt(m["N"]) * (0.5 + m["clustering"])
    results.append(m)
    graphs[z] = G

with open("/home/kevin/eq/analysis/zone_metrics.json", "w") as f:
    json.dump(results, f, indent=2)

QEY = {"qeynos", "qeynos2", "qcat", "qeytoqrg", "qrg"}
def show(rankkey, title, cols):
    rs = sorted(results, key=lambda r: r[rankkey], reverse=True)
    print(f"\n===== {title} =====")
    hdr = f"{'#':>3} {'zone':<11}" + "".join(f"{c[0]:>{c[2]}}" for c in cols) + "  long"
    print(hdr)
    for i, r in enumerate(rs[:20], 1):
        star = "*" if r["zone"] in QEY else " "
        line = f"{i:>3}{star}{r['zone']:<10}" + "".join(
            f"{r[c[1]]:>{c[2]}.{c[3]}f}" if c[3] else f"{r[c[1]]:>{c[2]}}" for c in cols)
        print(line + f"  {r['long'][:24]}")
    # qeynos positions
    pos = {r['zone']: i for i, r in enumerate(rs, 1)}
    print("  Qeynos-area:", ", ".join(f"{z}=#{pos[z]}" for z in
          ["qeynos","qeynos2","qcat","qeytoqrg","qrg"] if z in pos))

# cols: (header, key, width, decimals)
show("quest_score", "QUEST-WEB RICHNESS (quest-givers x interconnection x faction diversity)",
     [("qNPC","quest_npcs",6,None),("qDeg","q_avgdeg",6,2),("qDens","q_density",7,3),
      ("nFac","n_factions",6,None),("score","quest_score",9,1)])
show("quest_npcs", "RAW QUEST-GIVER COUNT",
     [("qNPC","quest_npcs",6,None),("N","N",5,None),("nFac","n_factions",6,None)])
show("n_factions", "FACTION DIVERSITY (distinct factions represented)",
     [("nFac","n_factions",6,None),("N","N",5,None),("qNPC","quest_npcs",6,None)])
show("raw_score", "RAW DENSITY (naive - favors monolithic dungeons)",
     [("N","N",5,None),("dens","density",7,3),("wdeg","avg_wdeg",6,2),("clus","clustering",6,2)])

print(f"\ntotal zones ranked: {len(results)}")

# ============================================================
# CITY CLUSTERS — the fair unit for "the city of Qeynos"
# ============================================================
CLUSTERS = {
    "Qeynos (city)":      ["qeynos", "qeynos2", "qcat"],
    "Qeynos (greater)":   ["qeynos", "qeynos2", "qcat", "qeytoqrg", "qrg"],
    "Freeport":           ["freportn", "freportw", "freporte"],
    "Neriak":             ["neriaka", "neriakb", "neriakc"],
    "Kaladim":            ["kaladima", "kaladimb"],
    "Felwithe":           ["felwithea", "felwitheb"],
    "Erudin":             ["erudnext", "erudnint"],
    "Cabilis":            ["cabeast", "cabwest"],
    "Thurgadin":          ["thurgadina", "thurgadinb"],
    "Halas":              ["halas"],
    "Grobb":              ["grobb"],
    "Oggok":              ["oggok"],
    "Rivervale":          ["rivervale"],
    "Ak'Anon":            ["akanon"],
    "Kelethin/GFay":      ["gfaydark"],
    "Shar Vahl":          ["sharvahl"],
    "Shadow Haven":       ["shadowhaven"],
    "Paineel":            ["paineel"],
    "Katta Castellum":    ["katta"],
}
cluster_rows = []
for cname, zs in CLUSTERS.items():
    npcs = set()
    for z in zs:
        npcs |= zone_npcs.get(z, set())
    if len(npcs) < 2:
        continue
    G = build_zone_graph(npcs)
    m = metrics(G, npcs)
    m["cluster"] = cname
    m["zones"] = zs
    m["quest_score"] = m["quest_npcs"] * (1 + m["q_avgdeg"]) * math.sqrt(max(m["n_factions"], 1))
    cluster_rows.append(m)

cluster_rows.sort(key=lambda r: r["quest_score"], reverse=True)
with open("/home/kevin/eq/analysis/cluster_metrics.json", "w") as f:
    json.dump(cluster_rows, f, indent=2)

print("\n===== CITY CLUSTERS — quest-web richness =====")
print(f"{'#':>3} {'city':<18}{'qNPC':>5}{'qDeg':>6}{'qDens':>7}{'nFac':>5}{'N':>5}{'score':>10}")
for i, r in enumerate(cluster_rows, 1):
    star = "*" if "Qeynos" in r["cluster"] else " "
    print(f"{i:>3}{star}{r['cluster']:<17}{r['quest_npcs']:>5}{r['q_avgdeg']:>6.1f}"
          f"{r['q_density']:>7.3f}{r['n_factions']:>5}{r['N']:>5}{r['quest_score']:>10.0f}")

# ============================================================
# VIZ EXPORT — featured zone/cluster graphs with layout + communities
# ============================================================
def export_viz(name, G, path):
    if G.number_of_nodes() == 0:
        return
    # communities for coloring
    try:
        comm = list(nx.community.greedy_modularity_communities(G, weight="weight"))
    except Exception:
        comm = [set(G.nodes)]
    node2comm = {}
    for ci, cset in enumerate(comm):
        for n in cset:
            node2comm[n] = ci
    # ---- community-grouped layout: clusters placed by inter-community ties,
    #      nodes nested inside their community. Reveals modular structure of a
    #      dense graph far better than a single global force layout (a hairball).
    ncom = len(comm)
    # community meta-graph (edges weighted by cross-community tie strength)
    CG = nx.Graph()
    CG.add_nodes_from(range(ncom))
    cross = collections.defaultdict(float)
    for a, b, d in G.edges(data=True):
        ca, cb = node2comm[a], node2comm[b]
        if ca != cb:
            cross[(min(ca, cb), max(ca, cb))] += d["weight"]
    for (ca, cb), w in cross.items():
        CG.add_edge(ca, cb, weight=w)
    if ncom > 1:
        cpos = nx.spring_layout(CG, k=2.2/math.sqrt(ncom), iterations=200,
                                weight="weight", seed=3)
    else:
        cpos = {0: (0.0, 0.0)}
    # scale community centres out
    csizes = [len(c) for c in comm]
    maxc = max(csizes)
    pos = {}
    for ci, cset in enumerate(comm):
        cx, cy = cpos[ci]
        cx *= 2.6; cy *= 2.6
        sub = G.subgraph(cset)
        if len(cset) == 1:
            (only,) = tuple(cset); pos[only] = (cx, cy); continue
        sp = nx.spring_layout(sub, k=1.0/math.sqrt(len(cset)), iterations=60,
                              weight="weight", seed=1)
        # radius of a community scales with sqrt of its size
        rad = 0.14 + 0.42 * math.sqrt(len(cset) / maxc)
        xs = [p[0] for p in sp.values()]; ys = [p[1] for p in sp.values()]
        x0, x1 = min(xs), max(xs); y0, y1 = min(ys), max(ys)
        spanx = (x1 - x0) or 1; spany = (y1 - y0) or 1
        for n, (px, py) in sp.items():
            nx_ = (px - (x0 + x1) / 2) / spanx * 2 * rad
            ny_ = (py - (y0 + y1) / 2) / spany * 2 * rad
            pos[n] = (cx + nx_, cy + ny_)
    # primary faction name per node
    def prim_fac(n):
        fs = npc_fac.get(n, set())
        if not fs: return ""
        f = min(fs, key=lambda x: fac_size.get(x, 1e9))  # rarest faction as label
        return fac_name.get(f, str(f))
    nodes = []
    for n in G.nodes:
        nm, iq = npc_info.get(n, (str(n), False))
        nm = (nm or str(n)).replace("_", " ").strip("#")
        nodes.append(dict(id=int(n), name=nm, quest=bool(iq),
                          comm=node2comm.get(n, 0), deg=G.degree(n),
                          fac=prim_fac(n),
                          x=round(float(pos[n][0]), 4), y=round(float(pos[n][1]), 4)))
    edges = [dict(s=int(a), t=int(b), w=round(float(d["weight"]), 4),
                  typ=("fac" if d["item"] == 0 else ("item" if d["fac"] == 0 else "both")))
             for a, b, d in G.edges(data=True)]
    with open(path, "w") as f:
        json.dump(dict(name=name, n_comm=len(comm), nodes=nodes, edges=edges), f)
    print(f"  exported {name}: {len(nodes)} nodes, {len(edges)} edges, {len(comm)} communities -> {path}")

print("\n===== VIZ EXPORT =====")
FEATURED = {
    "qeynos": ("South Qeynos", graphs.get("qeynos")),
    "freportw": ("West Freeport", graphs.get("freportw")),
    "shadowhaven": ("Shadow Haven", graphs.get("shadowhaven")),
    "rivervale": ("Rivervale", graphs.get("rivervale")),
}
for z, (nm, G) in FEATURED.items():
    if G is not None:
        export_viz(nm, G, f"/home/kevin/eq/analysis/viz_{z}.json")
# Qeynos metro combined
metro_npcs = set()
for z in ["qeynos", "qeynos2", "qcat"]:
    metro_npcs |= zone_npcs.get(z, set())
export_viz("Qeynos (city, combined)", build_zone_graph(metro_npcs),
           "/home/kevin/eq/analysis/viz_qeynos_metro.json")

import pickle
with open("/home/kevin/eq/analysis/graphs.pkl","wb") as f:
    pickle.dump({"npc_info":npc_info,"npc_fac":npc_fac,"fac_size":fac_size,
                 "fac_name":fac_name,"zmeta":zmeta}, f)
