"""
Build a DIRECTED, TYPED, LABELLED ontology (knowledge graph) for the Qeynos universe.

Entity types : NPC, Faction, Item, Zone, Spell, Recipe
Predicates (subject -[action phrase]-> object):
  NPC   -spawns in->            Zone
  NPC   -is a member of->       Faction        (primary faction)
  NPC   -raises standing with-> Faction        (npc_faction_entries value>0)
  NPC   -lowers standing with-> Faction        (value<0)
  NPC   -drops->                Item           (loot, non-commodity)
  NPC   -sells->                Item           (merchant, non-commodity)
  NPC   -casts->                Spell
  Zone  -connects to->          Zone           (zone_points)
  Zone  -yields (forage)->      Item
  Zone  -yields (fishing)->     Item
  Item  -is an ingredient in->  Recipe
  Recipe-produces->             Item
  Faction -is allied with->     Faction        (DERIVED: co-signed in NPC hit-lists)
  Faction -is opposed to->      Faction        (DERIVED: opposite-signed)

Scope = every NPC spawning in the Qeynos zones + all entities they touch (1 hop),
plus derived faction<->faction edges touching those factions.
"""
import pymysql, collections, itertools, json, html
conn = pymysql.connect(host="127.0.0.1", port=3399, user="root", db="alkabor",
                       unix_socket="/home/kevin/eq/db/mysql.sock")
cur = conn.cursor()
def q(s, a=None): cur.execute(s, a); return cur.fetchall()

QZONES = ["qeynos", "qeynos2", "qcat", "qeytoqrg", "qrg"]
ITEM_CAP = 40           # keep quest-relevant (non-commodity) items only
qz_in = "(" + ",".join(["%s"] * len(QZONES)) + ")"

def clean(s):
    return (s or "").replace("_", " ").strip("# ").strip() or "?"

# ---------- nodes & triples containers ----------
nodes = {}   # id -> {id,type,label}
triples = []
def node(nid, typ, label):
    if nid not in nodes: nodes[nid] = {"id": nid, "type": typ, "label": clean(label)}
    return nid
def triple(s, p, o, pt):
    triples.append({"s": s, "p": p, "o": o, "pt": pt})

# ---------- seed NPCs (spawn in Qeynos zones) ----------
rows = q(f"""SELECT DISTINCT se.npcID, s2.zone FROM spawn2 s2
             JOIN spawnentry se ON se.spawngroupID=s2.spawngroupID
             WHERE s2.zone IN {qz_in}""", QZONES)
npc_zone = collections.defaultdict(set)
for nid, z in rows: npc_zone[nid].add(z)
seed_npcs = set(npc_zone)

npc_meta = {i:(nm, lt, mid, sp, nfid) for i,nm,lt,mid,sp,nfid in
            q("SELECT id,name,loottable_id,merchant_id,npc_spells_id,npc_faction_id FROM npc_types")}
zmeta = {sn:(ln, zid) for sn,ln,zid in q("SELECT short_name,long_name,zoneidnumber FROM zone")}
zid2short = {zid:sn for sn,(ln,zid) in zmeta.items()}
fac_name = {f:nm for f,nm in q("SELECT id,name FROM faction_list")}
item_name = {i:nm for i,nm in q("SELECT id,Name FROM items")}
spell_name = {i:nm for i,nm in q("SELECT id,name FROM spells_new")}

# item global frequency (for commodity filter) -- reuse loot+merchant
item_freq = collections.Counter()
for (i,) in [(r[0],) for r in q("""SELECT lde.item_id FROM lootdrop_entries lde""")]:
    item_freq[i] += 1  # rough; refined below
item_freq = collections.Counter()
for i, c in q("""SELECT item_id, COUNT(DISTINCT nt.id) FROM npc_types nt
                 JOIN loottable_entries lte ON lte.loottable_id=nt.loottable_id
                 JOIN lootdrop_entries lde ON lde.lootdrop_id=lte.lootdrop_id
                 GROUP BY item_id"""):
    item_freq[i] += c
for i, c in q("""SELECT ml.item, COUNT(DISTINCT nt.id) FROM npc_types nt
                 JOIN merchantlist ml ON ml.merchantid=nt.merchant_id GROUP BY ml.item"""):
    item_freq[i] += c

def Z(short):
    ln, zid = zmeta.get(short, (short, 0)); return node(f"zone:{short}", "Zone", ln)
def F(fid):   return node(f"fac:{fid}", "Faction", fac_name.get(fid, f"faction {fid}"))
def I(iid):   return node(f"item:{iid}", "Item", item_name.get(iid, f"item {iid}"))
def SP(sid):  return node(f"spell:{sid}", "Spell", spell_name.get(sid, f"spell {sid}"))
def N(nid):   return node(f"npc:{nid}", "NPC", npc_meta.get(nid, (f"npc {nid}",))[0])

# ---------- per-NPC predicates ----------
# preload loot: loottable -> items
loot_items = collections.defaultdict(set)
for lt, iid in q("""SELECT lte.loottable_id, lde.item_id FROM loottable_entries lte
                    JOIN lootdrop_entries lde ON lde.lootdrop_id=lte.lootdrop_id"""):
    loot_items[lt].add(iid)
merch_items = collections.defaultdict(set)
for mid, iid in q("SELECT merchantid, item FROM merchantlist"): merch_items[mid].add(iid)
# npc faction entries
nf_entries = collections.defaultdict(list)   # npc_faction_id -> [(faction_id,value)]
for nfid, fid, val in q("SELECT npc_faction_id,faction_id,value FROM npc_faction_entries"):
    nf_entries[nfid].append((fid, val))
# npc spells
ns_spells = collections.defaultdict(set)
for nsid, sid in q("SELECT npc_spells_id, spellid FROM npc_spells_entries WHERE spellid>0"):
    ns_spells[nsid].add(sid)

used_factions = set()
for nid in seed_npcs:
    nm, lt, mid, spid, nfid = npc_meta.get(nid, (None,0,0,0,0))
    if nm is None: continue
    s = N(nid)
    for z in npc_zone[nid]:
        triple(s, "spawns in", Z(z), "spawns_in")
    # factions
    if nfid and nfid in nf_entries:
        ents = nf_entries[nfid]
        # primary = the highest positive standing = "is a member of"
        pos = [(f,v) for f,v in ents if v > 0]
        prim = max(pos, key=lambda x:x[1])[0] if pos else None
        for f, v in ents:
            used_factions.add(f)
            if f == prim:
                triple(s, "is a member of", F(f), "member_of")
            elif v > 0:
                triple(s, "raises standing with", F(f), "raises")
            elif v < 0:
                triple(s, "lowers standing with", F(f), "lowers")
    # loot
    if lt:
        for iid in loot_items.get(lt, ()):
            if item_freq.get(iid, 0) <= ITEM_CAP:
                triple(s, "drops", I(iid), "drops")
    # merchant
    if mid:
        for iid in merch_items.get(mid, ()):
            if item_freq.get(iid, 0) <= ITEM_CAP:
                triple(s, "sells", I(iid), "sells")
    # spells
    if spid:
        for sid in ns_spells.get(spid, ()):
            triple(s, "casts", SP(sid), "casts")

# ---------- zone -> zone (connects to) ----------
for z in QZONES:
    for (tgt,) in q("SELECT DISTINCT target_zone_id FROM zone_points WHERE zone=%s", (z,)):
        ts = zid2short.get(tgt)
        if ts and ts != z:
            triple(Z(z), "connects to", Z(ts), "connects_to")

# ---------- zone forage / fishing ----------
for z in QZONES:
    _, zid = zmeta.get(z, (z, 0))
    for (iid,) in q("SELECT DISTINCT Itemid FROM forage WHERE zoneid=%s AND Itemid>0", (zid,)):
        triple(Z(z), "yields (foraging)", I(iid), "forage")
    for (iid,) in q("SELECT DISTINCT Itemid FROM fishing WHERE zoneid=%s AND Itemid>0", (zid,)):
        triple(Z(z), "yields (fishing)", I(iid), "fishing")

# ---------- tradeskill: items in universe that are ingredients ----------
universe_items = {int(k.split(":")[1]) for k in nodes if k.startswith("item:")}
REC_PER_ITEM = 6        # cap so a common ingredient doesn't drag in the whole craft web
if universe_items:
    fmt = ",".join(["%s"]*len(universe_items))
    rec_hit = q(f"""SELECT tre.recipe_id, tre.item_id, tre.iscontainer, tre.componentcount
                    FROM tradeskill_recipe_entries tre
                    WHERE tre.item_id IN ({fmt})""", tuple(universe_items))
    # keep only ingredient rows, cap recipes per item
    per_item = collections.defaultdict(list)
    for rid, iid, iscont, cc in rec_hit:
        if iscont or (cc and cc > 0):
            per_item[iid].append(rid)
    recs = set()
    for iid, rids in per_item.items():
        for rid in sorted(set(rids))[:REC_PER_ITEM]:
            recs.add(rid)
            rnode = node(f"recipe:{rid}", "Recipe", f"recipe {rid}")
            triple(I(iid), "is an ingredient in", rnode, "ingredient_in")
    if recs:
        rec_name = dict(q(f"SELECT id,name FROM tradeskill_recipe WHERE id IN ({','.join(['%s']*len(recs))})",
                          tuple(recs)))
        for rid in recs:
            if rid in rec_name: nodes[f"recipe:{rid}"]["label"] = clean(rec_name[rid])
        for rid, iid, iscont, cc, sc in q(
            f"""SELECT recipe_id,item_id,iscontainer,componentcount,successcount
                FROM tradeskill_recipe_entries
                WHERE recipe_id IN ({','.join(['%s']*len(recs))})""", tuple(recs)):
            if sc and sc > 0 and not iscont:  # product
                rnode = node(f"recipe:{rid}", "Recipe", rec_name.get(rid, f"recipe {rid}"))
                triple(rnode, "produces", I(iid), "produces")

# ---------- DERIVED faction<->faction ally / enemy ----------
# co-occurrence of signs across ALL npc faction hit-lists (global relationships)
co_same = collections.Counter(); co_opp = collections.Counter()
for nfid, ents in nf_entries.items():
    sig = [(f, (1 if v>0 else -1)) for f, v in ents if v != 0]
    for (f1,s1),(f2,s2) in itertools.combinations(sig, 2):
        key = (min(f1,f2), max(f1,f2))
        if s1 == s2: co_same[key] += 1
        else: co_opp[key] += 1
MIN = 4
added_fac = set()
for key in set(co_same) | set(co_opp):
    f1, f2 = key
    if f1 not in used_factions and f2 not in used_factions:  # keep near Qeynos
        continue
    same, opp = co_same[key], co_opp[key]
    if max(same, opp) < MIN: continue
    if same >= opp and same >= MIN:
        triple(F(f1), "is allied with", F(f2), "allied"); added_fac.add(key)
    elif opp > same and opp >= MIN:
        triple(F(f1), "is opposed to", F(f2), "opposed"); added_fac.add(key)

# ---------- dialogue: 'has dialog mentioning' (semantic LLM extraction) ----------
import os as _os
DLG = "/home/kevin/eq/analysis/dialog_edges.json"
if _os.path.exists(DLG):
    dd = json.load(open(DLG)); extn = dd["ext_nodes"]; n_dlg = 0
    for e in dd["edges"]:
        s = N(e["speaker_id"]); tgt = e["target"]
        try:
            if tgt.startswith("npc:"):    o = N(int(tgt[4:]))
            elif tgt.startswith("fac:"):  o = F(int(tgt[4:]))
            elif tgt.startswith("item:"): o = I(int(tgt[5:]))
            elif tgt.startswith("zone:"): o = Z(tgt[5:])
            elif tgt.startswith("ext:"):
                meta = extn.get(tgt, {"label": tgt, "type": "NPC"})
                o = node(tgt, meta["type"], meta["label"]); nodes[tgt]["lore"] = True
            else: continue
        except Exception:
            continue
        if o == s: continue
        triples.append({"s": s, "p": "has dialog mentioning", "o": o, "pt": "mentions",
                        "how": e.get("how"), "conf": e.get("confidence"), "ev": e.get("evidence")})
        n_dlg += 1
    print(f"dialog 'mentions' edges added: {n_dlg}")

# ---------- schema (TBox) counts ----------
type_counts = collections.Counter(n["type"] for n in nodes.values())
pred_counts = collections.Counter(t["p"] for t in triples)
# predicate -> (subject type, object type) for schema arrows
PRED_SCHEMA = [
    ("NPC","spawns in","Zone","spawns_in"),
    ("NPC","is a member of","Faction","member_of"),
    ("NPC","raises standing with","Faction","raises"),
    ("NPC","lowers standing with","Faction","lowers"),
    ("NPC","drops","Item","drops"),
    ("NPC","sells","Item","sells"),
    ("NPC","casts","Spell","casts"),
    ("Zone","connects to","Zone","connects_to"),
    ("Zone","yields (forage/fishing)","Item","forage"),
    ("Item","is an ingredient in","Recipe","ingredient_in"),
    ("Recipe","produces","Item","produces"),
    ("Faction","is allied with","Faction","allied"),
    ("Faction","is opposed to","Faction","opposed"),
    ("NPC","has dialog mentioning","NPC","mentions"),
]

# degree for defaults / featured
deg = collections.Counter()
for t in triples:
    deg[t["s"]] += 1; deg[t["o"]] += 1
for n in nodes.values():
    n["deg"] = deg[n["id"]]

schema = {
    "type_counts": dict(type_counts),
    "pred_counts": dict(pred_counts),
    "pred_schema": [{"s":s,"p":p,"o":o,"pt":pt,"count":pred_counts.get(p,0)} for s,p,o,pt in PRED_SCHEMA],
    "n_nodes": len(nodes), "n_triples": len(triples),
}
# featured entities: top-degree NPCs + top factions
feat_npc = sorted((n for n in nodes.values() if n["type"]=="NPC"), key=lambda n:-n["deg"])[:6]
feat_fac = sorted((n for n in nodes.values() if n["type"]=="Faction"), key=lambda n:-n["deg"])[:4]
schema["featured"] = [{"id":n["id"],"label":n["label"],"type":n["type"]} for n in feat_npc+feat_fac]
schema["default_center"] = feat_fac[0]["id"] if feat_fac else (feat_npc[0]["id"] if feat_npc else None)

json.dump({"nodes":list(nodes.values()),"triples":triples},
          open("/home/kevin/eq/analysis/onto_graph.json","w"))
json.dump(schema, open("/home/kevin/eq/analysis/onto_schema.json","w"), indent=1)

print("nodes:", len(nodes), "triples:", len(triples))
print("types:", dict(type_counts))
print("predicates:")
for s,p,o,pt in PRED_SCHEMA:
    print(f"   {s:8}-{p:24}->{o:8}  {pred_counts.get(p,0)}")
print("default center:", schema["default_center"], "->",
      nodes.get(schema["default_center"],{}).get("label"))
print("featured:", [n["label"] for n in feat_npc+feat_fac])
import os
print("onto_graph.json size: %.1f KB" % (os.path.getsize("/home/kevin/eq/analysis/onto_graph.json")/1024))
