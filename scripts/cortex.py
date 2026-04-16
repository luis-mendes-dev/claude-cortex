#!/usr/bin/env python3
"""Cortex: Self-learning system for Claude Code.

Captures learnings from every session, compiles knowledge, auto-promotes
to CLAUDE.md rules and skills, decays stale patterns. Zero manual steps.
"""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print(
        "Cortex requires PyYAML. Install with: pip3 install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

# --- Paths ---

LEARNING_DIR = Path.home() / ".claude" / "learning"
CONFIG_PATH = LEARNING_DIR / "config.yaml"
PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).parent.parent))
DEFAULT_CONFIG_PATH = PLUGIN_ROOT / "config" / "config.default.yaml"


# --- Configuration ---


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    if DEFAULT_CONFIG_PATH.exists():
        with open(DEFAULT_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


CONFIG = load_config()


def cfg(dotpath: str, default=None):
    keys = dotpath.split(".")
    val = CONFIG
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
    return val if val is not None else default


# --- Logging ---

LOG_PATH = LEARNING_DIR / "logs" / "cortex.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cortex")


# --- Frontmatter ---


def parse_frontmatter(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
    if match:
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        body = match.group(2).strip()
        return meta, body
    return {}, text.strip()


def write_frontmatter(meta: dict, body: str) -> str:
    fm = yaml.dump(meta, default_flow_style=False, sort_keys=False).strip()
    return f"---\n{fm}\n---\n\n{body}\n"


def read_article(path: Path) -> tuple[dict, str]:
    return parse_frontmatter(path.read_text())


def write_article(path: Path, meta: dict, body: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(write_frontmatter(meta, body))


# --- Project Detection ---


def detect_project() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return os.path.basename(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return os.path.basename(os.getcwd())


def encode_project_path() -> str:
    project_dir = None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            project_dir = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    if project_dir is None:
        project_dir = os.getcwd()
    encoded = project_dir.replace("/", "-")
    if not encoded.startswith("-"):
        encoded = "-" + encoded
    return encoded


def find_latest_session() -> Optional[Path]:
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return None
    # Find the most recently modified .jsonl across all projects
    latest = None
    latest_mtime = 0
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            mtime = jsonl.stat().st_mtime
            if mtime > latest_mtime:
                latest = jsonl
                latest_mtime = mtime
    return latest


# --- LLM Helper ---


def find_claude_cli() -> str:
    """Find the claude CLI binary."""
    configured = cfg("capture.claude_cli")
    if configured and shutil.which(configured):
        return configured
    # Search common locations
    for candidate in ["claude", str(Path.home() / ".local/bin/claude"), "/usr/local/bin/claude"]:
        if shutil.which(candidate):
            return candidate
    return "claude"  # Hope for the best


def ask_haiku(prompt: str, timeout: int = None) -> Optional[str]:
    if timeout is None:
        timeout = cfg("capture.timeout_seconds", 30)
    claude_cli = find_claude_cli()
    model = cfg("capture.claude_model", "haiku")
    try:
        result = subprocess.run(
            [claude_cli, "-p", "--model", model, "--max-turns", "1"],
            input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning(f"Haiku call failed: {e}")
    return None


# --- Path Helpers ---


def daily_dir() -> Path:
    return LEARNING_DIR / "daily"


def knowledge_dir() -> Path:
    return LEARNING_DIR / "knowledge"


def rules_active_dir() -> Path:
    return LEARNING_DIR / "rules" / "active"


def rules_retired_dir() -> Path:
    return LEARNING_DIR / "rules" / "retired"


def skills_dir() -> Path:
    # Write to ~/.claude/rules/ so Claude Code auto-loads them every session
    return Path.home() / ".claude" / "rules"


def global_claude_md() -> Path:
    return Path.home() / ".claude" / "CLAUDE.md"


# --- Confidence ---


def compute_confidence(observations: int, sessions: int, last_seen: date) -> float:
    obs_w = cfg("confidence.observation_weight", 0.15)
    sess_w = cfg("confidence.session_weight", 0.20)
    bonus = cfg("confidence.recency_bonus", 0.10)
    window = cfg("confidence.recency_window_days", 7)

    days_ago = (date.today() - last_seen).days
    recency = bonus if days_ago <= window else 0.0
    return min(1.0, (observations * obs_w) + (sessions * sess_w) + recency)


# --- Project Name from Encoded Path ---


def project_name_from_encoded_dir(encoded_dir_name: str) -> str:
    """Extract project name from Claude Code's encoded project directory.
    e.g., '-Users-johndoe-Documents-Projects-my-project' -> 'my-project'
    """
    raw = encoded_dir_name.lstrip("-")
    home_parts = str(Path.home()).lstrip("/").split("/")
    home_encoded = "-".join(home_parts)

    if raw.startswith(home_encoded):
        remainder = raw[len(home_encoded):].lstrip("-")
        if not remainder:
            return "unknown"
        # Try to reconstruct the actual filesystem path
        # by testing progressively which segments are dirs
        test_base = Path.home()
        segments = remainder.split("-")
        resolved = []
        i = 0
        while i < len(segments):
            # Try increasingly long dash-joined segments
            for end in range(len(segments), i, -1):
                candidate = "-".join(segments[i:end])
                if (test_base / candidate).exists():
                    test_base = test_base / candidate
                    resolved.append(candidate)
                    i = end
                    break
            else:
                # No match found, take single segment
                candidate = segments[i]
                test_base = test_base / candidate
                resolved.append(candidate)
                i += 1
        return resolved[-1] if resolved else "unknown"

    # Fallback: last meaningful segment
    return raw.rsplit("-", 1)[-1] if "-" in raw else raw


def project_name_from_jsonl(jsonl_path: Path) -> Optional[str]:
    """Try to extract project name from JSONL session file metadata."""
    try:
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    cwd = data.get("cwd") or data.get("workingDirectory")
                    if cwd:
                        return os.path.basename(cwd)
                except json.JSONDecodeError:
                    continue
                # Only check first 5 lines
                break
    except (OSError, IOError):
        pass
    return None


# --- Slugify ---


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_]+", "-", slug).strip("-")[:80]


# --- Setup Check ---


def is_setup() -> bool:
    return LEARNING_DIR.exists() and (LEARNING_DIR / "config.yaml").exists()


# ============================================================
# COMMANDS
# ============================================================

# --- Capture ---

CAPTURE_PROMPT = """Analyze this Claude Code session transcript. Extract learnings in exactly this format:

## Corrections
- <what was wrong> -> <what the correct approach is>

## Decisions
- <decision made> because <rationale>

## Gotchas
- <what happened> -- avoid by <how to prevent>

## Patterns
- <pattern description>

## Mistakes
- <what went wrong> -> <the fix>

Rules:
- EVERY entry MUST start with "- " (dash space) on its own line
- Each entry must be 1-2 sentences max, on a single line
- Only include items with clear evidence in the transcript
- Skip trivial items (typos, formatting)
- If a category has no items, write "- (none)"
- Do NOT include project-specific one-off facts
- Do NOT use bold (**) formatting

Transcript:
{transcript}"""


def regex_fallback(transcript: str) -> str:
    sections = []
    corrections = re.findall(
        r'"(no[,.]|wrong|not like that|instead|actually)[^"]{10,100}"',
        transcript, re.IGNORECASE,
    )
    if corrections:
        items = "\n".join(f"- User correction detected: ...{c[:80]}..." for c in corrections[:5])
        sections.append(f"## Corrections\n{items}")
    errors = re.findall(
        r"(error|failed|exception|traceback)[^\"]{10,80}",
        transcript, re.IGNORECASE,
    )
    if errors:
        items = "\n".join(f"- Error detected: ...{e[:80]}..." for e in errors[:5])
        sections.append(f"## Mistakes\n{items}")
    return "\n\n".join(sections) if sections else ""


def cmd_capture(args):
    if not is_setup():
        return
    log.info("Starting capture...")
    session_file = find_latest_session()
    if not session_file:
        log.info("No session file found")
        return

    mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
    age_minutes = (datetime.now() - mtime).total_seconds() / 60
    if age_minutes > 30:
        log.info(f"Latest session is {age_minutes:.0f}m old, skipping")
        return

    max_chars = cfg("capture.max_transcript_chars", 50000)
    raw = session_file.read_text()
    transcript = raw[-max_chars:] if len(raw) > max_chars else raw

    result = ask_haiku(CAPTURE_PROMPT.format(transcript=transcript), timeout=60)

    if not result:
        log.warning("Haiku extraction failed, falling back to regex")
        result = regex_fallback(transcript)

    if not result or result.strip() == "":
        log.info("No learnings extracted")
        return

    project = detect_project()
    today = date.today().isoformat()
    ddir = daily_dir()
    ddir.mkdir(parents=True, exist_ok=True)
    daily_file = ddir / f"{today}-{project}.md"
    session_id = session_file.stem

    if daily_file.exists():
        existing = daily_file.read_text()
        daily_file.write_text(f"{existing}\n\n---\n\n## Session: {session_id}\n\n{result}\n")
    else:
        meta = {"date": today, "project": project, "compiled": False}
        body = f"## Session: {session_id}\n\n{result}"
        write_article(daily_file, meta, body)

    log.info(f"Captured learnings to {daily_file}")


# --- Compile ---

DEDUP_PROMPT = """Are these two learnings about the same concept or pattern? Consider them duplicates if they describe the same rule, gotcha, or approach even if worded differently.

Learning A:
{a}

Learning B:
{b}

Reply with exactly YES or NO."""


def parse_daily_entries(body: str) -> list[dict]:
    entries = []
    current_type = None
    current_entry_lines = []

    def flush_entry():
        if current_type and current_entry_lines:
            text = " ".join(current_entry_lines).strip()
            # Strip leading bullet or bold markers
            text = re.sub(r"^[-*]+\s*", "", text)
            text = re.sub(r"^\*\*[^*]+\*\*:\s*", "", text) if text.startswith("**") else text
            if text and text.lower() != "(none)" and len(text) > 5:
                entries.append({"type": current_type, "text": text[:300]})

    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("## Corrections"):
            flush_entry(); current_entry_lines = []; current_type = "correction"
        elif line.startswith("## Decisions"):
            flush_entry(); current_entry_lines = []; current_type = "decision"
        elif line.startswith("## Gotchas"):
            flush_entry(); current_entry_lines = []; current_type = "gotcha"
        elif line.startswith("## Patterns"):
            flush_entry(); current_entry_lines = []; current_type = "pattern"
        elif line.startswith("## Mistakes"):
            flush_entry(); current_entry_lines = []; current_type = "mistake"
        elif line.startswith("## Session:") or line.startswith("## ") or line.startswith("# "):
            flush_entry(); current_entry_lines = []; current_type = None
        elif line.startswith("---"):
            flush_entry(); current_entry_lines = []
        elif current_type:
            if line.startswith("- ") or line.startswith("**"):
                # New entry starts
                flush_entry()
                current_entry_lines = [line.lstrip("- ")]
            elif line and line.lower() != "(none)":
                # Continuation of current entry
                current_entry_lines.append(line)

    flush_entry()
    return entries


def find_duplicate(text: str, articles: list[tuple[Path, dict, str]]) -> Optional[Path]:
    for path, meta, body in articles:
        response = ask_haiku(DEDUP_PROMPT.format(a=text, b=body), timeout=30)
        if response is None:
            # Retry once on timeout
            response = ask_haiku(DEDUP_PROMPT.format(a=text, b=body), timeout=30)
        if response and response.strip().upper().startswith("YES"):
            return path
    return None


def sweep_uncaptured_sessions(max_sessions: int = 20):
    """Capture learnings from recent sessions that were missed (e.g., terminal closed).
    Limits to max_sessions per run to avoid long first-run sweeps."""
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return
    ddir = daily_dir()
    ddir.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now() - timedelta(days=7)

    # Collect all candidate sessions, sort by recency, cap at max_sessions
    candidates = []
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            mtime = jsonl.stat().st_mtime
            if datetime.fromtimestamp(mtime) < cutoff:
                continue
            if jsonl.stat().st_size < 500:
                continue
            candidates.append((mtime, jsonl, project_dir))

    # Sort by most recent first, cap
    candidates.sort(key=lambda x: x[0], reverse=True)
    candidates = candidates[:max_sessions]

    swept = 0
    total = len(candidates)
    for idx, (mtime, jsonl, project_dir) in enumerate(candidates):
        session_date = date.fromtimestamp(mtime).isoformat()
        # Try JSONL metadata first, then decode from directory name
        project_name = project_name_from_jsonl(jsonl) or project_name_from_encoded_dir(project_dir.name)
        daily_file = ddir / f"{session_date}-{project_name}.md"
        if daily_file.exists() and jsonl.stem in daily_file.read_text():
            continue
        max_chars = cfg("capture.max_transcript_chars", 50000)
        raw = jsonl.read_text()
        transcript = raw[-max_chars:] if len(raw) > max_chars else raw
        result = ask_haiku(CAPTURE_PROMPT.format(transcript=transcript), timeout=60)
        if not result:
            result = regex_fallback(transcript)
        if not result or result.strip() == "":
            continue
        if daily_file.exists():
            existing = daily_file.read_text()
            daily_file.write_text(f"{existing}\n\n---\n\n## Session: {jsonl.stem}\n\n{result}\n")
        else:
            meta = {"date": session_date, "project": project_name, "compiled": False}
            write_article(daily_file, meta, f"## Session: {jsonl.stem}\n\n{result}")
        swept += 1
        log.info(f"Sweep captured: {jsonl.stem} -> {daily_file.name}")
        print(f"  Sweep {swept}/{total}: {project_name} ({session_date})", file=sys.stderr)

    if swept:
        log.info(f"Sweep complete: {swept} sessions captured (max {max_sessions} per run)")


def cmd_compile(args):
    if not is_setup():
        return
    log.info("Starting compile...")

    # Sweep for sessions missed by SessionEnd hook (terminal closed, etc.)
    sweep_uncaptured_sessions()

    ddir = daily_dir()
    if not ddir.exists():
        log.info("No daily directory")
        return

    kdir = knowledge_dir()
    kdir.mkdir(parents=True, exist_ok=True)
    existing = []
    for kf in kdir.glob("*.md"):
        meta, body = read_article(kf)
        existing.append((kf, meta, body))

    compiled_count = 0
    daily_files = [df for df in sorted(ddir.glob("*.md")) if not read_article(df)[0].get("compiled")]
    for df_idx, df in enumerate(daily_files):
        meta, body = read_article(df)
        project = meta.get("project", "unknown")
        print(f"  Compiling {df.name} ({df_idx + 1}/{len(daily_files)})...", file=sys.stderr)
        entries = parse_daily_entries(body)
        session_date = meta.get("date", date.today().isoformat())

        for entry in entries:
            dup_path = find_duplicate(entry["text"], existing)
            if dup_path:
                kmeta, kbody = read_article(dup_path)
                kmeta["observations"] = kmeta.get("observations", 1) + 1
                seen_sessions = kmeta.get("session_dates", [])
                if session_date not in seen_sessions:
                    seen_sessions.append(session_date)
                    kmeta["sessions"] = len(seen_sessions)
                kmeta["session_dates"] = seen_sessions
                kmeta["last_seen"] = session_date
                if project not in kmeta.get("projects", []):
                    kmeta.setdefault("projects", []).append(project)
                kmeta["confidence"] = compute_confidence(
                    kmeta["observations"], kmeta["sessions"],
                    date.fromisoformat(kmeta["last_seen"]),
                )
                write_article(dup_path, kmeta, kbody)
                log.info(f"Updated: {dup_path.name} (obs={kmeta['observations']}, conf={kmeta['confidence']:.2f})")
                existing = [(p, m, b) if p != dup_path else (dup_path, kmeta, kbody) for p, m, b in existing]
            else:
                slug = slugify(entry["text"][:60])
                kpath = kdir / f"{slug}.md"
                counter = 1
                while kpath.exists():
                    kpath = kdir / f"{slug}-{counter}.md"
                    counter += 1
                kmeta = {
                    "id": slug, "type": entry["type"], "projects": [project],
                    "observations": 1, "sessions": 1, "session_dates": [session_date],
                    "confidence": compute_confidence(1, 1, date.fromisoformat(session_date)),
                    "first_seen": session_date, "last_seen": session_date, "promoted": False,
                }
                write_article(kpath, kmeta, entry["text"])
                existing.append((kpath, kmeta, entry["text"]))
                log.info(f"Created: {kpath.name}")
                compiled_count += 1

        meta["compiled"] = True
        write_article(df, meta, body)

    log.info(f"Compile complete. {compiled_count} new articles created.")


# --- Promote ---

RULE_PROMPT = """Distill this learning into a concise CLAUDE.md rule (one line, imperative, actionable).

Learning:
{learning}

Format: **Rule name**: Action to take -- brief reason.
Example: **Time.current always**: Use `Time.current`, never `Time.now` -- timezone-safe.

Reply with just the formatted rule line, nothing else."""

SKILL_PROMPT = """Generate a Claude Code skill file from these related learnings. The skill should be concise and actionable.

Domain: {domain}
Learnings:
{learnings}

Format the skill as a markdown file with:
- A YAML frontmatter block with name, description, tags
- A brief intro (1 sentence)
- Each learning as a clear rule with when/do format

Reply with the complete skill file content."""

LEARNED_RULES_HEADER = "## Learned Rules"
LEARNED_RULES_FOOTER = "<!-- END Learned Rules -->"


def read_learned_rules_section(claude_md: Path) -> tuple[str, str, str]:
    if not claude_md.exists():
        return "", "", ""
    content = claude_md.read_text()
    start = content.find(LEARNED_RULES_HEADER)
    if start == -1:
        return content, "", ""
    end = content.find(LEARNED_RULES_FOOTER, start)
    if end == -1:
        return content[:start], content[start:], ""
    return content[:start], content[start:end + len(LEARNED_RULES_FOOTER)], content[end + len(LEARNED_RULES_FOOTER):]


def write_learned_rules(claude_md: Path, rules: list[str], all_tags: dict):
    before, _, after = read_learned_rules_section(claude_md)
    lines = [LEARNED_RULES_HEADER, ""]
    tag_values = list(all_tags.values())
    for i, rule in enumerate(rules):
        tag_info = tag_values[i] if i < len(tag_values) else {}
        tags = " ".join(f"[{t}]" for t in tag_info.get("projects", []))
        conf = tag_info.get("confidence", 0)
        lines.append(f"- {rule} {tags} [confidence: {conf:.2f}]")
    lines.extend(["", LEARNED_RULES_FOOTER])
    section = "\n".join(lines)
    if not before.endswith("\n\n"):
        before = before.rstrip() + "\n\n"
    claude_md.write_text(before + section + after)


def cmd_promote(args):
    if not is_setup():
        return
    log.info("Starting promote...")
    kdir = knowledge_dir()
    if not kdir.exists():
        return

    rule_conf = cfg("promote.rule_confidence", 0.85)
    rule_min_sess = cfg("promote.rule_min_sessions", 3)
    skill_conf = cfg("promote.skill_confidence", 0.90)
    skill_min_sess = cfg("promote.skill_min_sessions", 5)
    skill_min_articles = cfg("promote.skill_min_articles", 3)
    max_rules = cfg("promote.max_active_rules", 30)
    max_skills = cfg("promote.max_active_skills", 10)

    promotable = []
    for kf in kdir.glob("*.md"):
        meta, body = read_article(kf)
        if meta.get("promoted"):
            continue
        if meta.get("confidence", 0) >= rule_conf and meta.get("sessions", 0) >= rule_min_sess:
            promotable.append((kf, meta, body))

    if not promotable:
        log.info("No articles ready for promotion")
        return

    adir = rules_active_dir()
    adir.mkdir(parents=True, exist_ok=True)
    active_rules = {}
    for rule_file in adir.glob("*.md"):
        rmeta, rbody = read_article(rule_file)
        active_rules[rmeta.get("source_id", rule_file.stem)] = (rule_file, rmeta, rbody)

    new_rules, new_tags, promoted_count = [], {}, 0

    for kf, meta, body in promotable:
        if len(active_rules) + len(new_rules) >= max_rules:
            log.warning(f"Rule limit ({max_rules}) reached")
            break
        rule_text = ask_haiku(RULE_PROMPT.format(learning=body), timeout=30)
        if not rule_text:
            continue
        rule_text = rule_text.strip().strip('"').strip("'")
        rule_meta = {
            "source_id": meta["id"], "source_path": str(kf), "rule_text": rule_text,
            "projects": meta.get("projects", []), "confidence": meta.get("confidence", 0),
            "promoted_at": date.today().isoformat(),
        }
        write_article(adir / f"{meta['id']}.md", rule_meta, rule_text)
        new_rules.append(rule_text)
        new_tags[meta["id"]] = {"projects": meta.get("projects", []), "confidence": meta.get("confidence", 0)}
        meta["promoted"] = True
        write_article(kf, meta, body)
        promoted_count += 1
        log.info(f"Promoted: {meta['id']} -> rule")

    if new_rules or active_rules:
        all_rules, all_tags = [], {}
        for sid, (rf, rmeta, rbody) in active_rules.items():
            all_rules.append(rmeta.get("rule_text", rbody))
            all_tags[sid] = {"projects": rmeta.get("projects", []), "confidence": rmeta.get("confidence", 0)}
        all_rules.extend(new_rules)
        all_tags.update(new_tags)
        write_learned_rules(global_claude_md(), all_rules, all_tags)
        log.info(f"Updated CLAUDE.md with {len(all_rules)} learned rules")

    # Skill clustering
    sdir = skills_dir()
    sdir.mkdir(parents=True, exist_ok=True)
    by_type = {}
    for kf in kdir.glob("*.md"):
        meta, body = read_article(kf)
        by_type.setdefault(meta.get("type", "unknown"), []).append((kf, meta, body))
    existing_skills = list(sdir.glob("*.md"))
    for article_type, articles in by_type.items():
        high_conf = [(kf, m, b) for kf, m, b in articles
                     if m.get("confidence", 0) >= skill_conf and m.get("sessions", 0) >= skill_min_sess]
        if len(high_conf) >= skill_min_articles and len(existing_skills) < max_skills:
            learnings_text = "\n".join(f"- {b}" for _, _, b in high_conf)
            skill_content = ask_haiku(SKILL_PROMPT.format(domain=article_type, learnings=learnings_text), timeout=30)
            if skill_content:
                skill_path = sdir / f"cortex-learned-{article_type}.md"
                skill_path.write_text(skill_content)
                existing_skills.append(skill_path)
                log.info(f"Generated skill: {skill_path.name}")

    log.info(f"Promote complete. {promoted_count} articles promoted.")


# --- Decay ---


def rebuild_claude_md_rules():
    adir = rules_active_dir()
    active_rules, all_tags = [], {}
    if adir.exists():
        for rf in adir.glob("*.md"):
            rmeta, rbody = read_article(rf)
            sid = rmeta.get("source_id", rf.stem)
            active_rules.append(rmeta.get("rule_text", rbody))
            all_tags[sid] = {"projects": rmeta.get("projects", []), "confidence": rmeta.get("confidence", 0)}
    if active_rules:
        write_learned_rules(global_claude_md(), active_rules, all_tags)
    else:
        cmd_path = global_claude_md()
        if cmd_path.exists():
            before, section, after = read_learned_rules_section(cmd_path)
            if section:
                cmd_path.write_text(before.rstrip() + "\n" + after.lstrip())


def cmd_decay(args):
    if not is_setup():
        return
    log.info("Starting decay...")
    grace = cfg("decay.grace_period_days", 14)
    rate = cfg("decay.rate_per_day", 0.02)
    retire_threshold = cfg("decay.retirement_threshold", 0.40)
    kdir = knowledge_dir()
    if not kdir.exists():
        return

    retired_count, decayed_count = 0, 0
    rdir = rules_retired_dir()
    rdir.mkdir(parents=True, exist_ok=True)

    for kf in list(kdir.glob("*.md")):
        meta, body = read_article(kf)
        last_seen = meta.get("last_seen")
        if not last_seen:
            continue
        try:
            last_date = date.fromisoformat(str(last_seen))
        except (ValueError, TypeError):
            continue
        days_stale = (date.today() - last_date).days
        if days_stale <= grace:
            continue
        decay_amount = (days_stale - grace) * rate
        new_conf = max(0, meta.get("confidence", 0) - decay_amount)
        meta["confidence"] = round(new_conf, 4)
        decayed_count += 1

        if new_conf < retire_threshold:
            meta["retired_at"] = date.today().isoformat()
            meta["retired_reason"] = f"Confidence decayed to {new_conf:.2f}"
            write_article(rdir / kf.name, meta, body)
            kf.unlink()
            rule_path = rules_active_dir() / f"{meta.get('id', kf.stem)}.md"
            if rule_path.exists():
                rule_path.unlink()
            retired_count += 1
            log.info(f"Retired: {kf.name} (confidence: {new_conf:.2f})")
        else:
            write_article(kf, meta, body)

    if retired_count > 0:
        rebuild_claude_md_rules()
    log.info(f"Decay complete. {decayed_count} decayed, {retired_count} retired.")


# --- Inject ---


def cmd_inject(args):
    if not is_setup():
        return
    kdir = knowledge_dir()
    if not kdir.exists():
        return
    project = detect_project()
    max_patterns = cfg("inject.max_patterns", 10)
    relevant = []
    for kf in kdir.glob("*.md"):
        meta, body = read_article(kf)
        projects = meta.get("projects", [])
        conf = meta.get("confidence", 0)
        if project in projects or len(projects) >= 2:
            relevant.append((conf, body, projects))
    if not relevant:
        return
    relevant.sort(key=lambda x: x[0], reverse=True)
    top = relevant[:max_patterns]
    lines = ["LEARNED PATTERNS (auto-generated by Cortex):"]
    for conf, body, projects in top:
        text = body.split("\n")[0][:120]
        lines.append(f"- {text} [{conf:.2f}]")
    print("\n".join(lines))


# --- Status ---


def cmd_status(args):
    if not is_setup():
        print("Cortex is not set up yet. Run /cortex:setup to get started.")
        return
    kdir = knowledge_dir()
    article_count = len(list(kdir.glob("*.md"))) if kdir.exists() else 0
    rule_count = len(list(rules_active_dir().glob("*.md"))) if rules_active_dir().exists() else 0
    skill_count = len([f for f in skills_dir().glob("cortex-learned-*.md") if f.is_file()]) if skills_dir().exists() else 0
    retired_count = len(list(rules_retired_dir().glob("*.md"))) if rules_retired_dir().exists() else 0

    last_capture = last_compile = last_promote = "never"
    if LOG_PATH.exists():
        for line in reversed(LOG_PATH.read_text().splitlines()[-200:]):
            if "Starting capture" in line and last_capture == "never":
                last_capture = line.split("]")[0].lstrip("[")
            elif "Starting compile" in line and last_compile == "never":
                last_compile = line.split("]")[0].lstrip("[")
            elif "Starting promote" in line and last_promote == "never":
                last_promote = line.split("]")[0].lstrip("[")

    top_pattern, top_conf = "none", 0
    if kdir.exists():
        for kf in kdir.glob("*.md"):
            meta, body = read_article(kf)
            if meta.get("confidence", 0) > top_conf:
                top_conf = meta.get("confidence", 0)
                top_pattern = f'"{meta.get("id", kf.stem)}" ({top_conf:.2f}, {meta.get("sessions", 0)} sessions)'

    decaying = []
    if kdir.exists():
        for kf in kdir.glob("*.md"):
            meta, _ = read_article(kf)
            if 0 < meta.get("confidence", 0) < 0.60 and meta.get("promoted"):
                decaying.append(meta.get("id", kf.stem))

    print(f"Cortex: {article_count} knowledge articles, {rule_count} active rules, {skill_count} learned skills")
    print(f"Retired: {retired_count} | Last capture: {last_capture} | Last compile: {last_compile} | Last promote: {last_promote}")
    print(f"Top pattern: {top_pattern}")
    if decaying:
        print(f"Decaying: {len(decaying)} rules approaching retirement")


# --- CLI ---


def main():
    parser = argparse.ArgumentParser(description="Cortex: Self-learning system for Claude Code")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capture", help="Extract learnings from latest session")
    sub.add_parser("compile", help="Merge daily extractions into knowledge articles")
    sub.add_parser("promote", help="Promote high-confidence patterns to rules/skills")
    sub.add_parser("decay", help="Apply time-based decay and retire stale patterns")
    sub.add_parser("inject", help="Print relevant patterns for session injection")
    sub.add_parser("status", help="Show Cortex status summary")
    args = parser.parse_args()
    dispatch = {
        "capture": cmd_capture, "compile": cmd_compile, "promote": cmd_promote,
        "decay": cmd_decay, "inject": cmd_inject, "status": cmd_status,
    }
    try:
        dispatch[args.command](args)
    except Exception as e:
        log.error(f"{args.command} failed: {e}", exc_info=True)
        # Never crash — hooks must not block Claude Code
        sys.exit(0)


if __name__ == "__main__":
    main()
