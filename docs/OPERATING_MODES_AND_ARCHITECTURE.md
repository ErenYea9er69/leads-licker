# Agent Reach: Architecture & Multi-Mode Operating Guide

Agent Reach is an enterprise-grade AI customer discovery and lead intelligence platform. It systematically finds prospective customers in public communities (Reddit, Hacker News, GitHub, X, Quora, and the open web) who have problems your product solves, scores buying intent with explainable rubrics, and drafts verified, honest replies in your voice that adhere strictly to platform policies.

---

## 1. System Architecture

All user interfaces, automated platforms, and AI clients interact with a unified, shared core backend. Business logic, scoring rubrics, evidence ledgers, and posting policies are defined once and executed identically across all interfaces.

```mermaid
flowchart TD
    subgraph UI["1. USER INTERFACES"]
        WebApp["Mode A: Standalone Web App\n(React 19 + TypeScript)"]
        ExternalAPI["Mode B: Standalone API Client\n(cURL / SDK / Automations)"]
        ClaudeDesktop["Mode E: Claude Desktop\n(Local stdio MCP)"]
        ClaudeWeb["Mode F: Claude Web\n(Remote SSE MCP)"]
        ClaudeCode["Mode G: Claude Code / CLI\n(stdio MCP / Terminal)"]
        OtherMCP["Mode H: Cursor / Windsurf\n(Local stdio MCP)"]
    end

    subgraph IntegrationLayer["2. INTEGRATION LAYER"]
        FastAPIApp["FastAPI Server (:8000)\n(/api/* & /mcp)"]
        SPARouter["SPA Static Mount\n(HTML5 Fallback)"]
        MCPSSE["FastMCP SSE Engine\n(/mcp/sse)"]
        MCPStdio["MCP Stdio Driver\n(agent-reach mcp)"]
        SecurityMiddleware["API Security Middleware\n(Bearer / X-API-Key / Loopback)"]
    end

    subgraph SharedCore["3. SHARED CORE BACKEND SERVICES"]
        BusinessEngine["Business Engine\n(ICP, Pain Vocabulary, Profile)"]
        SearchPlanner["Search Planner & Harvester\n(Reddit, HN, GitHub, X, Web)"]
        LeadQualifier["Lead Qualifier\n(5-Part Rubric & Scoring)"]
        ReplyGenerator["Reply Generator & Linter\n(Value-First & Product-Aware)"]
        TeamEngine["Team & Directive Engine\n(CEO + 9 Specialist Roles)"]
        Verifier["Evidence Verifier\n(Quotes, Numbers, Gate Check)"]
        AccountService["Account & Voice Service\n(Health, Karma, Style Match)"]
    end

    subgraph DataLayer["4. DATA LAYER"]
        SQLiteDB[("SQLite Storage (WAL Mode)\nProfiles, Leads, Campaigns, Directives")]
        OnlineBackup[("Online Atomic Backup Engine\n(src_conn.backup)")]
    end

    WebApp --> SPARouter --> FastAPIApp
    ExternalAPI --> SecurityMiddleware --> FastAPIApp
    ClaudeWeb --> SecurityMiddleware --> MCPSSE --> FastAPIApp
    FastAPIApp --> SharedCore
    ClaudeDesktop --> MCPStdio --> SharedCore
    ClaudeCode --> MCPStdio --> SharedCore
    OtherMCP --> MCPStdio --> SharedCore

    SharedCore --> SQLiteDB
    SQLiteDB --> OnlineBackup
```

---

## 2. All 8 Operating Modes (Detailed Execution Guide)

### Mode A: Standalone Web Application
* **Purpose:** A complete, standalone SaaS dashboard for founders and marketing teams without requiring Claude or any external AI host.
* **Architecture:**
  - Frontend: React 19, TypeScript, Lucide Icons, Vite SPA.
  - Backend: FastAPI serving `/api/*` and mounting `/` to `frontend/dist`.
  - Database: Local SQLite in WAL mode.
* **How to run:**
  ```bash
  agent-reach dashboard --host 127.0.0.1 --port 8000
  ```
  Open `http://localhost:8000` in your browser. All tabs (Overview, CEO & Squad, Business Profile, Discovery Engine, Leads Inbox, Reply Studio, Customer Insights, Settings) function end-to-end.

---

### Mode B: Standalone Backend and API
* **Purpose:** Headless operation for custom integrations, automation scripts, CI/CD pipelines, and external developers.
* **Architecture:**
  - Full REST API with automatic OpenAPI documentation.
  - System diagnostics and liveness probes.
* **Endpoints:**
  - `GET /api/health`: System health and SQLite database connectivity status.
  - `GET /api/system/status`: Complete diagnostics (LLM provider, lead counts, account stats).
  - `GET /docs`: Interactive Swagger UI.
  - `GET /openapi.json`: OpenAPI 3.x specification.
  - `GET /api/leads`: Query qualified leads with filtering, scoring, and pagination.
  - `POST /api/team/ask`: Submit natural-language requests to the autonomous CEO.
  - `GET /api/export`: Export lead intelligence in JSON or CSV format.
* **How to run:**
  ```bash
  uvicorn agent_reach.server.app:app --host 0.0.0.0 --port 8000
  ```

---

### Mode C: Standalone MCP Server
* **Purpose:** Expose the application's actual lead discovery and qualification capabilities directly to any MCP-compliant client without opening or running the web frontend.
* **Architecture:**
  - Standalone FastMCP server running over `stdio` or dedicated network transport (`sse`, `streamable-http`).
  - Accesses the shared `DiscoveryStorage` and domain orchestrators directly.
* **How to run:**
  ```bash
  # Local stdio (default)
  agent-reach mcp

  # Network SSE server on dedicated port
  agent-reach mcp --transport sse --host 127.0.0.1 --port 8001
  ```

---

### Mode D: Web Application + MCP (Synchronized)
* **Purpose:** Users run the standalone web application while connecting an AI assistant (Claude, Cursor) to the same backend.
* **Architecture:**
  - The web application and MCP server concurrently access the same SQLite database file (`~/.agent-reach/discovery.db`).
  - SQLite WAL (Write-Ahead Logging) ensures concurrent reader/writer operations without locking contention.
  - Actions performed by the AI client (e.g. creating directives, qualifying leads) immediately appear in the dashboard upon refresh.

---

### Mode E: Claude Desktop + MCP
* **Purpose:** Drive customer discovery and review directly within Claude Desktop on macOS or Windows.
* **Configuration:**
  Run the configuration generator to produce the exact JSON for your system:
  ```bash
  agent-reach mcp config claude-desktop
  ```
  Add the output to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):
  ```json
  {
    "mcpServers": {
      "agent-reach": {
        "command": "agent-reach",
        "args": ["mcp"]
      }
    }
  }
  ```

---

### Mode F: Claude Web + Remote MCP
* **Purpose:** Connect Claude Web (claude.ai) or remote AI agents to a cloud-hosted Agent Reach instance.
* **Architecture:**
  - FastAPI server mounts the MCP SSE engine at `/mcp/sse`.
  - Protected by `api_security_middleware` requiring `AGENT_REACH_API_KEY` or `MCP_AUTH_TOKEN`.
* **Configuration:**
  1. Set your security key on the host:
     ```bash
     export AGENT_REACH_API_KEY="your-secure-random-token"
     ```
  2. In Claude Web or remote MCP configuration, point to:
     ```json
     {
       "mcpServers": {
         "agent-reach-remote": {
           "url": "https://your-domain.com/mcp/sse",
           "transport": "sse",
           "headers": {
             "Authorization": "Bearer your-secure-random-token"
           }
         }
       }
     }
     ```

---

### Mode G: Claude Code / CLI + MCP
* **Purpose:** Command-line development and automation via Claude Code.
* **Registration:**
  ```bash
  agent-reach mcp config claude-code
  # Outputs:
  claude mcp add agent-reach -- agent-reach mcp
  ```
  Or talk directly to the CEO via the built-in terminal team CLI:
  ```bash
  agent-reach team ask "Find customers for https://my-product.com"
  agent-reach team status
  agent-reach team report DIRECTIVE_ID
  ```

---

### Mode H: Other MCP Clients (Cursor, Windsurf, Antigravity)
* **Cursor:** Add to `.cursor/mcp.json`:
  ```json
  {
    "mcpServers": {
      "agent-reach": {
        "command": "agent-reach",
        "args": ["mcp"]
      }
    }
  }
  ```
* **Windsurf:** Add to `~/.codeium/windsurf/mcp_config.json`:
  ```json
  {
    "mcpServers": {
      "agent-reach": {
        "command": "agent-reach",
        "args": ["mcp"]
      }
    }
  }
  ```

---

## 3. Final Compatibility Matrix

| Capability | Web App (Mode A) | Headless API (Mode B) | Standalone MCP (Mode C) | Claude Desktop (Mode E) | Claude Web (Mode F) | Claude Code / CLI (Mode G) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Business Profile Management** | Yes | Yes | Yes | Yes | Yes | Yes |
| **Public Thread Harvesting** | Yes | Yes | Yes | Yes | Yes | Yes |
| **5-Part Rubric Lead Scoring** | Yes | Yes | Yes | Yes | Yes | Yes |
| **Value-First & Product-Aware Reply Drafting** | Yes | Yes | Yes | Yes | Yes | Yes |
| **Real-time Safety Linter & Rule Checks** | Yes | Yes | Yes | Yes | Yes | Yes |
| **CEO Directive Delegation & Specialist Squad** | Yes | Yes | Yes | Yes | Yes | Yes |
| **Human Approval Checkpoints** | Yes | Yes | Yes | Yes | Yes | Yes |
| **Account Health & Karma Inspection** | Yes | Yes | Yes | Yes | Yes | Yes |
| **Data Export (JSON / CSV)** | Yes | Yes | Yes | Yes | Yes | Yes |
| **Online Atomic Database Backup** | Via Storage | Via Storage | Via Storage | Via Storage | Via Storage | Via Storage |
| **Network Transport** | HTTP / WS | HTTP / REST | Stdio / SSE | Local Stdio | HTTPS / SSE | Local Stdio |
| **Authentication Requirement** | Loopback / Session | Optional Key | None (Local) | None (Local) | Bearer Token | None (Local) |

---

## 4. Security, Secrets Management, and Multi-Tenant Isolation

1. **No Stored Passwords or Tokens:**
   - Agent Reach **never** stores platform passwords or authorization cookies in SQLite.
   - API keys for optional automated posting (Reddit client credentials, GitHub tokens) and LLM providers are read strictly from host environment variables (`.env`).
2. **Access Control & Network Boundaries:**
   - By default, unauthenticated requests are restricted strictly to loopback interfaces (`127.0.0.1`, `::1`, `localhost`).
   - When binding to `0.0.0.0` or hosting remotely, `AGENT_REACH_API_KEY` is enforced across all `/api/*` and `/mcp` endpoints using constant-time HMAC comparison (`hmac.compare_digest`).
3. **Data Integrity & Storage:**
   - Multi-process concurrency is safeguarded by SQLite WAL mode and PRAGMA busy timeouts.
   - Database files are created with private file permissions (`0o600`).
   - Online atomic backups (`DiscoveryStorage.backup`) allow snapshots during active background tasks without locking errors.

---

## 5. Deployment Options & Infrastructure

### Local Deployment
```bash
git clone https://github.com/your-org/agent-reach.git
cd agent-reach
python -m pip install -e ".[dashboard,dev]"
cd frontend && npm install && npm run build && cd ..
agent-reach dashboard
```

### Docker Deployment
Use the included [`Dockerfile`](file:///c:/Users/hp/Desktop/Agent-Reach/Dockerfile):
```bash
docker build -t agent-reach .
docker run -d -p 8000:8000 \
  -e AGENT_REACH_API_KEY="your-secret-api-key" \
  -e GROQ_API_KEY="your-groq-key" \
  -v agent_reach_data:/root/.agent-reach \
  agent-reach
```
- Web Application: `http://your-server:8000`
- REST API Documentation: `http://your-server:8000/docs`
- Remote MCP Endpoint: `http://your-server:8000/mcp/sse` (pass `Authorization: Bearer <key>`)

