---
name: learned
description: Show what Cortex has learned -- lists all knowledge articles sorted by confidence, with type, project tags, and observation counts. Use when the user asks what Claude has learned, what patterns were captured, or wants to review learnings.
---

Read all knowledge articles from `~/.claude/learning/knowledge/` and display them grouped by confidence tier:

1. First, list the directory:
```bash
ls -la ~/.claude/learning/knowledge/
```

2. Then read each `.md` file and extract the frontmatter (confidence, type, projects, observations, sessions) and the body text.

3. Present them in three tiers:

**High confidence (>= 0.85)** -- these will be promoted to CLAUDE.md rules on the next weekly promote cycle:
- Show each with: confidence score, type, project tags, observation count, and the learning text

**Medium confidence (0.50 - 0.84)** -- building up, need more reinforcement:
- Same format

**Low confidence (< 0.50)** -- new or decaying, may retire if not reinforced:
- Same format

4. At the end, show:
- Total articles
- How many are promoted (have `promoted: true`)
- How many are in the active rules directory: `ls ~/.claude/learning/rules/active/ 2>/dev/null | wc -l`
- The next promote cycle (Sunday 3am)

Format each entry concisely:
```
[0.95] (pattern) [my-project] 7 obs, 4 sessions
  Use guard clauses for early returns instead of nested conditionals
```
