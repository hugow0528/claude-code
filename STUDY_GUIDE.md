# Claude Code — Complete Study & Deployment Guide

> **Context**: This guide covers the leaked Claude Code source (`src/`, leaked 2026-03-31).  
> Runtime is **Bun** (not Node.js). The UI is **React + Ink** (React rendered in the terminal).

---

## Table of Contents

1. [Repository Layout](#1-repository-layout)
2. [Prerequisites](#2-prerequisites)
3. [Running the Code](#3-running-the-code)
4. [Building & Bundling](#4-building--bundling)
5. [Environment Variables Reference](#5-environment-variables-reference)
6. [Codebase Study Path](#6-codebase-study-path)
   - [Step 1 — Entry Point](#step-1--entry-point)
   - [Step 2 — Query Engine (Core LLM Loop)](#step-2--query-engine-core-llm-loop)
   - [Step 3 — Tool System](#step-3--tool-system)
   - [Step 4 — Permission System](#step-4--permission-system)
   - [Step 5 — Command System](#step-5--command-system)
   - [Step 6 — Context & System Prompt Assembly](#step-6--context--system-prompt-assembly)
   - [Step 7 — Service Layer](#step-7--service-layer)
   - [Step 8 — Multi-Agent / Swarm System](#step-8--multi-agent--swarm-system)
   - [Step 9 — IDE Bridge](#step-9--ide-bridge)
   - [Step 10 — Terminal UI Layer](#step-10--terminal-ui-layer)
7. [Prompting Theory — Key Files](#7-prompting-theory--key-files)
8. [Architecture Flow Diagram](#8-architecture-flow-diagram)
9. [Full Architecture Reference Table](#9-full-architecture-reference-table)
10. [Feature Flags Reference](#10-feature-flags-reference)
11. [Tool Reference](#11-tool-reference)
12. [Command Reference](#12-command-reference)

---

## 1. Repository Layout

```
claude-code/
├── README.md                    ← Overview of the leak and architecture
├── STUDY_GUIDE.md               ← This file
└── src/
    ├── main.tsx                 ← CLI entry point (Commander.js + React/Ink boot)
    ├── commands.ts              ← Slash command registry
    ├── tools.ts                 ← Tool registry
    ├── Tool.ts                  ← Tool base type definitions
    ├── QueryEngine.ts           ← LLM streaming loop (~46K lines, core engine)
    ├── context.ts               ← System/user context (system prompt assembly)
    ├── cost-tracker.ts          ← Token cost tracking
    ├── query.ts                 ← Entry into query pipeline
    │
    ├── commands/                ← Slash command implementations (~50 commands)
    ├── tools/                   ← Agent tool implementations (~40 tools)
    ├── components/              ← Ink UI components (~140 components)
    ├── hooks/                   ← React hooks
    ├── services/                ← External service integrations
    ├── screens/                 ← Full-screen UIs (Doctor, REPL, Resume)
    ├── types/                   ← TypeScript type definitions
    ├── utils/                   ← Utility functions
    │
    ├── bridge/                  ← IDE integration bridge (VS Code, JetBrains)
    ├── coordinator/             ← Multi-agent coordinator
    ├── plugins/                 ← Plugin system
    ├── skills/                  ← Skill system (reusable agent workflows)
    ├── keybindings/             ← Keybinding configuration
    ├── vim/                     ← Vim mode
    ├── voice/                   ← Voice input
    ├── remote/                  ← Remote sessions
    ├── server/                  ← Server mode
    ├── memdir/                  ← Memory directory (persistent CLAUDE.md memory)
    ├── tasks/                   ← Task management
    ├── state/                   ← App state management
    ├── migrations/              ← Config migrations
    ├── schemas/                 ← Config schemas (Zod v4)
    ├── entrypoints/             ← Initialization logic
    ├── query/                   ← Query pipeline stages
    ├── buddy/                   ← Companion sprite (Easter egg)
    ├── native-ts/               ← Native TypeScript utilities
    ├── outputStyles/            ← Output styling
    └── upstreamproxy/           ← Proxy configuration
```

---

## 2. Prerequisites

### Install Bun (required runtime)

```bash
# macOS / Linux
curl -fsSL https://bun.sh/install | bash

# Verify
bun --version
```

> **Important**: Do NOT use Node.js (`node`) or `ts-node`. This project is written for Bun's runtime APIs.

### Install ripgrep (required by GrepTool)

```bash
# macOS
brew install ripgrep

# Ubuntu / Debian
apt install ripgrep

# Verify
rg --version
```

### Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## 3. Running the Code

### Install dependencies

```bash
cd /path/to/claude-code
bun install
```

### Run the CLI (interactive REPL mode)

```bash
bun run src/main.tsx
```

This boots the Commander.js CLI parser and launches the React/Ink terminal REPL.

### Run with a one-shot prompt

```bash
bun run src/main.tsx "explain this codebase"
```

### Run in print mode (non-interactive, outputs to stdout)

```bash
bun run src/main.tsx --print "list all files in src/"
```

### Run in headless / API mode

```bash
bun run src/main.tsx --output-format json "summarize this project"
```

### Common startup flags

| Flag | Description |
|---|---|
| `--model <model>` | Override the Claude model (e.g. `claude-opus-4-5`) |
| `--print` / `-p` | Non-interactive single-prompt mode |
| `--output-format json` | JSON output for programmatic use |
| `--permission-mode <mode>` | `default`, `plan`, `bypassPermissions`, `auto` |
| `--no-update` | Disable auto-update check |
| `--verbose` | Verbose logging |
| `--debug` | Debug logging |

---

## 4. Building & Bundling

Claude Code uses Bun's `bun:bundle` module for dead-code elimination via **feature flags**. Inactive feature code is completely stripped at build time.

### Basic bundle

```bash
bun build src/main.tsx --outfile dist/claude-code.js
```

### Bundle with specific feature flags

```bash
bun build src/main.tsx \
  --define "feature.VOICE_MODE=false" \
  --define "feature.BRIDGE_MODE=false" \
  --define "feature.PROACTIVE=false" \
  --define "feature.DAEMON=false" \
  --outfile dist/claude-code.js
```

### Bundle for IDE bridge mode

```bash
bun build src/main.tsx \
  --define "feature.BRIDGE_MODE=true" \
  --outfile dist/claude-code-bridge.js
```

---

## 5. Environment Variables Reference

### Core

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (required unless using OAuth) |
| `ANTHROPIC_BASE_URL` | Override the API base URL |
| `ANTHROPIC_MODEL` | Override the default model |

### Behavior

| Variable | Description |
|---|---|
| `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=true` | Disable background task scheduling |
| `CLAUDE_CODE_DISABLE_SANDBOX=true` | Disable BashTool sandboxing |
| `CLAUDE_CODE_AGENT_LIST_IN_MESSAGES=true` | Inject agent list as messages (vs tool description) |
| `CLAUDE_CODE_DISABLE_TELEMETRY=true` | Disable OpenTelemetry telemetry |

### Development / Debug

| Variable | Description |
|---|---|
| `CLAUDE_DEBUG=1` | Enable debug logging |
| `CLAUDE_CODE_ENABLE_PROFILER=1` | Enable startup profiler |
| `GROWTHBOOK_OVERRIDE=<json>` | Override GrowthBook feature flags |

---

## 6. Codebase Study Path

Follow this ordered path from outside-in. Each step builds on the previous one.

---

### Step 1 — Entry Point

**Files to read:**
```
src/main.tsx
src/replLauncher.tsx
src/entrypoints/init.ts
```

**What to learn:**
- `main.tsx` uses **Commander.js** to parse CLI flags and arguments
- Before any heavy imports, it fires parallel startup side-effects:
  - `startMdmRawRead()` — reads MDM (Mobile Device Management) policy settings
  - `startKeychainPrefetch()` — prefetches macOS keychain reads (API key + OAuth token) in parallel, saving ~65ms on every startup
- `launchRepl()` boots the React/Ink REPL
- Feature flags (`feature('BRIDGE_MODE')`, etc.) gate entire subsystems using Bun's dead-code elimination

**Key pattern — parallel prefetch:**
```typescript
// Fires before heavy module imports to overlap I/O with module evaluation
startMdmRawRead()
startKeychainPrefetch()
```

---

### Step 2 — Query Engine (Core LLM Loop)

**Files to read:**
```
src/QueryEngine.ts          (~46K lines — the heart of the system)
src/query.ts                (entry into the query pipeline)
src/query/                  (pipeline stages: tokenBudget, config, deps, stopHooks)
src/cost-tracker.ts         (token cost accumulation)
```

**What to learn:**
- `QueryEngine.ts` is the most important file. It drives the entire **agentic loop**:
  1. Build the messages array (system prompt + conversation history)
  2. Call the Anthropic API with streaming
  3. If Claude returns a **tool_use** block → execute the tool → append result → loop
  4. If Claude returns a **text** block → stream to terminal → done
- Handles **thinking mode** (extended thinking tokens)
- Handles **retry logic** with exponential backoff on rate-limit / server errors
- Handles **token budget** management (stop sequences, compact triggers)
- Token costs are tracked in `cost-tracker.ts` per-session

---

### Step 3 — Tool System

**Files to read:**
```
src/Tool.ts                             ← Base type: inputSchema, permissionModel, call()
src/tools.ts                            ← Tool registry (getTools())
src/tools/BashTool/BashTool.tsx         ← Shell execution + sandboxing
src/tools/BashTool/prompt.ts            ← LLM instructions for using bash
src/tools/FileEditTool/FileEditTool.ts  ← String-replacement file editing
src/tools/FileEditTool/prompt.ts        ← LLM instructions for editing files
src/tools/AgentTool/AgentTool.tsx       ← Sub-agent spawning
src/tools/AgentTool/prompt.ts           ← LLM instructions for sub-agents
src/tools/GrepTool/                     ← ripgrep-based search
src/tools/FileReadTool/                 ← File reading (images, PDFs, notebooks)
src/tools/FileWriteTool/                ← File creation / overwrite
```

**What to learn:**

Every tool follows the same structure:
```
src/tools/<ToolName>/
  ├── <ToolName>.ts    ← Core logic: inputSchema (Zod), call(), permissionModel
  ├── prompt.ts        ← The actual LLM instructions injected into the system prompt
  ├── UI.tsx           ← Ink component for rendering tool output in the terminal
  └── utils.ts         ← Helpers
```

The `prompt.ts` files are **gold** for understanding Anthropic's prompt engineering.  
They show exactly how Claude is instructed to use each tool safely and effectively.

**BashTool security model** (study `src/tools/BashTool/bashSecurity.ts`):
- Commands are parsed into an AST
- Dangerous patterns (pipe injection, multiple `cd`, bare repo git hooks) are detected
- Sandboxing is applied per-platform

---

### Step 4 — Permission System

**Files to read:**
```
src/hooks/toolPermission/     ← Permission check hooks
src/hooks/useCanUseTool.tsx   ← React hook wrapping permission logic
src/utils/permissions/        ← Permission result types and helpers
```

**What to learn:**

Every tool call flows through the permission system before execution:

| Permission Mode | Behavior |
|---|---|
| `default` | Prompt user for approval on first use of each tool |
| `plan` | Only read-only tools allowed; writing requires approval |
| `bypassPermissions` | All tools auto-approved (dangerous, for CI/headless) |
| `auto` | Learned approvals; auto-approves previously-approved patterns |

Permission results are one of: `allow`, `deny`, `ask`.

---

### Step 5 — Command System

**Files to read:**
```
src/commands.ts               ← Command registry
src/commands/commit.ts        ← /commit: git commit with auto message
src/commands/compact/         ← /compact: context window compression
src/commands/config/          ← /config: settings management UI
src/commands/doctor/          ← /doctor: environment diagnostics
src/commands/memory/          ← /memory: persistent memory management
src/commands/mcp/             ← /mcp: MCP server management
src/commands/review/          ← /review: code review
```

**What to learn:**
- Slash commands are user-facing (`/commit`, `/review`, `/compact`, etc.)
- They are distinct from tools — commands are typed by the human, tools are called by Claude
- `commands.ts` registers all commands and conditionally loads them based on environment

---

### Step 6 — Context & System Prompt Assembly

**Files to read:**
```
src/context.ts                ← getSystemContext() + getUserContext()
src/utils/messages.ts         ← createSystemMessage() / createUserMessage()
src/memdir/memdir.ts          ← Persistent memory loading (CLAUDE.md files)
src/memdir/paths.ts           ← Memory file path resolution
```

**What to learn:**

`getSystemContext()` assembles the system prompt from:
- OS/platform information
- Current working directory and git status
- List of available tools (with their descriptions)
- Permission mode
- Feature-flag-dependent sections

`getUserContext()` adds:
- User preferences
- Contents of `CLAUDE.md` memory files (from `~/.claude/` and project root)
- Loaded skills

`memdir/` implements the **persistent memory** system:
- Claude can write to `CLAUDE.md` files to remember things across sessions
- Memory is loaded at startup and injected into the system prompt

---

### Step 7 — Service Layer

**Files to read:**
```
src/services/api/claude.ts              ← Anthropic API client, streaming
src/services/api/errors.ts             ← Retryable error categorization
src/services/api/logging.ts            ← Usage logging
src/services/mcp/                      ← Model Context Protocol server management
src/services/oauth/                    ← OAuth 2.0 authentication flow
src/services/compact/                  ← Context compression (summarization)
src/services/extractMemories/          ← Auto memory extraction from conversations
src/services/analytics/growthbook.js   ← Feature flags + A/B testing
src/services/lsp/                      ← Language Server Protocol manager
src/services/policyLimits/             ← Organization policy enforcement
```

**What to learn:**
- `claude.ts` wraps the Anthropic SDK with retry logic, streaming, and cost tracking
- `mcp/` connects to MCP (Model Context Protocol) servers — external tool providers
- `compact/` uses a secondary LLM call to summarize the conversation when context gets too long
- `extractMemories/` uses an LLM call to extract and persist memorable facts from the conversation

---

### Step 8 — Multi-Agent / Swarm System

**Files to read:**
```
src/coordinator/coordinatorMode.ts        ← Multi-agent orchestration
src/tools/AgentTool/AgentTool.tsx         ← Sub-agent spawning
src/tools/AgentTool/runAgent.ts           ← Sub-agent execution loop
src/tools/AgentTool/forkSubagent.ts       ← Fork-based sub-agent spawning
src/tools/AgentTool/loadAgentsDir.ts      ← Load agent definitions from disk
src/tools/AgentTool/builtInAgents.ts      ← Built-in agent types
src/tools/SendMessageTool/               ← Inter-agent messaging
src/tools/TaskCreateTool/               ← Task creation for agents
src/tools/TaskUpdateTool/               ← Task status updates
src/utils/swarm/                         ← Swarm connection utilities
```

**What to learn:**

Claude Code supports **agent swarms**:
- The main Claude instance can spawn sub-agents via `AgentTool`
- Sub-agents are full Claude instances with their own tool access and conversation history
- `TeamCreateTool` enables **parallel** team-level work (multiple agents on the same task)
- `SendMessageTool` provides inter-agent messaging
- The `coordinator/` module handles orchestration when `COORDINATOR_MODE` is enabled

---

### Step 9 — IDE Bridge

**Files to read:**
```
src/bridge/bridgeMain.ts              ← Bridge main loop
src/bridge/bridgeMessaging.ts         ← Message protocol
src/bridge/bridgePermissionCallbacks.ts ← Permission callbacks from IDE
src/bridge/replBridge.ts             ← REPL session bridge
src/bridge/jwtUtils.ts               ← JWT-based authentication
src/bridge/sessionRunner.ts          ← Session execution in bridge mode
```

**What to learn:**
- The bridge connects VS Code / JetBrains IDE extensions to the Claude Code CLI
- Communication is bidirectional over a local socket
- JWT tokens authenticate the IDE extension to the CLI process
- The IDE can send file context, selections, and diagnostics to Claude

---

### Step 10 — Terminal UI Layer

**Files to read:**
```
src/screens/                       ← Full-screen UIs (REPL, Doctor, Resume)
src/components/                    ← Shared Ink components (~140 files)
src/hooks/useTextInput.ts          ← Text input with history and typeahead
src/hooks/useVimInput.ts           ← Vim mode input handling
src/hooks/useGlobalKeybindings.tsx ← Global keyboard shortcuts
src/ink.ts                         ← Ink renderer wrapper
src/replLauncher.tsx               ← REPL launcher (mounts the root React component)
```

**What to learn:**
- All UI is built with **React + Ink** — React components that render to terminal escape codes
- Each tool has a `UI.tsx` component that renders its output in the terminal
- The REPL screen composes these components into the full interactive interface
- Vim mode, keybindings, and history are all implemented as React hooks

---

## 7. Prompting Theory — Key Files

These files are the most instructive for learning how Anthropic engineers prompts for agentic tasks:

| File | Topic |
|---|---|
| `src/tools/BashTool/prompt.ts` | Safe shell execution instructions, timeout handling, background tasks |
| `src/tools/FileEditTool/prompt.ts` | Precise string-replacement instructions, avoiding common mistakes |
| `src/tools/AgentTool/prompt.ts` | When/how to delegate to sub-agents, task decomposition |
| `src/tools/GrepTool/prompt.ts` | Code search strategies, ripgrep usage |
| `src/tools/FileReadTool/prompt.ts` | File reading strategy, handling large files |
| `src/context.ts` | Full system prompt construction — see `getSystemContext()` |
| `src/utils/messages.ts` | `createSystemMessage()` / `createUserMessage()` patterns |
| `src/memdir/memdir.ts` | How CLAUDE.md memory is injected into context |
| `src/services/compact/` | Summarization prompts for context compression |
| `src/services/extractMemories/` | Prompts for auto-extracting memorable facts |

**What makes these valuable:**  
Each `prompt.ts` file contains the *actual instructions* that tell Claude how to use a given tool — when to use it, common pitfalls to avoid, safety constraints, and output formatting. These represent Anthropic's production-grade prompt engineering patterns.

---

## 8. Architecture Flow Diagram

```
User types a prompt in the terminal
             │
             ▼
    src/main.tsx
    (Commander.js parses CLI flags)
             │
             ▼
    src/replLauncher.tsx
    (React/Ink REPL mounts)
             │
             ▼
    src/QueryEngine.ts  ◄─────────────────────────────────┐
    (LLM streaming loop)                                   │
             │                                             │
             ├── src/context.ts                            │
             │   (build system prompt)                     │
             │                                             │
             ├── src/services/api/claude.ts                │
             │   (call Anthropic API with streaming)       │
             │                                             │
             ▼                                             │
    Claude returns tool_use block?                         │
             │                                             │
    YES ─────┤                                             │
             ▼                                             │
    src/hooks/toolPermission/                              │
    (check permission: allow / deny / ask)                 │
             │                                             │
    ALLOW ───┤                                             │
             ▼                                             │
    src/tools/<ToolName>/                                  │
    (execute: Bash, FileEdit, Agent, Grep, etc.)           │
             │                                             │
             └─── append tool result to messages ──────────┘
                  (loop back to QueryEngine)

    NO tool_use (text response) ─────────────────────────────►
    src/components/ + src/screens/
    (Ink renders streaming text to terminal)
```

---

## 9. Full Architecture Reference Table

| Layer | Path | Role |
|---|---|---|
| **Entry** | `src/main.tsx` | CLI parsing, startup optimizations |
| **REPL** | `src/replLauncher.tsx` | Terminal UI boot and React root mount |
| **LLM Engine** | `src/QueryEngine.ts` | Streaming API calls + tool-call loop |
| **Query Pipeline** | `src/query.ts`, `src/query/` | Pipeline stages (budget, config, deps) |
| **Tools** | `src/tools/` | What Claude can *do* (40+ tools) |
| **Tool Registry** | `src/tools.ts` | Loads and registers all tools |
| **Tool Base Types** | `src/Tool.ts` | inputSchema, permissionModel, call() |
| **Commands** | `src/commands/` | What the *user* can type (50+ slash commands) |
| **Command Registry** | `src/commands.ts` | Loads and registers all commands |
| **Context** | `src/context.ts` | System prompt assembly |
| **Memory** | `src/memdir/` | Persistent memory (CLAUDE.md files) |
| **Permissions** | `src/hooks/toolPermission/` | Safety gate on every tool call |
| **Hooks** | `src/hooks/` | React hooks for all interactive features |
| **API Client** | `src/services/api/` | Anthropic HTTP client, streaming, retry |
| **MCP** | `src/services/mcp/` | Model Context Protocol server connections |
| **OAuth** | `src/services/oauth/` | OAuth 2.0 authentication |
| **Compact** | `src/services/compact/` | Context window compression |
| **Memory Extract** | `src/services/extractMemories/` | Auto-extract memories from conversations |
| **Feature Flags** | `src/services/analytics/` | GrowthBook A/B testing + feature flags |
| **LSP** | `src/services/lsp/` | Language Server Protocol manager |
| **Bridge** | `src/bridge/` | VS Code / JetBrains IDE integration |
| **Multi-agent** | `src/coordinator/`, `src/tools/AgentTool/` | Agent swarms + orchestration |
| **Skills** | `src/skills/` | Reusable agent workflows |
| **Plugins** | `src/plugins/` | Plugin loading system |
| **UI Components** | `src/components/` | Ink terminal UI components |
| **Screens** | `src/screens/` | Full-screen UIs (REPL, Doctor, Resume) |
| **State** | `src/state/` | App state management |
| **Config** | `src/schemas/`, `src/utils/config.ts` | Settings + Zod validation |
| **Cost** | `src/cost-tracker.ts` | Token usage and cost tracking |
| **Keybindings** | `src/keybindings/` | Keyboard shortcut configuration |
| **Vim** | `src/vim/` | Vim mode implementation |
| **Voice** | `src/voice/` | Voice input (gated behind `VOICE_MODE` flag) |
| **Remote** | `src/remote/` | Remote session support |
| **Server** | `src/server/` | Server mode |
| **Tasks** | `src/tasks/` | Task management system |
| **Migrations** | `src/migrations/` | Config migration logic |
| **Utils** | `src/utils/` | Shared utilities |

---

## 10. Feature Flags Reference

Feature flags are evaluated at **build time** using Bun's `bun:bundle`. Code behind a `false` flag is completely removed from the bundle.

```typescript
import { feature } from 'bun:bundle'

const voiceModule = feature('VOICE_MODE')
  ? require('./commands/voice/index.js')
  : null
```

| Flag | Description |
|---|---|
| `PROACTIVE` | Proactive background agent (monitors and acts without prompting) |
| `KAIROS` | Assistant mode (alternative interaction model) |
| `BRIDGE_MODE` | VS Code / JetBrains IDE bridge |
| `DAEMON` | Background daemon process |
| `VOICE_MODE` | Voice input support |
| `AGENT_TRIGGERS` | Scheduled cron and remote triggers |
| `COORDINATOR_MODE` | Multi-agent coordinator orchestration |
| `MONITOR_TOOL` | Monitoring tool |

---

## 11. Tool Reference

| Tool | Path | Description |
|---|---|---|
| `BashTool` | `src/tools/BashTool/` | Shell command execution with sandboxing |
| `FileReadTool` | `src/tools/FileReadTool/` | File reading (text, images, PDFs, notebooks) |
| `FileWriteTool` | `src/tools/FileWriteTool/` | File creation / overwrite |
| `FileEditTool` | `src/tools/FileEditTool/` | Partial file modification (string replacement) |
| `GlobTool` | `src/tools/GlobTool/` | File pattern matching search |
| `GrepTool` | `src/tools/GrepTool/` | ripgrep-based content search |
| `WebFetchTool` | `src/tools/WebFetchTool/` | Fetch and parse URL content |
| `WebSearchTool` | `src/tools/WebSearchTool/` | Web search |
| `AgentTool` | `src/tools/AgentTool/` | Spawn a sub-agent |
| `SkillTool` | `src/tools/SkillTool/` | Execute a saved skill workflow |
| `MCPTool` | `src/tools/MCPTool/` | Invoke a tool from an MCP server |
| `LSPTool` | `src/tools/LSPTool/` | Language Server Protocol queries |
| `NotebookEditTool` | `src/tools/NotebookEditTool/` | Jupyter notebook editing |
| `TaskCreateTool` | `src/tools/TaskCreateTool/` | Create a task for an agent |
| `TaskUpdateTool` | `src/tools/TaskUpdateTool/` | Update task status |
| `SendMessageTool` | `src/tools/SendMessageTool/` | Send a message to another agent |
| `EnterPlanModeTool` | `src/tools/EnterPlanModeTool/` | Switch to plan-only mode |
| `ExitPlanModeTool` | `src/tools/ExitPlanModeTool/` | Exit plan mode |
| `EnterWorktreeTool` | `src/tools/EnterWorktreeTool/` | Enter git worktree isolation |
| `ExitWorktreeTool` | `src/tools/ExitWorktreeTool/` | Exit git worktree |
| `SyntheticOutputTool` | `src/tools/SyntheticOutputTool/` | Structured output generation |
| `SleepTool` | `src/tools/SleepTool/` | Wait (for proactive mode) |
| `RemoteTriggerTool` | `src/tools/RemoteTriggerTool/` | Fire a remote trigger |
| `ScheduleCronTool` | `src/tools/ScheduleCronTool/` | Create a scheduled cron trigger |

---

## 12. Command Reference

Slash commands are typed by the user with a `/` prefix in the REPL.

| Command | Path | Description |
|---|---|---|
| `/commit` | `src/commands/commit.ts` | Create a git commit with auto-generated message |
| `/review` | `src/commands/review/` | AI code review |
| `/compact` | `src/commands/compact/` | Compress context window |
| `/mcp` | `src/commands/mcp/` | MCP server management |
| `/config` | `src/commands/config/` | Settings management UI |
| `/doctor` | `src/commands/doctor/` | Environment diagnostics |
| `/login` | `src/commands/login/` | Authenticate with Anthropic |
| `/logout` | `src/commands/logout/` | Sign out |
| `/memory` | `src/commands/memory/` | Persistent memory management |
| `/skills` | `src/commands/skills/` | Skill management |
| `/tasks` | `src/commands/tasks/` | Task management |
| `/vim` | `src/commands/vim/` | Toggle Vim mode |
| `/diff` | `src/commands/diff/` | View file changes |
| `/cost` | `src/commands/cost/` | Show token usage and cost |
| `/theme` | `src/commands/theme/` | Change terminal theme |
| `/context` | `src/commands/context/` | Context window visualization |
| `/pr_comments` | `src/commands/pr_comments/` | View GitHub PR review comments |
| `/resume` | `src/commands/resume/` | Restore a previous session |
| `/share` | `src/commands/share/` | Share current session |
| `/desktop` | `src/commands/desktop/` | Handoff to desktop app |
| `/mobile` | `src/commands/mobile/` | Handoff to mobile app |

---

*This guide covers the leaked Claude Code source from 2026-03-31. All original source code is the property of [Anthropic](https://www.anthropic.com).*
