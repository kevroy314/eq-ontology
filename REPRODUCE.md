# Reproducing the EQ ontology analysis

End-to-end instructions to rebuild everything in this repo — the connectivity
graphs, the knowledge-graph ontology (including the LLM-extracted dialogue
edges), the zone figures, the anchored layout, and the dashboard — from the
committed source data.

Everything is derived from one artifact: the **Alkabor full database dump**
(`db/alkabor.tar.gz`, committed here, ~12 MB). Nothing else is required except
open-source tooling.

---

## 0. Prerequisites

- **Linux / WSL** (developed on WSL2, Ubuntu-flavored).
- **Python 3.12** with `venv`.
- **MySQL 5.7 server** (`mysqld`) — 5.7 specifically, because the dump relies on
  behaviors around zero-date defaults. Any 5.7.x works (developed with 5.7.24,
  the one bundled with Anaconda). MariaDB or MySQL 8 may need extra flag-tuning.
- **git**, **curl**.
- *(Optional, only to re-run the dialogue extraction)* an LLM with tool access.
  The extraction results are committed (`analysis/dialog_sem/out_*.json`), so
  this step is not required to rebuild the graphs.

Paths below assume the repo is at `~/eq`. All Python scripts connect to MySQL at
`127.0.0.1:3399` over the unix socket `db/mysql.sock` as user `root` (no
password) — adjust the connection block at the top of each script if your setup
differs.

---

## 1. Get the code

```bash
git clone https://github.com/kevroy314/eq-ontology.git ~/eq
cd ~/eq
```

## 2. Stand up the database

The dump is committed as a tarball. Extract it and load it into a **local**
MySQL 5.7 instance (a throwaway datadir, so nothing touches a system MySQL):

```bash
cd ~/eq/db
tar xzf alkabor.tar.gz            # -> alkabor_2024-03-01-11_57.sql (+ player/login/data dumps)

# one-time: initialize a local datadir with an empty-password root
mysqld --no-defaults --initialize-insecure \
       --datadir="$PWD/mysql_data" --basedir=/path/to/mysql

# start it on a dedicated port + socket (leave running in another shell / background)
mysqld --no-defaults --datadir="$PWD/mysql_data" --basedir=/path/to/mysql \
       --socket="$PWD/mysql.sock" --port=3399 --bind-address=127.0.0.1 &

# create the schema and load the content dump.
# IMPORTANT: the dump uses '0000-00-00' style defaults that MySQL 5.7 strict
# mode rejects, so blank sql_mode before sourcing.
M="mysql --no-defaults -uroot -S $PWD/mysql.sock"
$M -e "CREATE DATABASE IF NOT EXISTS alkabor CHARACTER SET utf8"
{ echo "SET GLOBAL sql_mode='';"; cat alkabor_2024-03-01-*.sql; } | $M alkabor
```

Sanity check:

```bash
mysql --no-defaults -uroot -S ~/eq/db/mysql.sock alkabor \
  -e "SELECT (SELECT COUNT(*) FROM zone) zones,
             (SELECT COUNT(*) FROM npc_types) npcs,
             (SELECT COUNT(*) FROM faction_list) factions"
# expect: zones=185  npcs=16906  factions=2117
```

> The tarball also contains `player_tables_*.sql` and `login_tables_*.sql`; they
> are character/account tables and are **not** needed for this analysis — only
> the main `alkabor_*.sql` content dump is loaded above.

## 3. Get the quest scripts (for dialogue only)

NPC dialogue lives in the Lua quest scripts, not the database. Clone them next to
the analysis:

```bash
cd ~/eq
git clone https://github.com/EQMacEmu/quests.git quests
```

You only need this if you want to **re-extract** dialogue (step 5c). Because the
extraction output is committed, you can skip it and still rebuild the ontology.

## 4. Python environment

```bash
cd ~/eq
python -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## 5. Run the pipeline

With mysqld from step 2 running, execute (from `~/eq`):

**a. Connectivity graphs + zone/city metrics** (takes ~1 min — community detection):
```bash
./.venv/bin/python analysis/build_graphs.py          # -> zone_metrics.json, cluster_metrics.json, viz_*.json
```

**b. Zone figures + anchored layout:**
```bash
./.venv/bin/python analysis/build_zone_ontology.py   # -> zoneonto_*.json  (layered swim-lane figures)
./.venv/bin/python analysis/build_anchored_layout.py # -> anchored_*.json  (spawn-seeded, faction-grouped)
```

**c. Dialogue edges** (the semantic `has dialog mentioning` relation):
```bash
# c1. pull each NPC's spoken lines from quests/ + exact-match hints
./.venv/bin/python analysis/build_dialog_extract.py  # -> dialog_records.json
# c2. SEMANTIC PASS (optional — results already committed as dialog_sem/out_*.json).
#     To regenerate: split dialog_records.json into batches (dialog_sem/in_*.json)
#     and have an LLM read each NPC's dialogue and emit referenced entities
#     (by name AND by epithet/role), writing dialog_sem/out_*.json. See the
#     "Dialogue extraction" note below for the exact task spec.
# c3. resolve referents to canonical DB entities -> edges
./.venv/bin/python analysis/build_dialog_edges.py    # -> dialog_edges.json
```

**d. Assemble the knowledge graph** (folds in every relation incl. dialogue):
```bash
./.venv/bin/python analysis/build_ontology.py        # -> onto_graph.json, onto_schema.json
```

**e. Publish to the dashboard:**
```bash
cp analysis/*.json server/data/
```

## 6. View it

```bash
./.venv/bin/python server/serve.py     # serves server/ on :8787 (caching disabled)
```
Open <http://localhost:8787>. The paper is at `/paper.html`.

---

## Dialogue extraction — task spec (step 5c2)

Each NPC's dialogue is read and reasoned over (not string-matched) to list the
other entities it references. The batch job splits ~293 NPCs across parallel LLM
workers; each worker, per speaker, returns mentions with:

- `referent` — canonical proper name (resolved from epithet/role where needed,
  e.g. "the governor of Qeynos" → *Antonius Bayle*);
- `type` — `npc | faction | place | item`;
- `how` — `name | epithet | role | pronoun`;
- `evidence` — a short supporting quote;
- `confidence` — `high | med | low`.

`build_dialog_edges.py` then resolves each `referent` to a canonical DB id
(exact → title-strip → surname → plural-aware fuzzy, with cross-type fallback);
unresolved lore entities (buildings, distant NPCs) are kept as `ext:` nodes.
String-only matching is too noisy for NPC names — the semantic pass is what makes
this relation usable.

## Connection / gotchas

- All scripts hard-code `host=127.0.0.1, port=3399, unix_socket=db/mysql.sock,
  user=root, db=alkabor`. Change the `pymysql.connect(...)` block if needed.
- An NPC's **canonical primary faction** is `npc_faction.primaryfaction`
  (→`faction_list.id`), *not* the max-value row in `npc_faction_entries`. The
  zone/anchored builders use `primaryfaction`.
- "Quests" are not in the DB — quest logic + dialogue are Lua in the `quests`
  repo. The DB gives factions, loot, merchants, spawns, spells, tradeskills.

## Provenance

The database and quest scripts are products of the EverQuest emulator community
(EQMacEmu / Project Quarm lineage) and are publicly distributed. This repo
redistributes the DB dump for reproducibility and otherwise contains only
*derived* analysis.
