---
name: setup
description: First-run setup for Cortex learning system. Creates directories, copies config, schedules background jobs. Run once per machine.
---

Run the Cortex setup script to initialize the learning system:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"
```

This will:
1. Check that Python 3.10+ and PyYAML are installed
2. Create the learning directory at ~/.claude/learning/
3. Copy the default configuration
4. Schedule daily compile (2am) and weekly promote+decay (Sunday 3am) via launchd (macOS) or cron (Linux)
5. Verify everything works

After setup, Cortex runs fully automatically:
- Every session end: captures learnings via Haiku
- Every session start: injects relevant patterns
- Daily: compiles and deduplicates knowledge
- Weekly: promotes high-confidence patterns to CLAUDE.md rules, decays stale ones

No further manual steps needed.
