import pymysql, collections
c = pymysql.connect(host="127.0.0.1", port=3399, user="root", db="alkabor",
                    unix_socket="/home/kevin/eq/db/mysql.sock", cursorclass=pymysql.cursors.Cursor)
cur = c.cursor()

def q(sql):
    cur.execute(sql); return cur.fetchall()

# NPC -> zone (via spawn2 -> spawnentry). zone col is short_name.
rows = q("""
SELECT DISTINCT s2.zone, se.npcID
FROM spawn2 s2 JOIN spawnentry se ON se.spawngroupID=s2.spawngroupID
""")
npc_zone = collections.defaultdict(set)
zone_npcs = collections.defaultdict(set)
for z,n in rows:
    npc_zone[n].add(z); zone_npcs[z].add(n)
print("distinct spawned NPCs:", len(npc_zone), "zones with spawns:", len(zone_npcs))

# NPC -> factions
rows = q("""
SELECT nt.id, fe.faction_id
FROM npc_types nt
JOIN npc_faction_entries fe ON fe.npc_faction_id = nt.npc_faction_id
WHERE nt.npc_faction_id>0
""")
npc_fac = collections.defaultdict(set)
fac_npcs = collections.defaultdict(set)
for n,f in rows:
    npc_fac[n].add(f); fac_npcs[f].add(n)
print("NPCs with factions:", len(npc_fac), "distinct factions used:", len(fac_npcs))
fac_sizes = sorted((len(v) for v in fac_npcs.values()), reverse=True)
print("faction size (npc count) top20:", fac_sizes[:20])
print("faction size pctiles: median", fac_sizes[len(fac_sizes)//2], "p90", fac_sizes[len(fac_sizes)//10])

# NPC -> items (loot)
rows = q("""
SELECT nt.id, lde.item_id
FROM npc_types nt
JOIN loottable_entries lte ON lte.loottable_id = nt.loottable_id
JOIN lootdrop_entries lde ON lde.lootdrop_id = lte.lootdrop_id
WHERE nt.loottable_id>0
""")
npc_item = collections.defaultdict(set)
item_npcs = collections.defaultdict(set)
for n,i in rows:
    npc_item[n].add(i); item_npcs[i].add(n)
# NPC -> items (merchant)
rows = q("""
SELECT nt.id, ml.item
FROM npc_types nt
JOIN merchantlist ml ON ml.merchantid = nt.merchant_id
WHERE nt.merchant_id>0
""")
for n,i in rows:
    npc_item[n].add(i); item_npcs[i].add(n)
print("NPCs with items:", len(npc_item), "distinct items:", len(item_npcs))
item_freq = sorted((len(v) for v in item_npcs.values()), reverse=True)
print("item npc-freq top25:", item_freq[:25])
import numpy as np
arr=np.array(item_freq)
for p in [50,75,90,95,99]:
    print(f"item freq p{p}:", int(np.percentile(arr,p)))
print("items held by 1 npc:", sum(1 for x in item_freq if x==1), "/", len(item_freq))

# top commodity items by name
rows = q("""
SELECT i.Name, cnt FROM (
  SELECT item_id, COUNT(*) cnt FROM (
    SELECT DISTINCT nt.id nid, lde.item_id FROM npc_types nt
      JOIN loottable_entries lte ON lte.loottable_id=nt.loottable_id
      JOIN lootdrop_entries lde ON lde.lootdrop_id=lte.lootdrop_id
    UNION
    SELECT DISTINCT nt.id, ml.item FROM npc_types nt JOIN merchantlist ml ON ml.merchantid=nt.merchant_id
  ) t GROUP BY item_id ORDER BY cnt DESC LIMIT 15
) top JOIN items i ON i.id=top.item_id ORDER BY cnt DESC
""")
print("=== top commodity items ===")
for name,cnt in rows: print(f"  {cnt:5d}  {name}")
