"""
Phase 1 of the layout proposal: emit spatially-anchored, faction-grouped layout
data for a constraint solver (cola.js). Each NPC is seeded at its real spawn
coordinate (spawn2.x/y); factions become containment groups; sparse shared-rare-
item links give the stress solver structure. The browser runs WebCola on this.
"""
import pymysql, collections, itertools, json
conn = pymysql.connect(host="127.0.0.1", port=3399, user="root", db="alkabor",
                       unix_socket="/home/kevin/eq/db/mysql.sock")
cur = conn.cursor()
def q(s, a=None): cur.execute(s, a); return cur.fetchall()

QZONES = ["qeynos", "qeynos2", "qcat", "qeytoqrg", "qrg", "freportw", "rivervale"]
ITEM_CAP = 40          # non-commodity
MAX_HOLDERS = 8        # rare/specific shared items become links (avoid huge cliques)

def clean(s): return (s or "").replace("_", " ").strip("# ").strip() or "?"
zmeta = {sn: clean(ln) for sn, ln in q("SELECT short_name,long_name FROM zone")}
npc_info = {i: (clean(nm), bool(iq), nfid, lt, mid) for i, nm, iq, nfid, lt, mid in
            q("SELECT id,name,isquest,npc_faction_id,loottable_id,merchant_id FROM npc_types")}
nf_primary = {i: pf for i, pf in q("SELECT id,primaryfaction FROM npc_faction")}
fac_name = {f: clean(nm) for f, nm in q("SELECT id,name FROM faction_list")}
loot_items = collections.defaultdict(set)
for lt, iid in q("""SELECT lte.loottable_id, lde.item_id FROM loottable_entries lte
                    JOIN lootdrop_entries lde ON lde.lootdrop_id=lte.lootdrop_id"""):
    loot_items[lt].add(iid)
merch_items = collections.defaultdict(set)
for mid, iid in q("SELECT merchantid,item FROM merchantlist"): merch_items[mid].add(iid)
item_freq = collections.Counter()
for i, c in q("""SELECT item_id,COUNT(DISTINCT nt.id) FROM npc_types nt
                 JOIN loottable_entries lte ON lte.loottable_id=nt.loottable_id
                 JOIN lootdrop_entries lde ON lde.lootdrop_id=lte.lootdrop_id GROUP BY item_id"""):
    item_freq[i] += c
for i, c in q("SELECT item,COUNT(DISTINCT merchantid) FROM merchantlist GROUP BY item"):
    item_freq[i] += c

def npc_items(nid):
    _, _, _, lt, mid = npc_info[nid]
    its = set()
    if lt: its |= loot_items.get(lt, set())
    if mid: its |= merch_items.get(mid, set())
    return {i for i in its if item_freq.get(i, 0) <= ITEM_CAP}

import os
DLG = "/home/kevin/eq/analysis/dialog_edges.json"      # NPC->NPC dialogue mentions
npc_mentions = collections.defaultdict(set)
if os.path.exists(DLG):
    for e in json.load(open(DLG))["edges"]:
        t = e["target"]
        if t.startswith("npc:"): npc_mentions[e["speaker_id"]].add(int(t[4:]))

def build(zone):
    # NPC -> averaged spawn coordinate in this zone
    rows = q("""SELECT se.npcID, s2.x, s2.y FROM spawn2 s2
                JOIN spawnentry se ON se.spawngroupID=s2.spawngroupID WHERE s2.zone=%s""", (zone,))
    acc = collections.defaultdict(lambda: [0.0, 0.0, 0])
    for nid, x, y in rows:
        if nid in npc_info:
            acc[nid][0] += float(x); acc[nid][1] += float(y); acc[nid][2] += 1
    coord = {n: (a[0]/a[2], a[1]/a[2]) for n, a in acc.items() if a[2]}
    npcs = sorted(coord)
    if len(npcs) < 3: return None
    idx = {n: i for i, n in enumerate(npcs)}
    # normalize spawn coords -> canvas box (EQ y is inverted vs screen).
    # clip to 2..98 percentile so a few far-flung spawns don't squash the core.
    import numpy as np
    xs = np.array([coord[n][0] for n in npcs]); ys = np.array([coord[n][1] for n in npcs])
    x0, x1 = np.percentile(xs, 2), np.percentile(xs, 98)
    y0, y1 = np.percentile(ys, 2), np.percentile(ys, 98)
    W, H, pad = 1000, 720, 40
    sx = (W-2*pad)/((x1-x0) or 1); sy = (H-2*pad)/((y1-y0) or 1); s = min(sx, sy)
    def nx(x): return max(pad, min(W-pad, pad + (x-x0)*s))       # clamp outliers to edge
    def ny(y): return max(pad, min(H-pad, H - pad - (y-y0)*s))   # flip + clamp
    prim = {n: (nf_primary.get(npc_info[n][2], 0) or 0) for n in npcs}
    nodes = []
    for n in npcs:
        nm, iq, *_ = npc_info[n]
        nodes.append({"id": int(n), "label": nm, "quest": iq, "fac": prim[n],
                      "x": round(nx(coord[n][0]), 1), "y": round(ny(coord[n][1]), 1)})
    # groups by primary faction
    fgroups = collections.defaultdict(list)
    for n in npcs:
        if prim[n]: fgroups[prim[n]].append(idx[n])
    groups = [{"fac": f, "label": fac_name.get(f, "?"), "leaves": sorted(v)}
              for f, v in sorted(fgroups.items(), key=lambda kv: -len(kv[1])) if len(v) >= 1]
    # links (typed): shared rare item (green) + dialogue mention (lavender)
    pair_type = {}
    holders = collections.defaultdict(list)
    for n in npcs:
        for it in npc_items(n): holders[it].append(n)
    for it, hs in holders.items():
        if 2 <= len(hs) <= MAX_HOLDERS:
            for a, b in itertools.combinations(sorted(hs), 2):
                pair_type[(idx[a], idx[b])] = "item"
    nset = set(npcs)
    for sp in npcs:                                    # intra-zone dialogue mentions
        for tg in npc_mentions.get(sp, ()):
            if tg in nset and tg != sp:
                pair_type[tuple(sorted((idx[sp], idx[tg])))] = "mention"   # mention overrides item
    links = [{"source": a, "target": b, "type": t} for (a, b), t in pair_type.items()]
    ni = sum(1 for l in links if l["type"] == "item"); nm = len(links) - ni
    return {"zone": zone, "long": zmeta.get(zone, zone), "W": W, "H": H,
            "nodes": nodes, "groups": groups, "links": links,
            "stats": {"npcs": len(npcs), "factions": len(groups), "links": len(links),
                      "item_links": ni, "mention_links": nm,
                      "quest": sum(1 for n in nodes if n["quest"])}}

manifest = []
for z in QZONES:
    fig = build(z)
    if not fig: continue
    json.dump(fig, open(f"/home/kevin/eq/analysis/anchored_{z}.json", "w"))
    manifest.append({"zone": z, "long": fig["long"], "stats": fig["stats"]})
    s = fig["stats"]
    print(f"{z:10} npcs={s['npcs']:3} factions={s['factions']:2} links={s['links']:4} quest={s['quest']}")
json.dump(manifest, open("/home/kevin/eq/analysis/anchored_manifest.json", "w"))
