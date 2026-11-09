# MCP setup

The MCP server runs over stdio. Your host AI is the CEO. The owner talks to it, and it runs the team through MCP tools. The server fetches public pages, stores results, keeps the evidence ledger, verifies every specialist output, checks scores and writing, and gates posting. You need no model key for it. With a key, the specialists run on the server's model.

## Install

```
pip install agent-reach          # or: pip install .  from a checkout
agent-reach mcp --help
```

The server needs the MCP Python SDK in the range `>=1.27,<3`. Both the 1.x and 2.x lines are tested in CI. The package declares the range, so pip picks a working version.

To run it without installing, use the container:

```
docker build -t agent-reach .
docker run -i --rm -v reach-data:/data agent-reach mcp
```

## Client configuration

Every client takes the same entry. Use `agent-reach` when it is on your PATH, or the full path to the executable.

```json
{
  "mcpServers": {
    "agent-reach": {
      "command": "agent-reach",
      "args": ["mcp"],
      "env": { "AGENT_REACH_DISCOVERY_DB": "/home/you/.agent-reach/discovery.db" }
    }
  }
}
```

Where to put it:

| Client | Location |
| --- | --- |
| Claude Code | `claude mcp add agent-reach -- agent-reach mcp`, or `.mcp.json` in the project |
| Cursor | `.cursor/mcp.json` in the project, or `~/.cursor/mcp.json` |
| VS Code | `.vscode/mcp.json` (use the key `servers` instead of `mcpServers`) |
| Claude Desktop | `claude_desktop_config.json` (Settings, Developer, Edit Config) |
| Antigravity | `~/.gemini/antigravity/mcp_config.json`, or Agent Panel, Manage MCP Servers |

The repository ships `.mcp.json` and `.cursor/mcp.json` with this entry.

Optional environment values go in the `env` block: `SERPER_API_KEY`, `BRAVE_API_KEY` or `TAVILY_API_KEY` for better search, and a model key only if you want the server's own `reach_analyze_business` or batch qualification to use a model. See `.env.example`.

## Modes

| Mode | Command | What the host sees |
| --- | --- | --- |
| company (default) | `agent-reach mcp` | The 16 `ceo_*` tools and the owner tools: status, approve, publish, confirm, accounts, rules, settings, preferences, export, voice samples, leads, skills. Specialist tools stay inside the team. |
| full | `agent-reach mcp --mode full` or `AGENT_REACH_MCP_MODE=full` | Every tool, including the specialist tools. Use it to run the stages yourself or to debug. |

The server registers no MCP prompts. The skills are also published as read-only resources (`skill://NAME`) and through `reach_get_skill`.

## Accounts and keys

Link as many accounts as you own on each platform with `reach_link_account` (handle, optional alias, optional communities where that account is preferred). Ask "which tokens do I need" and the assistant calls `reach_connections`: it lists per source what works with no setup, which variables are set or missing (names only), and what each linked account needs. An account with alias `alt1` on Reddit reads `REDDIT_ALT1_CLIENT_ID`, `REDDIT_ALT1_CLIENT_SECRET`, `REDDIT_ALT1_USERNAME` and `REDDIT_ALT1_PASSWORD`. Set them in the `env` block of the MCP server entry and restart the client. Nothing is stored in the database.

## First conversation

New project: tell the assistant about your product and your customers. It calls `ceo_intake`, asks one or two questions at a time, and starts the search by itself once it knows the product and the target users. The search runs in the background while you answer the other questions (accounts, voice, language, rules). The plan you start afterwards finds those threads waiting.

Existing project, or you prefer to start with a site. Tell the assistant: "Use Agent Reach to find customers for https://your-site.com." It should:

1. read the `company-operations` skill with `reach_get_skill` and call `ceo_open_directive` with your words (the answer lists what the company lacks);
   from then on, call `ceo_next_step` after every action and do what it says;
2. with a server model: let the team run until the profile checkpoint. Without one: play the analyst through `ceo_next_work_order`, `ceo_call_tool` and `ceo_submit_result`;
3. show you the saved profile and ask you to confirm it, then record your answer with `ceo_resolve_checkpoint`;
4. continue through search, qualification, drafting, the gate check and the audit;
5. call `ceo_report` and tell you what passed, what did not and what you must do next.

## Tools

`skills/customer-discovery/references/tool-reference.md` lists all 50 tools with their arguments. It is generated from the server, and CI fails when it is stale. The groups are:

- CEO: `ceo_intake`, `ceo_open_directive`, `ceo_status`, `ceo_run`, `ceo_next_work_order`, `ceo_call_tool`, `ceo_submit_result`, `ceo_resolve_checkpoint`, `ceo_create_task`, `ceo_update_task`, `ceo_hire_specialist`, `ceo_create_playbook`, `ceo_list_team`, `ceo_report`, `ceo_next_step`, `ceo_cancel_directive`, `ceo_memory`
- State and skills: `reach_status`, `reach_list_skills`, `reach_get_skill`
- Profile (specialist): `reach_fetch_site_text`, `reach_analyze_business`, `reach_get_or_create_profile`
- Search (specialist): `reach_plan_queries`, `reach_harvest_threads`, `reach_read_thread`
- Leads: `reach_save_lead`, `reach_list_leads`, `reach_set_lead_status`, `reach_run_autonomous_batch`
- Replies: `reach_get_reply_context`, `reach_lint_reply`, `reach_save_reply`, `reach_approve_reply`
- Posting (owner): `reach_publish_reply`, `reach_confirm_posted`
- Owner setup: `reach_connections`, `reach_list_accounts`, `reach_link_account`, `reach_account_health`, `reach_unlink_account`, `reach_import_voice_from_account`, `reach_set_voice_samples`, `reach_set_reply_preferences`, `reach_set_community_rules`
- Settings and output: `reach_get_settings`, `reach_update_settings`, `reach_export_results`, `reach_get_insights`, `reach_control_dashboard`

Each tool carries annotations: read only, writes locally, or reads public pages and writes locally. Clients that honor them can ask before the second and third kind. Specialists use only the tools their role lists. `ceo_list_team` shows each role and its tools.

## What protects you

- Specialist output counts only after the verifier accepts it. It checks evidence ids, verbatim quotes, numbers, links, scores, linter results and gate codes. See `skills/company-operations/references/verification-rules.md`.
- A specialist cannot hold `reach_publish_reply`, `reach_approve_reply`, `reach_confirm_posted`, `reach_update_settings`, account tools or community rule tools. The server refuses them even for a hired specialist.
- A checkpoint needs the owner's own words. An empty answer is refused.
- Thread text, comments and pages come back wrapped as untrusted, with `injection_flags`. Skip flagged items.
- `reach_save_lead` takes sub-scores, not a class. The server caps each score, looks for your evidence quote in the stored thread and sets the class. An unverified quote cannot reach high potential.
- `reach_save_reply` runs the linter and refuses a draft with errors. The issues come back as a list to fix.
- `reach_publish_reply` runs every gate. In manual mode it returns text and a link. A reply counts as posted only after `reach_confirm_posted`.
- `reach_export_results` writes only under the current folder, your home folder or the temp folder.
- `reach_update_settings` with `emergency_stop` stops all posting at once.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ModuleNotFoundError: mcp.server.fastmcp` in an older install | The SDK is 2.x. Upgrade this package. The new server picks the right import. |
| A specialist tool such as `reach_harvest_threads` is missing | Company mode hides specialist tools from the host. Use `ceo_open_directive`, or start with `--mode full`. |
| Client shows no tools | Run `agent-reach mcp` in a terminal. It should wait silently for input. Check the path to `agent-reach`. |
| `reach_harvest_threads` returns few items | Run `agent-reach discovery check search`. Without a keyed backend the app uses Exa and DuckDuckGo, which rate limit. |
| `rules_not_read` when publishing | Record the community's rules with `reach_set_community_rules`. |
| `account_unknown` | Link the account with `reach_link_account`, or turn off `require_account_health` knowingly. |
