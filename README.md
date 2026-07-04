# eq-ontology

Graph-theoretic and **ontological** analysis of the EverQuest (Project-Quarm-era / EQMacEmu "Alkabor") world database, built to answer one question — *does the city of Qeynos really have the densest quest connectivity in the game?* — and then to reconstruct the world as a proper directed knowledge graph.

An interactive dashboard visualizes everything; a companion research paper proposes how to make these auto-generated layouts read like hand-drawn ones.

---

## The finding

Treated as a **city cluster** (South + North Qeynos + the Aqueducts), **Qeynos ranks #1 of every city in EQ** for quest-web richness — a blend of quest-giver count, how densely those quest-givers interlink, and *faction diversity*. It roughly doubles its nearest rival, Freeport. No single Qeynos *zone* tops any single metric (Shadow Haven has more quest NPCs but only 6 factions; dragon dungeons win naive graph density by being one monolithic clique) — Qeynos wins by being **broad and varied**: ~67 distinct factions woven through ~160 quest-givers.

## What's here

| Path | What |
|---|---|
| `analysis/build_graphs.py` | Per-zone + city-cluster connectivity graphs (networkx): density, clustering, communities, quest-web richness score. |
| `analysis/build_ontology.py` | Directed, typed **knowledge graph** for the Qeynos universe — 15 relations (spawns in, is a member of, raises/lowers standing, drops, sells, casts, connects to, crafting, derived faction ally/enemy, **has dialog mentioning**). |
| `analysis/build_zone_ontology.py` | Deliberate **layered zone figure**: neighbouring-zones → faction swim-lanes → NPCs → items, positions computed for a clean, intentional layout. |
| `analysis/build_dialog_extract.py` | Pulls each Qeynos NPC's spoken dialogue from the Lua quest scripts. |
| `analysis/dialog_sem/out_*.json` | **Semantic** dialogue extraction (10 LLM subagents): each NPC's dialogue reasoned for referenced entities, by name *and* by epithet/role. |
| `analysis/build_dialog_edges.py` | Resolves those referents to canonical DB entities (fuzzy + cross-type) → `has dialog mentioning` edges. |
| `analysis/layout_paper.html` | Lit review + proposal: *Making Machine-Drawn Ontologies Look Hand-Drawn.* |
| `server/` | The dashboard (`index.html`), the paper (`paper.html`), the no-cache dev server (`serve.py`), and all rendered data (`data/*.json`). |

## The dashboard

```bash
python server/serve.py      # serves server/ on :8787 with caching disabled
```
Then open <http://localhost:8787>. Sections: the verdict, a city-cluster leaderboard, an interactive canvas network graph, an **ontology view** (schema diagram + click-to-traverse ego-explorer + a zone-scoped layered figure), a sortable 173-zone table, and a link to the research paper.

## Reproducing from scratch

The raw database and the third-party quest scripts are **not** committed (size / provenance). To regenerate:

1. **Database.** Download the Alkabor full dump from
   `EQMacEmu/Server` → `utils/sql/database_full/` and load it into a local MySQL 5.7:
   ```bash
   mysqld --datadir=db/mysql_data --socket=db/mysql.sock --port=3399   # first: --initialize-insecure
   mysql -uroot -S db/mysql.sock -e "CREATE DATABASE alkabor CHARACTER SET utf8"
   { echo "SET GLOBAL sql_mode='';"; cat db/alkabor_*.sql; } | mysql -uroot -S db/mysql.sock alkabor
   ```
   (The dump uses zero-date defaults MySQL 5.7 strict mode rejects — hence `sql_mode=''`.)
2. **Quest scripts** (for dialogue): `git clone https://github.com/EQMacEmu/quests.git quests`
3. **Python env:** `python -m venv .venv && ./.venv/bin/pip install -r requirements.txt`
4. **Run** (all connect to MySQL on `127.0.0.1:3399`, socket `db/mysql.sock`):
   ```bash
   ./.venv/bin/python analysis/build_graphs.py
   ./.venv/bin/python analysis/build_zone_ontology.py
   ./.venv/bin/python analysis/build_dialog_extract.py   # then the semantic pass, then:
   ./.venv/bin/python analysis/build_dialog_edges.py
   ./.venv/bin/python analysis/build_ontology.py
   cp analysis/*.json server/data/
   ```

The `has dialog mentioning` semantic pass (`dialog_sem/out_*.json`) is committed so you don't have to re-run the LLM extraction; `build_dialog_edges.py` consumes it directly.

## Data & code provenance

Database content © the EverQuest emulator community (EQMacEmu / Project Quarm lineage); this repo contains only *derived* analysis, not the raw game data or quest scripts.
