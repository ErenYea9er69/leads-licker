# Audit

This file lists what the audit of the uploaded backend found, what changed and what is still open. It follows the sections of the app.

## How the audit was done

- Read in full: README, the architecture note, every doc, `pyproject.toml`, CI, `mcp/server.py`, `mcp/compat.py`, `mcp/helpers.py`, `discovery/orchestrator.py`, `discovery/llm_client.py`, `discovery/models.py`, `config.py`, `utils/paths.py`, `server/app.py` (routes and settings), `scripts/validate_skills.py`.
- Read in part (the parts that decide trust and secrets): `storage.py`, `publisher.py`, `qualifier.py`, `business_engine.py`, `search_backends.py`, `skillpack.py`, `security.py`.
- Not read line by line: `harvester.py`, `thread_check.py`, `thread_comments.py`, `voice.py`, `reply_generator.py`, `accounts.py`, `analytics.py`, `search_planner.py`, `platform_policy.py`, `llm_mock.py`. They pass ruff, mypy, the skill validator (which lints every example reply) and the test suite, and the team verifier calls them. A deeper read of those files is still worth doing.
- Tools: a static import graph from the entry points, grep for references to missing files, ruff, mypy, the skill validator, a wheel build, a clean install, a real MCP stdio session on SDK 1.30 and 2.3.

## 1. Packaging and configuration

| Finding | Status |
| --- | --- |
| Four different version numbers: package 2.2.0, `agent_reach/__init__` 1.6.0, discovery 2.1.0, API 2.1.0, user agent 2.2 | Fixed: 3.0.0 everywhere the code reads it from `__version__` |
| `yt-dlp` pinned to an exact version and `loguru` listed. Nothing in discovery or MCP uses them after the legacy stack is gone | Removed |
| Keywords and classifiers describe the old tool (bilibili, xiaohongshu, twitter-scraper, youtube-transcript, free-api) | Replaced |
| Project URLs point to the upstream project | Removed. Add yours |
| `sdist` includes `AUDIT.md`, `CHANGELOG.md`, `constraints.txt`, `llms.txt`, `tests`. Four of them did not exist | `AUDIT.md`, `CHANGELOG.md`, `tests` now exist. The other two are dropped from the list and from CI |
| `.env.example` said nothing about the dashboard key or the MCP mode | Added |
| Authors field still names the upstream author and the license is MIT | Open: check this is what you want |

## 2. Old fork code

About 6,900 lines (31 files) came from a general internet access tool: browser and CDP control, session handling, installer and onboarding, OpenCLI and Cloak backends, channels for Twitter, Reddit, YouTube, GitHub and web reading, and transcription. They had a separate command set (`channels`, `read`, `login`, `browser`, `setup`, `doctor`) and 46 lines of Chinese text in the onboarding module. Discovery imported only three things from them: `Config`, the SSRF-safe URL helpers and an Exa search helper.

Status: removed. `Config` and `utils/paths.py` stay in English and no longer import the removed state module (the old `Config.save` would have crashed without it). Exa search now lives in `search_backends.py`. `utils/url.py` stays. `agent_reach/server` and `agent_reach/utils` gained `__init__.py` files.

## 3. CLI and entry point

| Finding | Status |
| --- | --- |
| `agent-reach` routed through a 593-line CLI for the old tool before reaching `discovery` or `mcp` | Replaced by a short router: `mcp`, `team`, `discovery`, `dashboard`, `doctor`, `version` |
| Help text, docs and code comments named commands that do not exist (`llm-check`, `search-check`) | Fixed to `check llm` and `check search` |
| README said the dashboard module is not part of the build while `server/app.py` is a complete FastAPI app | Fixed. The messages now say to install the `dashboard` extra |
| `ensure_dashboard_running` tested for `agent_reach.server`, which always exists | Fixed to test for `fastapi` and `uvicorn` |

## 4. MCP server

| Finding | Status |
| --- | --- |
| The host AI saw 31 low level tools and could do every stage itself, so nothing forced checks between stages | Company mode (default) hides the specialist tools. The host talks to 13 `ceo_*` tools plus the owner tools. `--mode full` keeps the old surface |
| Three MCP prompts (`find_customers`, `draft_reply`, `weekly_review`) | Removed. You asked for tools, not prompts |
| `reach_harvest_threads` returned a fresh item id when the thread was already stored. `reach_save_lead` then found no stored thread, could not verify the quote and the lead stayed unverified | Fixed in both tools |
| `reach_save_lead` trusts the host's sub-scores and only checks the quote | Open by design. In the team flow the verifier adds a second model opinion on high potential leads when a key is set |
| `reach_run_autonomous_batch` runs the whole loop in one call and skips the team's checks | Hidden in company mode, restricted for specialists |

## 5. Discovery engine

| Finding | Status |
| --- | --- |
| The dashboard `POST /api/settings` wrote Reddit and GitHub credentials into SQLite through `set_setting`, bypassing `save_posting_settings` that drops them. The docs say credentials are never stored | Fixed: the route uses `save_posting_settings` and reports `ignored_credentials`. Old rows are scrubbed at start |
| The same route stored the model key in the database although `.env.example` says nothing there is stored | Fixed: the key goes to the owner-only config file. An old stored key moves there at start |
| Profile facts were never checked against the crawled text | The analyst check compares features and prices with the site text or the request |
| The live "thread still open" check exists only on the Reddit API posting path. The manual hand-over path can give you a reply for a thread locked since harvest. The architecture note listed it as gate 13 of every post | Open. Recheck the thread before you post. Doc corrected to the 18 real gate codes |
| `docs/safety.md` left out the `empty` gate | Fixed |
| Quote matching lowercases and collapses whitespace only. Curly quotes or dashes in a source can make a true quote fail | Open, low risk. It fails closed |
| Model name lists in `llm_client.py` were not verifiable here | Open: run `agent-reach discovery check llm` with your key |
| Keyed search providers and API posting were never run against live accounts (the original README says so too) | Open |

## 6. Skills and scripts

| Finding | Status |
| --- | --- |
| `skills/README.md` told you to run `tests/test_examples.py`, which did not exist | Added |
| The skill validator checked `reach_*` names only | Now checks `ceo_*` too and expects 8 skills |
| No skill described the CEO flow | Added `company-operations` and its verification rules. Bumped `customer-discovery` to 1.1.0. Manifest and tool reference regenerated |

## 7. CI, Docker and docs

Missing but referenced before: `Dockerfile`, `.cursor/mcp.json`, `release.yml`, `canary.yml`, `CHANGELOG.md`, `AUDIT.md`, `constraints.txt`, `llms.txt`, `tests/`.

Added: `Dockerfile`, `.dockerignore`, `.gitignore`, `.cursor/mcp.json`, `CHANGELOG.md`, `AUDIT.md`, 50 tests. Not added: release and canary workflows, `constraints.txt`, `llms.txt`. The docs no longer describe them. The Docker job was not run (no daemon here).

## 8. Dashboard API

Existing routes are unchanged except `/api/settings`. New routes for the chat box: `POST /api/team/ask`, `GET /api/team/directives`, `GET /api/team/directives/{id}`, `POST /api/team/directives/{id}/run`, `GET /api/team/directives/{id}/report`, `POST /api/team/tasks/{id}/checkpoint`, `GET /api/team/roster`. The frontend was not part of the upload. A frontend that sends credentials to `/api/settings` will now see them ignored.

## 9. The company layer: limits

- Host mode cannot prove that the owner, and not the assistant, answered a checkpoint. The server records the words and refuses an empty answer.
- The auditor model and the lead second opinion need a provider key on the server. Without one, only the deterministic checks run. Those checks catch invented evidence ids, quotes, numbers and links. They cannot judge whether a true quote supports a weak conclusion.
- A number written as a word ("forty") is not caught by the number check.
- The company mode keeps `reach_set_voice_samples` and `reach_set_reply_preferences` visible so the owner can change them through the CEO.
