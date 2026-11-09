# Architecture

Agent Reach is a small company run through MCP tools. The owner talks to the CEO. The CEO plans, specialists work through a short list of tools, a verifier checks each output, and the owner decides what goes out.

## Layers

```
 owner
   |
 CEO ------------------ MCP server (agent_reach/mcp/server.py + team_tools.py)
   |                    CLI (agent-reach team ...)       API (/api/team/*)
   v
 TeamEngine (agent_reach/team/engine.py)
   |-- planner: intent, playbooks, tasks and dependencies
   |-- prompts: role charter + skill pack + task brief + verified inputs
   |-- toolbox: role based permissions over the verified reach_* tools
   |-- ledger:  every tool result becomes evidence (E1, E2, ...)
   |-- verifier: deterministic checks, optional auditor model
   |-- store:   directives, tasks, events (SQLite, same file as discovery)
   v
 Discovery engine (agent_reach/discovery/)
   profile, search planner, harvester, qualifier, reply generator, linter, publisher gates, storage
```

## The team

| Role | Job | Tools |
| --- | --- | --- |
| analyst | Business profile | fetch site text, save profile |
| scout | Queries and harvest | read profile, plan queries, harvest threads |
| qualifier | Score threads, save leads | read profile and items, read thread, save lead, list leads, set lead status |
| writer | Drafts in the owner's voice | read profile, list leads, reply context, lint, save reply, voice import |
| editor | Second read of every draft | read profile, replies and items, list leads, lint |
| strategist | Review results | read profile, list leads, insights, account health |
| researcher | Competitors and market | read profile, fetch site text |
| follow_up | Re-read threads after posting | read replies, list leads, read thread, set lead status |
| inspector | Posting gates for every draft (automatic, no model) | none; it runs in the engine |

The owner is a pseudo role for checkpoints. A hired specialist gets a name, a charter, skills and tools. Restricted tools are refused at hire time and again at call time.

## Life of a directive

1. `ceo_open_directive` classifies the intent (model when configured, keyword rules otherwise) and instantiates a playbook as tasks with dependencies. A confirmed profile on file lets `find_customers` skip the profile steps when the request brings no new site or description.
2. A task is `pending` until its dependencies are `done`, then `ready`. A checkpoint becomes `needs_owner`.
3. A work order (`ceo_next_work_order`, or built by the server for its own worker) holds the role prompt, the instruction, acceptance checks, verified outputs of earlier tasks, the allowed tools and the output contract.
4. Tools run through `ceo_call_tool` (or the worker loop). Each result is stored as evidence with an id.
5. `ceo_submit_result` runs the verifier. Pass: the task is `done`. Fail: the issues go back to the specialist. Three fails: the task is `escalated`, dependents are `blocked`, and the CEO retries, reassigns or skips.
6. At `confirm_profile` the owner answers. Approval confirms the profile. Rejection sends the analyst back with the owner's words.
7. `ceo_report` lists verified work, unverified work, database counts and the owner's next actions. The narrative is written from verified work. If it adds a number or a link the ledger does not hold, the report falls back to a plain template.

## Verification

Deterministic checks always run. See `skills/company-operations/references/verification-rules.md`. The auditor model (part of the verifier, not a team member) is optional and can only object to a claim that exists in the output. Qualifier outputs also get a second model opinion on high potential leads.

## Existing discovery pipeline

Unchanged in purpose. The step by step CLI (`agent-reach discovery ...`) and the orchestrator still work, and the verified `reach_*` tools are the same functions the team launches. The posting gates (`publisher.py`) have 27 codes: emergency_stop, draft_mode, not_approved, empty, platform_policy, lint, rules_not_read, rules_no_ai, rules_no_promo, rules_no_links, not_whitelisted, target_taken, thread_account, thread_cap, same_author, same_opening, thread_product, thread_gap, account_needed, account_missing, account_unknown, account_health, rules_min_karma, community_overlap, mention_ratio, daily_cap, interval.

## Where secrets live

Environment variables. Reddit and GitHub credentials and the model key are never written to the database. `~/.agent-reach/config.yaml` is an optional fallback file with owner-only permissions.
