"""
Extract each Qeynos NPC's spoken dialogue from the Lua quest scripts, then run a
high-precision string/alias entity-linker (overt mentions). Emits per-NPC records
with dialog text + candidate mentions, to be refined by a semantic LLM pass.
"""
import pymysql, collections, re, json, os, glob
conn = pymysql.connect(host="127.0.0.1", port=3399, user="root", db="alkabor",
                       unix_socket="/home/kevin/eq/db/mysql.sock")
cur = conn.cursor()
def q(s, a=None): cur.execute(s, a); return cur.fetchall()

QZONES = ["qeynos", "qeynos2", "qcat", "qeytoqrg", "qrg"]
QUESTDIR = "/home/kevin/eq/quests"

def norm(s):  # tokenise to lowercase words (drop punctuation, keep apostrophes)
    return " ".join(re.findall(r"[a-z']+", (s or "").lower()))
def clean(s): return (s or "").replace("_", " ").strip("# ").strip()

# ---- entity KB ----
zmeta = {sn:(clean(ln), zid) for sn,ln,zid in q("SELECT short_name,long_name,zoneidnumber FROM zone")}
fac_name = {f:clean(nm) for f,nm in q("SELECT id,name FROM faction_list")}
item_name = {i:clean(nm) for i,nm in q("SELECT id,Name FROM items")}
npc_name = {i:clean(nm) for i,nm in q("SELECT id,name FROM npc_types")}

# universe NPCs (spawn in Qeynos zones)
zin = "(" + ",".join(["%s"]*len(QZONES)) + ")"
seed = {}
for nid, z in q(f"""SELECT DISTINCT se.npcID, s2.zone FROM spawn2 s2
                    JOIN spawnentry se ON se.spawngroupID=s2.spawngroupID
                    WHERE s2.zone IN {zin}""", QZONES):
    seed.setdefault(nid, z)

# KB: normalized-name -> (type, id, canonical). Longest-match wins.
KB = {}
def add(name, typ, id_):
    k = norm(name)
    if len(k) < 5 or len(k.split()) < 1: return
    KB.setdefault(k, (typ, id_, clean(name)))
for f, nm in fac_name.items():
    if len(nm.split()) >= 2 or len(nm) >= 8: add(nm, "Faction", f)
for sn,(ln,zid) in zmeta.items():
    if len(ln) >= 5: add(ln, "Zone", sn)
for i, nm in npc_name.items():
    if len(nm.split()) >= 2: add(nm, "NPC", i)      # multi-token names only (precision)
for i, nm in item_name.items():
    if len(nm.split()) >= 2 and len(nm) >= 9: add(nm, "Item", i)

# name->npc id for resolving the speaker file
name2npc = collections.defaultdict(list)
for i, nm in npc_name.items(): name2npc[norm(nm)].append(i)

def link(text):
    toks = re.findall(r"[A-Za-z']+", text)
    low = [t.lower() for t in toks]
    found = {}
    i = 0
    while i < len(low):
        hit = None
        for L in range(5, 0, -1):
            if i+L <= len(low):
                ph = " ".join(low[i:i+L])
                if ph in KB: hit = (L, KB[ph]); break
        if hit:
            L, (typ, id_, canon) = hit
            found.setdefault((typ, id_), canon); i += L
        else:
            i += 1
    return found

SAY_RE = re.compile(r':(?:Say|Emote|QuestDialog)\(\s*(["\'])((?:\\.|(?!\1).)*)\1', re.S)
records = []
for z in QZONES:
    for path in sorted(glob.glob(os.path.join(QUESTDIR, z, "*.lua"))):
        base = os.path.basename(path)[:-4]
        if base.startswith("#"): continue                    # disabled scripts
        content = open(path, encoding="utf-8", errors="ignore").read()
        says = [m.group(2) for m in SAY_RE.finditer(content)]
        if not says: continue
        dialog = " ".join(s.replace("\\n", " ").replace("''", '"') for s in says)
        dialog = re.sub(r"\s+", " ", dialog).strip()
        if len(dialog) < 40: continue
        # resolve speaker id
        nm = clean(base)
        ids = name2npc.get(norm(nm), [])
        sid = next((i for i in ids if i in seed), ids[0] if ids else None)
        cands = link(dialog)
        cands = [{"type":t, "id":i, "name":c} for (t,i),c in cands.items()
                 if not (t=="NPC" and i==sid)]
        records.append({"speaker_id": sid, "speaker": nm, "zone": z,
                        "n_say": len(says), "dialog": dialog[:6000],
                        "exact": cands})

records.sort(key=lambda r: -len(r["dialog"]))
json.dump(records, open("/home/kevin/eq/analysis/dialog_records.json","w"))

tot_cand = sum(len(r["exact"]) for r in records)
by_zone = collections.Counter(r["zone"] for r in records)
print(f"NPCs with dialog: {len(records)}   (by zone: {dict(by_zone)})")
print(f"speaker resolved to id: {sum(1 for r in records if r['speaker_id'])}/{len(records)}")
print(f"total exact-match candidate mentions: {tot_cand} (avg {tot_cand/len(records):.1f}/npc)")
print(f"dialog chars total: {sum(len(r['dialog']) for r in records):,}")
print("\n--- top 3 by dialog length: speaker + exact mentions ---")
for r in records[:3]:
    print(f"\n### {r['speaker']} ({r['zone']}, {r['n_say']} say, {len(r['dialog'])} chars)")
    print("  exact:", ", ".join(f"{c['name']}[{c['type']}]" for c in r["exact"][:14]))
