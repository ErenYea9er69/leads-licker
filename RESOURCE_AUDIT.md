# Resource audit (3.3.1)

Method: measure first, change only what a measurement or a read of the code supports. Tools: cProfile over the full test suite, tracemalloc over a 200-directive loop, `-X importtime`, SQLite `EXPLAIN QUERY PLAN`, and micro benchmarks. The baseline is the 3.3.0 code.

## What the measurements showed

| Finding | Evidence | Change |
| --- | --- | --- |
| Every storage call ended with a WAL checkpoint and a WAL file delete | 4,641 connections in the test suite; commit and close took 1.97 s of 7 s. Micro benchmark: 1.26 ms per write and read | One idle connection per database file. 0.37 ms per write and read, same durability |
| Newest-first lists scanned and sorted whole tables | `EXPLAIN QUERY PLAN` showed SCAN and TEMP B-TREE for six queries | Six indexes. 100 list calls on 20,000 rows: 3,738 ms to 17 ms |
| The config file was read once per provider probe | 904 loads and 2,723 symlink checks in the suite | One read per client. 248 loads |
| Directive locks were never released | 220 locks held after 200 directives | Weak references. 0 held |
| `get_setting` broke on numeric values | Test failure on a stored int | Fixed |

A 200-directive loop took 7.30 s before and 3.55 s after.

## What did not change, and why

- Import memory. Importing the MCP server takes about 65 MB. The MCP SDK accounts for roughly 41 MB, `requests` 16 MB and pydantic 9 MB. The product needs all three. The project's own modules add about 13 MB. The CLI itself imports lazily and stays near 14 MB.
- Peak memory of the test suite: 89.8 MB before, 90.8 MB after. The idle connections and the new tests add about 1 MB. This audit did not lower resident memory in a short run. The memory gains apply to long runs: no growth in lock tables, and no full-table sorts on large lists.
- Python object leaks. A 200-directive tracemalloc run showed 0 live Task or Directive objects afterward and a resident size growth of 0.2 MB. That growth comes from pydantic's bounded string cache.
- HTTP sessions cost 6 KB each and close when dereferenced. Site fetches already cap the body at 1.5 MB. No change.
- Settings reads and team lookups (custom roles, business profile). They repeat, but each call is now about 0.1 ms. A cache would risk stale data across processes, so none was added.
- `_init_db` runs the schema script each time a storage object is created. The server creates one. Skipping it would change the secret scrub on start. No change.

## Safety checks

127 tests pass on MCP SDK 1.x and 2.x. Ruff and mypy pass. The skill validator and tool reference check pass. A real stdio session shows 32 company tools and 47 full tools, with no prompts. Eight threads writing 200 settings each showed no lock errors, with the same speed as before.

## Open items

- `AGENT_REACH_DB_SYNC=NORMAL` lowers write cost further. It risks losing the last transactions after a power cut, so it stays off by default.
- `team_events`, `posting_logs` and `discovered_items` grow without a limit. Pruning would remove owner data, so it needs the owner's decision.
