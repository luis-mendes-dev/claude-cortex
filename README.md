<p align="center">
  <h1 align="center">Cortex</h1>
  <p align="center"><strong>Self-learning system for Claude Code.</strong></p>
  <p align="center">The first plugin to close the full learning loop.</p>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Commands-3-purple.svg" alt="Commands">
  <img src="https://img.shields.io/badge/Hooks-2-orange.svg" alt="Hooks">
  <img src="https://img.shields.io/badge/Built_for-Claude_Code-blueviolet.svg" alt="Built for Claude Code">
  <img src="https://img.shields.io/badge/Zero-Manual_Steps-brightgreen.svg" alt="Zero Manual Steps">
</p>

---

## Why This Exists

Every Claude Code session produces valuable learnings -- corrections you make, patterns that work, gotchas you hit, decisions you explain. But those learnings vanish when the session ends. Next time, Claude makes the same mistakes. You correct it again. The cycle repeats.

Cortex breaks that cycle. It captures what you teach Claude Code and makes it permanent. Corrections, patterns, decisions, and mistakes are extracted from every session, compiled into scored knowledge, and promoted into your CLAUDE.md rules and skill files automatically. Patterns you stop using decay and retire. Everything runs in the background with zero manual steps after setup.

No other tool in the Claude Code ecosystem closes the full loop: **capture -> compile -> promote -> decay**.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Getting Started](#getting-started)
- [Commands](#commands)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Data Storage](#data-storage)
- [How It Compares](#how-it-compares)
- [Customization](#customization)
- [Requirements](#requirements)
- [Uninstall](#uninstall)
- [License](#license)

---

## How It Works

Cortex runs a 5-stage pipeline. Every stage is automatic.

```
SESSION ENDS ──> Haiku extracts learnings ──> daily/YYYY-MM-DD-project.md
                                                       |
DAILY 2am ─────> Sweep missed sessions    ──> (catches terminal-close cases)
               > Deduplicate & score      ──> knowledge/use-guard-clauses.md
                                                       |
WEEKLY Sun 3am > Promote high-confidence  ──> ~/.claude/CLAUDE.md (## Learned Rules)
                                           ──> ~/.claude/rules/cortex-learned-*.md
               > Decay stale patterns     ──> rules/retired/
                                                       |
SESSION STARTS > Inject top 10 patterns   ──> Claude sees them automatically
```

### Stage 1: Capture

When a Claude Code session ends, Cortex sends the transcript to Haiku and extracts 5 types of learnings:

| Type | What it captures |
|------|-----------------|
| **Corrections** | When you said "no" or "wrong" and Claude changed approach |
| **Decisions** | Explicit choices between alternatives with rationale |
| **Gotchas** | Something unexpected that caused a retry or failure |
| **Patterns** | Workflows that worked well and were repeated |
| **Mistakes** | Things Claude did wrong that had to be fixed |

**Cost:** ~$0.01-0.03 per session. Falls back to regex if Haiku is unavailable.

**Missed sessions:** If you close the terminal instead of exiting gracefully (Ctrl+C, `/exit`), the SessionEnd hook may not fire. No data is lost -- the daily compile job sweeps for uncaptured sessions from the last 7 days and extracts their learnings retroactively.

### Stage 2: Compile

Runs daily at 2am. Merges daily extractions into deduplicated knowledge articles. Each article gets a confidence score:

```
confidence = min(1.0, (observations x 0.15) + (sessions x 0.20) + recency_bonus)
```

- 1 observation, 1 session: **0.45** (won't promote)
- 3 observations, 3 sessions: **1.0** (will promote)
- Same pattern in 2+ projects: tagged as **universal**

### Stage 3: Promote

Runs weekly, Sunday 3am. High-confidence patterns graduate to permanent configuration:

- **Single patterns** (confidence >= 0.85, 3+ sessions) become rules in `~/.claude/CLAUDE.md` under `## Learned Rules`
- **Clusters of 3+ related patterns** become rule files in `~/.claude/rules/` (auto-loaded every session)
- **Project-scoped patterns** (seen in only 1 project) stay scoped to that project

### Stage 4: Decay

Runs after promote. Patterns not seen in 14+ days lose confidence (0.02/day). Below 0.40, they're retired -- removed from CLAUDE.md and archived. If a retired pattern reappears in a new session, it resurrects and rebuilds confidence naturally.

### Stage 5: Inject

Every session start, the top 10 most relevant patterns for the current project are printed as context. Claude sees them automatically. No slash command needed.

---

## Getting Started

### Prerequisites

- Python 3.10+
- PyYAML (`pip3 install pyyaml`)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (provides the `claude` CLI)
- macOS or Linux

### Setup

```bash
# 1. Add the marketplace
claude plugin marketplace add luis-mendes-dev/claude-cortex

# 2. Install the plugin
claude plugin install claude-cortex@claude-cortex

# 3. Run first-time setup (inside Claude Code)
/cortex:setup
```

Setup creates the data directories, copies the default config, and schedules the background jobs (launchd on macOS, cron on Linux).

> **Note:** Hooks are installed immediately on plugin install, but they silently no-op until you run `/cortex:setup`.

After setup, just use Claude Code normally. Cortex runs entirely in the background.

---

## Commands

| Command | What it does |
|---------|-------------|
| `/cortex` | Show status dashboard: knowledge articles, active rules, learned skills, decay state |
| `/cortex:setup` | First-run setup: creates directories, copies config, schedules background jobs |
| `/cortex:compile` | Manually trigger compile: sweep uncaptured sessions + process daily files into knowledge |

---

## Architecture

```
~/.claude/learning/              Cortex data (created by /cortex:setup)
  config.yaml                    Your configuration (tunable thresholds)
  daily/                         Raw daily extractions from Haiku
    YYYY-MM-DD-project.md
  knowledge/                     Compiled, scored knowledge articles
    use-guard-clauses.md
  rules/
    active/                      Tracking copies of promoted rules
    retired/                     Decayed rules (kept for audit trail)
  logs/
    cortex.log                   Unified log

~/.claude/CLAUDE.md              Auto-managed ## Learned Rules section
~/.claude/rules/                 Auto-generated rule files (cortex-learned-*.md)
```

### Knowledge Article Format

Every knowledge article is markdown with YAML frontmatter:

```yaml
---
id: use-guard-clauses
type: pattern
projects: [my-project, other-project]
observations: 7
sessions: 4
confidence: 0.95
first_seen: 2026-04-10
last_seen: 2026-04-16
promoted: true
---

Use early returns and guard clauses instead of deeply nested conditionals.
```

Readable. Greppable. Editable by hand if needed.

---

## Configuration

After setup, edit `~/.claude/learning/config.yaml`:

```yaml
capture:
  max_transcript_chars: 50000    # How much transcript to send to Haiku
  timeout_seconds: 30            # Haiku call timeout
  claude_model: haiku            # Model for extraction

confidence:
  observation_weight: 0.15       # Weight per observation
  session_weight: 0.20           # Weight per unique session
  recency_bonus: 0.10            # Bonus if seen within 7 days

promote:
  rule_confidence: 0.85          # Minimum confidence to promote
  rule_min_sessions: 3           # Minimum sessions to promote
  max_active_rules: 30           # Cap on CLAUDE.md learned rules
  max_active_skills: 10          # Cap on generated rule files

decay:
  grace_period_days: 14          # Days before decay starts
  rate_per_day: 0.02             # Confidence lost per day after grace
  retirement_threshold: 0.40     # Retire below this

inject:
  max_patterns: 10               # Top N patterns injected at session start
```

---

## Data Storage

All data is markdown with YAML frontmatter. No databases, no binary formats.

| Location | What | Auto-loaded? |
|----------|------|-------------|
| `~/.claude/learning/daily/` | Raw daily extractions | No (intermediate) |
| `~/.claude/learning/knowledge/` | Compiled knowledge articles | No (source of truth) |
| `~/.claude/learning/rules/active/` | Tracking copies of promoted rules | No (tracking) |
| `~/.claude/learning/rules/retired/` | Decayed rules archive | No (audit trail) |
| `~/.claude/CLAUDE.md` `## Learned Rules` | Promoted individual rules | **Yes, every session** |
| `~/.claude/rules/cortex-learned-*.md` | Promoted rule clusters | **Yes, every session** |
| SessionStart hook output | Top 10 patterns for current project | **Yes, every session** |

---

## How It Compares

| Feature | Cortex | claude-reflect | claude-memory-compiler | enso-os |
|---------|--------|---------------|----------------------|---------|
| Captures corrections | Yes | Yes (manual `/reflect`) | No | Errors only |
| Captures patterns | Yes | No | Yes | No |
| Compiles & deduplicates | Yes | No | Yes | No |
| Auto-promotes to CLAUDE.md | **Yes** | Manual only | No | No |
| Generates rule files | **Yes** | Manual only | No | No |
| Decays stale patterns | **Yes** | No | No | Yes |
| Sweeps missed sessions | **Yes** | No | No | No |
| Zero manual steps | **Yes** | No (`/reflect` required) | Partial | Yes |
| Cross-project learning | **Yes** | No | No | No |

---

## Customization

- **Thresholds**: Tune confidence weights, promotion thresholds, and decay rates in `config.yaml`
- **Max rules**: Cap how many learned rules appear in CLAUDE.md (default 30)
- **Injection count**: Control how many patterns are injected at session start (default 10)
- **Grace period**: Adjust how long before unused patterns start decaying (default 14 days)
- **Model**: Change `claude_model` to use a different model for extraction
- **Schedule**: Modify launchd plists or cron entries for different compile/promote times
- **Knowledge articles**: Edit or delete any `.md` file in `~/.claude/learning/knowledge/` directly

---

## Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | Used for the core engine |
| PyYAML | Any | `pip3 install pyyaml` |
| Claude Code | Any | Provides `claude` CLI for Haiku extraction |
| OS | macOS or Linux | launchd (macOS) or cron (Linux) for scheduling |

---

## Uninstall

```bash
# Option 1: Run the uninstall script
bash ~/.claude/plugins/cache/claude-cortex/claude-cortex/*/scripts/uninstall.sh

# Option 2: Inside Claude Code, ask Claude to run it
```

The uninstall script removes scheduled jobs, optionally archives your learning data, and cleans up the `## Learned Rules` section from CLAUDE.md.

---

<p align="center">
  <em>Built for <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a>. Learnings are yours -- all data stays local as markdown files.</em>
</p>

## License

MIT -- see [LICENSE](LICENSE).
