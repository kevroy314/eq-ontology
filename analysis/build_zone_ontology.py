"""
Zone-scoped ontology FIGURE generator.

Produces a deliberate LAYERED layout for one zone:
    [ neighbouring zones ] -> [ factions ] -> [ NPCs ] -> [ items ]
NPCs are grouped into faction swim-lanes; items sit at the barycentre of the
NPCs that provide them; neighbouring zones + world-spanning factions/items are
flagged as EXTERNAL. Node (x,y) positions are computed here so the browser just
draws a clean, intentional figure (no force-directed hairball).
"""
import pymysql, collections, json, sys
conn = pymysql.connect(host="127.0.0.1", port=3399, user="root", db="alkabor",
                       unix_socket="/home/kevin/eq/db/mysql.sock")
cur = conn.cursor()
def q(s, a=None): cur.execute(s, a); return cur.fetchall()

ITEM_CAP = 40          # global-frequency ceiling => non-commodity
ITEMS_PER_NPC = 3      # keep the N rarest items per NPC
ZONES = ["qeynos", "qeynos2", "qcat", "qeytoqrg", "qrg", "freportw", "rivervale"]

def clean(s): return (s or "").replace("_", " ").strip("# ").strip() or "?"

# ---- global reference maps (built once) ----
zmeta = {sn:(clean(ln), zid) for sn,ln,zid in q("SELECT short_name,long_name,zoneidnumber FROM zone")}
zid2short = {zid:sn for sn,(ln,zid) in zmeta.items()}
fac_name = {f:clean(nm) for f,nm in q("SELECT id,name FROM faction_list")}
item_name = {i:clean(nm) for i,nm in q("SELECT id,Name FROM items")}
npc_row = {i:(clean(nm), bool(iq), nfid, lt, mid) for i,nm,iq,nfid,lt,mid in
           q("SELECT id,name,isquest,npc_faction_id,loottable_id,merchant_id FROM npc_types")}

# npc -> zones (all)
npc_zones = collections.defaultdict(set)
for z,n in q("SELECT DISTINCT s2.zone, se.npcID FROM spawn2 s2 JOIN spawnentry se ON se.spawngroupID=s2.spawngroupID"):
    npc_zones[n].add(z)
# zone -> npcs
zone_npcs = collections.defaultdict(set)
for n,zs in npc_zones.items():
    for z in zs: zone_npcs[z].add(n)

# faction entries: npc_faction_id -> [(fac,val)]
nf = collections.defaultdict(list)
for nfid,fid,val in q("SELECT npc_faction_id,faction_id,value FROM npc_faction_entries"):
    nf[nfid].append((fid,val))
# canonical primary faction per npc_faction packet (npc_faction.primaryfaction)
nf_primary = {i:pf for i,pf in q("SELECT id,primaryfaction FROM npc_faction")}
def primary_faction(nfid):
    pf = nf_primary.get(nfid, 0)
    return pf if pf and pf > 0 else None

# loot / merchant -> items
loot_items = collections.defaultdict(set)
for lt,iid in q("""SELECT lte.loottable_id, lde.item_id FROM loottable_entries lte
                   JOIN lootdrop_entries lde ON lde.lootdrop_id=lte.lootdrop_id"""):
    loot_items[lt].add(iid)
merch_items = collections.defaultdict(set)
for mid,iid in q("SELECT merchantid,item FROM merchantlist"): merch_items[mid].add(iid)
# item global freq + zones
item_freq = collections.Counter(); item_zones = collections.defaultdict(set)
for n,(nm,iq,nfid,lt,mid) in npc_row.items():
    its = set()
    if lt: its |= loot_items.get(lt,set())
    if mid: its |= merch_items.get(mid,set())
    for iid in its:
        item_freq[iid]+=1
        item_zones[iid] |= npc_zones.get(n,set())
# faction zones (which zones a faction's members appear in)
fac_zones = collections.defaultdict(set)
for n,(nm,iq,nfid,lt,mid) in npc_row.items():
    if nfid:
        for f,v in nf.get(nfid,()):
            if v>0: fac_zones[f] |= npc_zones.get(n,set())

# derived faction ally/enemy (global) restricted later to present factions
import itertools
co_same=collections.Counter(); co_opp=collections.Counter()
for nfid,ents in nf.items():
    sig=[(f,1 if v>0 else -1) for f,v in ents if v!=0]
    for (f1,s1),(f2,s2) in itertools.combinations(sig,2):
        k=(min(f1,f2),max(f1,f2))
        (co_same if s1==s2 else co_opp)[k]+=1

def npc_items(n):
    nm,iq,nfid,lt,mid = npc_row[n]
    its=set()
    if lt: its |= loot_items.get(lt,set())
    if mid: its |= merch_items.get(mid,set())
    its=[i for i in its if item_freq.get(i,0)<=ITEM_CAP]
    its.sort(key=lambda i:item_freq.get(i,999))     # rarest first
    return its[:ITEMS_PER_NPC]

# ---------- layout for one zone ----------
XZONE, XFAC, XNPC, XITEM = 100, 450, 860, 1250
ROWH, GAP, TOP, ITEMH = 15, 18, 90, 15

def build(zone):
    npcs = [n for n in zone_npcs.get(zone, set()) if n in npc_row]
    lane_of = {n: primary_faction(npc_row[n][2]) for n in npcs}
    grp = collections.defaultdict(list)
    for n in npcs: grp[lane_of[n]].append(n)
    facs = [f for f in grp if f is not None]
    facs.sort(key=lambda f: -len(grp[f]))            # big lanes first
    order = facs + ([None] if None in grp else [])

    # providers per item, then assign each item to the lane of its majority provider
    prov = collections.defaultdict(list)
    for n in npcs:
        for it in npc_items(n): prov[it].append(n)
    item_lane = {}
    for it, ps in prov.items():
        item_lane[it] = collections.Counter(lane_of[p] for p in ps).most_common(1)[0][0]
    lane_items = collections.defaultdict(list)
    for it, l in item_lane.items(): lane_items[l].append(it)

    npc_y={}; item_y={}; fac_y={}; bands=[]
    # initial (stable) order
    for l in order:
        grp[l].sort(key=lambda n: npc_row[n][0])
        lane_items[l].sort(key=lambda it: item_name.get(it, ""))

    def layout():
        y=TOP; bands.clear()
        for l in order:
            ns=grp[l]; its=lane_items.get(l, [])
            rows=max(len(ns), len(its), 1); bh=rows*ROWH; y0=y
            noff=(bh-len(ns)*ROWH)/2; ioff=(bh-len(its)*ROWH)/2
            for i,n in enumerate(ns): npc_y[n]=y0+noff+i*ROWH+ROWH/2
            for i,it in enumerate(its): item_y[it]=y0+ioff+i*ROWH+ROWH/2
            fac_y[l]=y0+bh/2
            bands.append({"f":l,"label":(fac_name.get(l,"?") if l else "unaffiliated"),
                          "y0":y0-4,"y1":y0+bh+4,"n":len(ns)})
            y+=bh+GAP
        return y
    # barycentre sweeps: align connected NPC<->item pairs WITHIN each lane
    for _ in range(4):
        layout()
        for l in order:
            def ikey(it):
                ins=[p for p in prov[it] if lane_of[p]==l]
                return sum(npc_y[p] for p in ins)/len(ins) if ins else item_y.get(it,0)
            lane_items[l].sort(key=ikey)
            def nkey(n):
                its=[it for it in npc_items(n) if item_lane.get(it)==l]
                return sum(item_y[it] for it in its)/len(its) if its else npc_y[n]
            grp[l].sort(key=nkey)
    height=layout()+40

    # ---- assemble nodes/edges ----
    nodes=[]; edges=[]
    def ext_f(f): return len(fac_zones.get(f,set()))>=3   # spans the wider world
    def ext_i(i): return len(item_zones.get(i,set()))>=4
    for f in facs:
        nodes.append({"id":f"fac:{f}","type":"Faction","label":fac_name.get(f,"?"),
                      "x":XFAC,"y":round(fac_y[f],1),"external":ext_f(f),"deg":len(grp[f]),
                      "zc":len(fac_zones.get(f,set()))})
    for n in npcs:
        nm,iq,nfid,lt,mid = npc_row[n]
        nodes.append({"id":f"npc:{n}","type":"NPC","label":nm,"x":XNPC,"y":round(npc_y[n],1),
                      "quest":iq,"external":len(npc_zones.get(n,set()))>1,
                      "zc":len(npc_zones.get(n,set()))})
        pf=lane_of[n]
        if pf is not None:
            edges.append({"s":f"npc:{n}","t":f"fac:{pf}","pt":"member_of"})
        for it in npc_items(n):
            edges.append({"s":f"npc:{n}","t":f"item:{it}",
                          "pt":"sells" if (mid and it in merch_items.get(mid,set()) and not (lt and it in loot_items.get(lt,set()))) else "drops",
                          "xlane": item_lane.get(it) != pf})   # crosses faction lanes?
    for it,ps in prov.items():
        nodes.append({"id":f"item:{it}","type":"Item","label":item_name.get(it,"?"),
                      "x":XITEM,"y":round(item_y[it],1),"external":ext_i(it),"deg":len(ps),
                      "zc":len(item_zones.get(it,set()))})
    # neighbour zones (external geography)
    nbrs=[t for (t,) in q("SELECT DISTINCT target_zone_id FROM zone_points WHERE zone=%s",(zone,))]
    ny=TOP
    for tz in nbrs:
        ts=zid2short.get(tz)
        if not ts or ts==zone: continue
        nodes.append({"id":f"zone:{ts}","type":"Zone","label":zmeta.get(ts,(ts,))[0],
                      "x":XZONE,"y":ny,"external":True}); ny+=34
        edges.append({"s":"ZONEHDR","t":f"zone:{ts}","pt":"connects_to"})
    # faction<->faction ally/enemy among present factions
    present=set(facs)
    for k in set(co_same)|set(co_opp):
        f1,f2=k
        if f1 in present and f2 in present:
            same,opp=co_same[k],co_opp[k]
            if max(same,opp)<4: continue
            edges.append({"s":f"fac:{f1}","t":f"fac:{f2}",
                          "pt":"allied" if same>=opp else "opposed"})
    stats={"npcs":len(npcs),"factions":len(facs),"items":len(prov),
           "neighbors":len([n for n in nodes if n["type"]=="Zone"]),
           "ext_factions":sum(1 for n in nodes if n["type"]=="Faction" and n["external"]),
           "ext_items":sum(1 for n in nodes if n["type"]=="Item" and n["external"]),
           "quest_npcs":sum(1 for n in nodes if n.get("quest"))}
    return {"zone":zone,"long":zmeta.get(zone,(zone,))[0],
            "cols":{"XZONE":XZONE,"XFAC":XFAC,"XNPC":XNPC,"XITEM":XITEM},
            "width":1360,"height":round(height),"top":TOP,
            "bands":bands,"nodes":nodes,"edges":edges,"stats":stats,
            "zone_anchor_y":TOP-30}

manifest=[]
for z in ZONES:
    fig=build(z)
    json.dump(fig, open(f"/home/kevin/eq/analysis/zoneonto_{z}.json","w"))
    manifest.append({"zone":z,"long":fig["long"],"stats":fig["stats"]})
    s=fig["stats"]
    print(f"{z:10} NPCs={s['npcs']:3} fac={s['factions']:2} items={s['items']:3} "
          f"nbr={s['neighbors']} extFac={s['ext_factions']} extItem={s['ext_items']} "
          f"quest={s['quest_npcs']} h={fig['height']}")
json.dump(manifest, open("/home/kevin/eq/analysis/zoneonto_manifest.json","w"))
