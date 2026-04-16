# Cortex

**Self-learning system for Claude Code.** The first plugin to close the full learning loop.

Cortex captures what you teach Claude Code and makes it permanent. Corrections, patterns, decisions, and mistakes from every session are extracted, compiled into knowledge, and promoted into your CLAUDE.md rules and skill files automatically. Stale patterns decay and retire. Zero manual steps after setup.

```
Session ends  -->  Haiku extracts learnings  -->  daily/2026-04-16-myproject.md
                                                         |
Daily 2am     -->  Deduplicate & score      -->  knowledge/use-guard-clauses.md
                                                         |
Weekly Sun    -->  Promote high-confidence   -->  ~/.claude/CLAUDE.md (## Learned Rules)
              -->  Decay stale patterns      -->  rules/retired/
                                                         |
Session starts -->  Inject top 10 patterns  -->  Claude sees them automatically
```

## Install

```bash
# Add the marketplace
claude plugin marketplace add luis-mendes-dev/claude-cortex

# Install the plugin
claude plugin install claude-cortex@claude-cortex

# Run first-time setup (creates directories, schedules background jobs)
# Inside Claude Code:
/cortex:setup
```

## How It Works

### Capture (every session end)

When a Claude Code session ends, Cortex sends the transcript to Haiku and extracts 5 types of learnings:

- **Corrections** -- when you said "no" or "wrong" and Claude changed approach
- **Decisions** -- explicit choices between alternatives with rationale
- **Gotchas** -- something unexpected that caused a retry or failure
- **Patterns** -- workflows that worked well and were repeated
- **Mistakes** -- things Claude did wrong that had to be fixed

Cost: ~$0.01-0.03 per session. Falls back to regex if Haiku is unavailable.

### Compile (daily at 2am)

Merges daily extractions into deduplicated knowledge articles. Each article has a confidence score based on:

```
confidence = min(1.0, (observations x 0.15) + (sessions x 0.20) + recency_bonus)
```

Patterns observed multiple times across multiple sessions score higher.

### Promote (weekly, Sunday 3am)

Patterns with confidence >= 0.85 seen in 3+ sessions are promoted:
- **Single patterns** become rules in `~/.claude/CLAUDE.md` under `## Learned Rules`
- **Clusters of 3+ related patterns** become slash commands in `~/.claude/commands/` (e.g., `/cortex-learned-pattern`)
- **Project-scoped patterns** (seen in only 1 project) stay local

### Decay (weekly, Sunday 3am)

Patterns not seen in 14+ days start losing confidence (0.02/day). Below 0.40, they're retired -- removed from CLAUDE.md and archived. If the pattern reappears in a new session, it resurrects and rebuilds confidence naturally.

### Inject (every session start)

Top 10 relevant patterns for the current project are printed at session start. Claude sees them as context.

## Commands

| Command | What it does |
|---------|-------------|
| `/cortex` | Show status: articles, rules, skills, decay state |
| `/cortex:setup` | First-run setup: directories, config, scheduled jobs |

## Configuration

After setup, edit `~/.claude/learning/config.yaml` to tune thresholds:

```yaml
capture:
  max_transcript_chars: 50000    # How much transcript to analyze
  claude_model: haiku            # Model for extraction

promote:
  rule_confidence: 0.85          # Minimum confidence to promote
  rule_min_sessions: 3           # Minimum sessions to promote
  max_active_rules: 30           # Cap on CLAUDE.md rules

decay:
  grace_period_days: 14          # Days before decay starts
  rate_per_day: 0.02             # Confidence lost per day after grace
  retirement_threshold: 0.40     # Retire below this
```

## Data

All data lives in `~/.claude/learning/`:

```
~/.claude/learning/
  config.yaml         # Your configuration
  daily/              # Raw daily extractions
  knowledge/          # Compiled, scored articles
  rules/active/       # Tracking copies of promoted rules
  rules/retired/      # Decayed rules (audit trail)
  logs/cortex.log     # Unified log

# Auto-generated skill files go to ~/.claude/commands/ so Claude Code discovers them:
~/.claude/commands/
  cortex-learned-pattern.md    # Example: clustered pattern learnings
  cortex-learned-correction.md # Example: clustered correction learnings
```

Everything is markdown with YAML frontmatter. Readable, greppable, editable.

## How It Compares

| Feature | Cortex | claude-reflect | claude-memory-compiler | enso-os |
|---------|--------|---------------|----------------------|---------|
| Captures corrections | Yes | Yes (manual /reflect) | No | Errors only |
| Captures patterns | Yes | No | Yes | No |
| Compiles knowledge | Yes (dedup + score) | No | Yes | No |
| Promotes to CLAUDE.md | Yes (automatic) | Yes (manual) | No | No |
| Generates skills | Yes | Yes (manual) | No | No |
| Decays stale patterns | Yes | No | No | Yes |
| Zero manual steps | Yes | No (/reflect required) | Partial | Yes |

## Requirements

- Python 3.10+
- PyYAML (`pip3 install pyyaml`)
- Claude Code (for the `claude` CLI used by Haiku extraction)
- macOS or Linux

## Uninstall

```bash
bash ~/.claude/plugins/cache/claude-cortex/claude-cortex/*/scripts/uninstall.sh
```

Or inside Claude Code, ask Claude to run the uninstall script.

## License

MIT
