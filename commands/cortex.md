---
name: cortex
description: Show Cortex learning system status -- knowledge articles, active rules, learned skills, and decay status. Use when user asks what Claude has learned or wants to check learning progress.
---

Run the Cortex status command to show what the learning system has accumulated:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cortex.py" status
```

If the output says "Cortex is not set up yet", tell the user to run `/cortex:setup` first.

Otherwise, display the results and explain:
- **Knowledge articles**: individual learnings extracted from past sessions
- **Active rules**: patterns promoted to ~/.claude/CLAUDE.md (auto-applied every session)
- **Learned skills**: auto-generated skill files from clusters of related patterns
- **Decaying**: rules that haven't been reinforced recently and will retire if not seen again
