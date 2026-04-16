---
name: compile
description: Manually trigger Cortex compile -- sweeps uncaptured sessions and compiles daily extractions into knowledge articles. Use when you want to process learnings immediately instead of waiting for the 2am daily job.
---

Run the Cortex compile command:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/cortex-compile-interactive.sh"
```

This will:
1. Sweep for recent sessions that weren't captured by the SessionEnd hook (max 20)
2. Parse daily extraction files into individual learning entries
3. Deduplicate against existing knowledge articles
4. Create new knowledge articles with confidence scores

After it completes, run `/cortex` to see the updated status.
