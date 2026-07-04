"""
Merge the 10 semantic dialog-extraction outputs, resolve each referent to a
canonical DB entity (NPC/faction/zone/item) or keep it as an external lore node,
and emit 'has dialog mentioning' edges for the ontology.
"""
import pymysql, collections, re, json, glob
conn = pymysql.connect(host="127.0.0.1", port=3399, user="root", db="alkabor",
                       unix_socket="/home/kevin/eq/db/mysql.sock")
cur = conn.cursor()
def q(s, a=None): cur.execute(s, a); return cur.fetchall()

QZONES = ["qeynos", "qeynos2", "qcat", "qeytoqrg", "qrg"]
def norm(s): return " ".join(re.findall(r"[a-z']+", (s or "").lower()))
def clean(s): return (s or "").replace("_", " ").strip("# ").strip()

# universe NPC ids (Qeynos)
zin = "(" + ",".join(["%s"]*len(QZONES)) + ")"
seed = set(n for (n,) in q(f"""SELECT DISTINCT se.npcID FROM spawn2 s2
    JOIN spawnentry se ON se.spawngroupID=s2.spawngroupID WHERE s2.zone IN {zin}""", QZONES))

# resolver indices
npc_idx = {}                       # norm name -> npc id (prefer universe)
for i, nm in q("SELECT id,name FROM npc_types"):
    k = norm(nm)
    if not k: continue
    if k not in npc_idx or (i in seed and npc_idx[k] not in seed):
        npc_idx[k] = i
fac_idx = {norm(nm): f for f, nm in q("SELECT id,name FROM faction_list") if norm(nm)}
item_idx = {norm(nm): i for i, nm in q("SELECT id,Name FROM items") if norm(nm)}
zone_idx = {}
for sn, ln in q("SELECT short_name,long_name FROM zone"):
    if norm(ln): zone_idx[norm(ln)] = sn
    zone_idx.setdefault(norm(sn), sn)
ZONE_ALIAS = {"north qeynos":"qeynos2","south qeynos":"qeynos","qeynos hills":"qeytoqrg",
    "surefall glade":"qrg","qeynos catacombs":"qcat","qeynos aqueduct":"qcat","aqueducts":"qcat",
    "everfrost":"everfrost","plane of sky":"airplane","the plane of sky":"airplane",
    "highpass":"highpass","kithicor":"kithicor","kithicor forest":"kithicor","kithicor woods":"kithicor"}
zone_idx.update(ZONE_ALIAS)

from difflib import SequenceMatcher
TITLES = {"captain","sir","lord","lady","ambassador","commander","field","marshall","marshal",
          "priestess","priest","general","sergeant","lieutenant","king","queen","master","apprentice",
          "elder","the","governor","brother","sister","mayor","councilman","a","of","and"}
BLACK = {"life", "truth", "the truth", "death", "war", "peace"}   # abstract referents -> keep external
def strip_titles(k):
    return " ".join(t for t in k.split() if t not in TITLES)
def sig(k):  # distinctive tokens
    return set(t for t in k.split() if t not in TITLES and len(t) >= 3)
def teq(a, b):        # plural-insensitive token equality (guard~guards, hand~hands)
    return a == b or a + "s" == b or b + "s" == a
def tsub(A, B):       # every token in A matches some token in B (under teq)
    return all(any(teq(a, b) for b in B) for a in A)

DICTS = {"npc": (npc_idx, "npc"), "faction": (fac_idx, "fac"),
         "place": (zone_idx, "zone"), "item": (item_idx, "item")}
# token -> set of norm-names, per type (for fuzzy candidate gathering)
tok_index = {t: collections.defaultdict(set) for t in DICTS}
for t,(d,_) in DICTS.items():
    for nm in d:
        for tok in sig(nm): tok_index[t][tok].add(nm)

def _try(d, kind, k):
    for c in [k, strip_titles(k)] + ([k.split()[-1]] if len(k.split())>=2 else []):
        if c and c in d: return kind, d[c]
    # fuzzy within this type — score ALL candidates, pick the best acceptable one
    ks = sig(k)
    if not ks: return None
    cands = set()
    for tok in ks: cands |= tok_index[kind_to_type(kind)].get(tok, set())
    best=None; bestscore=0.0
    for nm in cands:
        ns = sig(nm)
        if not ns: continue
        r = SequenceMatcher(None, k, nm).ratio()
        equal  = len(ns) == len(ks) and tsub(ks, ns) and tsub(ns, ks)
        subset = (tsub(ns, ks) or tsub(ks, ns)) and \
                 max((len(a) for a in ks for b in ns if teq(a, b)), default=0) >= 4
        ok = equal or r >= 0.9 or (subset and r >= 0.7)
        if not ok: continue
        score = r + (0.6 if equal else 0) + (0.2 if subset else 0) - 0.03*abs(len(ns)-len(ks))
        if score > bestscore: bestscore, best = score, d[nm]
    return (kind, best) if best is not None else None
def kind_to_type(kind): return {"npc":"npc","fac":"faction","zone":"place","item":"item"}[kind]

def resolve(ref, typ):
    k = norm(ref)
    if not k or k in BLACK: return None
    order = [typ] + [t for t in ["faction","npc","place"] if t != typ]  # declared type first, then cross-type
    for t in order:
        d, kind = DICTS[t]
        r = _try(d, kind, k)
        if r: return r
    return None

conf_rank = {"high": 3, "med": 2, "low": 1}
edges = {}   # (speaker_id, kind, key) -> record
ext_nodes = {}   # ext id -> {label,type}
stats = collections.Counter()
files = sorted(glob.glob("/home/kevin/eq/analysis/dialog_sem/out_*.json"))
for f in files:
    for rec in json.load(open(f)):
        sid = rec.get("speaker_id")
        if not sid: continue
        for m in rec.get("mentions", []):
            ref = (m.get("referent") or "").strip()
            typ = (m.get("type") or "npc").lower()
            if not ref or len(ref) < 3: continue
            conf = (m.get("confidence") or "med").lower()
            r = resolve(ref, typ)
            if r:
                kind, cid = r
                key = f"{kind}:{cid}"
                if kind == "npc" and cid == sid:   # self-mention
                    continue
                resolved = True
            else:
                slug = re.sub(r"[^a-z0-9]+", "_", ref.lower()).strip("_")[:40]
                tmap = {"npc":"NPC","faction":"Faction","place":"Zone","item":"Item"}
                key = f"ext:{typ}:{slug}"
                ext_nodes[key] = {"label": clean(ref), "type": tmap.get(typ, "NPC")}
                resolved = False
            stats["resolved" if r else "external"] += 1
            stats[f"type_{typ}"] += 1
            e = edges.get((sid, key))
            if not e or conf_rank.get(conf,2) > conf_rank.get(e["confidence"],2):
                edges[(sid, key)] = {"speaker_id": sid, "target": key, "referent": clean(ref),
                                     "how": m.get("how","name"), "confidence": conf,
                                     "evidence": (m.get("evidence") or "")[:160], "resolved": resolved}

edge_list = list(edges.values())
json.dump({"edges": edge_list, "ext_nodes": ext_nodes},
          open("/home/kevin/eq/analysis/dialog_edges.json", "w"))

print(f"input files: {len(files)}")
print(f"unique dialog edges: {len(edge_list)}  (resolved {stats['resolved']}, external {stats['external']})")
print("by type:", {k[5:]:v for k,v in stats.items() if k.startswith('type_')})
print("by confidence:", dict(collections.Counter(e['confidence'] for e in edge_list)))
print("external lore nodes:", len(ext_nodes))
# most-mentioned targets
tc = collections.Counter(e["target"] for e in edge_list)
def lbl(key):
    kind,_,rest = key.partition(":")
    if key.startswith("ext:"): return ext_nodes[key]["label"]+" (ext)"
    if kind=="npc": return next((clean(nm) for i,nm in q("SELECT id,name FROM npc_types WHERE id=%s",(int(rest),))),rest)
    if kind=="fac": return next((clean(nm) for i,nm in q("SELECT id,name FROM faction_list WHERE id=%s",(int(rest),))),rest)
    if kind=="zone": return rest
    if kind=="item": return next((clean(nm) for i,nm in q("SELECT id,Name FROM items WHERE id=%s",(int(rest),))),rest)
    return key
print("\ntop 20 most-mentioned entities:")
for key,c in tc.most_common(20):
    print(f"  {c:3}  {lbl(key)}")
