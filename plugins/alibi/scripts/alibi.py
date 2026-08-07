#!/usr/bin/env python3
"""Alibi - passive work-log capture and daily reconciliation.

Two layers:

  capture     Hooks append raw records to ~/.alibi/journal/YYYY-MM-DD.jsonl.
              Cheap, silent, allowed to be messy. Nobody reads this file.

  reconcile   `day` collapses a day of raw records into per-project totals,
              splitting time that overlapping parallel sessions both claim.
              The agent turns that into the final log entry, with the user
              confirming before anything is written.

Everything is local. No network, no credentials. Standard library only.

House rule: fail open. Every path exits 0 and stays
quiet on unexpected conditions, because a hook that errors on every turn is
worse than a hook that does nothing.
"""

import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

# Alibi deliberately does not parse ticket identifiers. Trackers name issues
# in every imaginable way, so the script records raw branch names and commit
# subjects, and the agent decides what - if anything - is a ticket.

DEFAULTS = {
    "log": "~/.alibi/{yyyy}-{mm}.md",
    "heading": "",
    "idle_gap_minutes": 20,
    "min_session_minutes": 5,
    "min_turns": 3,
    "round_minutes": 15,
    "target_hours": 8,
    "lead_in_minutes": 3,
    "nudge": True,
}

INT_KEYS = ("idle_gap_minutes", "min_session_minutes", "min_turns",
            "round_minutes", "lead_in_minutes")
FLOAT_KEYS = ("target_hours",)
BOOL_KEYS = ("nudge",)


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

def home():
    return os.path.abspath(os.path.expanduser(
        os.environ.get("ALIBI_HOME", "~/.alibi")))


def projects_path():
    return os.path.join(home(), "projects.md")


def journal_path(date):
    return os.path.join(home(), "journal", "%s.jsonl" % date.isoformat())


def state_path(sid):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", sid or "unknown")[:80]
    return os.path.join(home(), "state", "%s.json" % safe)


def declined_marker():
    return os.path.join(home(), ".declined")


def now():
    return datetime.now().astimezone()


# --------------------------------------------------------------------------
# journal io
# --------------------------------------------------------------------------

def append_record(record, date=None):
    """Append one JSON record. Returns True on success, False on any failure.

    A record is filed under the day it is *about*. For live capture that is the
    day it happened, so `at` decides; a rollup marker is written today about an
    earlier day, so it passes `date` explicitly. Filing that one by `at` drops
    it into today's journal, where nothing that reads the reconciled day ever
    looks -- the day stays pending however often it is marked.
    """
    try:
        at = parse_ts(record.get("at")) or now()
        path = journal_path(date or at.date())
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def read_journal(date):
    """Records for one calendar day. Corrupt lines are skipped, not fatal."""
    out = []
    try:
        with open(journal_path(date), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def read_state(sid):
    try:
        with open(state_path(sid), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def write_state(sid, state):
    try:
        path = state_path(sid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        return True
    except Exception:
        return False


def prune_state(days=7):
    """Drop state files from sessions that never fired SessionEnd."""
    try:
        d = os.path.join(home(), "state")
        cutoff = now().timestamp() - days * 86400
        for name in os.listdir(d):
            p = os.path.join(d, name)
            try:
                if os.path.getmtime(p) < cutoff:
                    os.remove(p)
            except Exception:
                continue
    except Exception:
        pass


# --------------------------------------------------------------------------
# projects.md
# --------------------------------------------------------------------------

def _strip_value(raw):
    raw = raw.strip()
    if raw[:1] in ('"', "'") and raw[-1:] == raw[:1] and len(raw) > 1:
        return raw[1:-1]
    # Only treat ' #' as a comment when the value is unquoted, so a heading
    # like `## Work log` survives.
    cut = raw.find(" #")
    if cut != -1:
        raw = raw[:cut]
    return raw.strip()


def load_config_and_projects():
    """Parse projects.md into (config dict, list of project dicts).

    Returns (defaults, []) when the file is absent, so every caller can work
    against a config without special-casing an unconfigured install.
    """
    cfg = dict(DEFAULTS)
    projects = []
    try:
        with open(projects_path(), "r", encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return cfg, projects

    lines = text.splitlines()
    body_start = 0

    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body_start = i + 1
                break
            if ":" not in lines[i]:
                continue
            key, _, raw = lines[i].partition(":")
            key = key.strip()
            if key in DEFAULTS:
                cfg[key] = _strip_value(raw)

    for key in INT_KEYS:
        try:
            cfg[key] = max(0, int(str(cfg[key]).strip()))
        except Exception:
            cfg[key] = DEFAULTS[key]
    for key in FLOAT_KEYS:
        try:
            cfg[key] = max(0.0, float(str(cfg[key]).strip()))
        except Exception:
            cfg[key] = DEFAULTS[key]
    for key in BOOL_KEYS:
        cfg[key] = str(cfg[key]).strip().lower() not in ("false", "0", "no", "off")

    current = None
    for line in lines[body_start:]:
        stripped = line.strip()
        if stripped.startswith("## "):
            current = {"name": stripped[3:].strip(), "ticket": "",
                       "paths": [], "report_as": "", "note": "",
                       "report": True}
            projects.append(current)
            continue
        if current is None or not stripped.startswith("- "):
            continue
        key, _, raw = stripped[2:].partition(":")
        key = key.strip().lower().replace("-", "_")
        value = _strip_value(raw)
        if key == "paths":
            for part in value.split(","):
                part = part.strip()
                if part:
                    current["paths"].append(
                        os.path.abspath(os.path.expanduser(part)))
        elif key in ("ticket", "jira"):
            # `jira:` is accepted as a synonym so a Jira shop can write what
            # comes naturally, but nothing in Alibi is Jira-specific.
            current["ticket"] = value
        elif key in ("report_as", "note"):
            current[key] = value
        elif key == "report":
            # `report: false` marks a personal project: captured, but never
            # nudged and never reported.
            current["report"] = value.lower() not in ("false", "0", "no", "off")

    return cfg, projects


def slugify(text):
    """Claude Code's directory-slug encoding, as used for the per-session
    scratchpad and ~/.claude/projects: the originating directory with its
    separators folded to dashes.

    Deliberately more aggressive than the real rule (which at least folds both
    `/` and `.`, so `~/x/.worktrees` becomes `-x--worktrees`). The encoding is
    undocumented and lossy, so we never try to reverse it -- we only ever
    slugify a known path and compare. Over-folding costs at most a theoretical
    collision between two configured projects; under-folding would silently
    fail to match any project whose path contains a dot.
    """
    return "".join(c if (c.isascii() and c.isalnum()) else "-" for c in text)


def match_project(path, projects):
    """Longest matching configured path wins. Returns None when unmapped."""
    if not path:
        return None
    path = os.path.abspath(path)
    best = None
    best_len = -1
    for project in projects:
        for base in project["paths"]:
            if path == base or path.startswith(base.rstrip(os.sep) + os.sep):
                if len(base) > best_len:
                    best, best_len = project, len(base)
    if best:
        return best

    # Nothing matched directly. A session run from a scratchpad or worktree
    # under a temp directory carries its originating project in a slug
    # component -- /private/tmp/.../-Users-me-dev-thing/<uuid>/scratchpad/...
    # -- so compare in slug space, mirroring the containment test above.
    for segment in path.split(os.sep):
        if not segment.startswith("-"):
            continue
        for project in projects:
            for base in project["paths"]:
                slug = slugify(base.rstrip(os.sep))
                if segment == slug or segment.startswith(slug + "-"):
                    if len(base) > best_len:
                        best, best_len = project, len(base)
    return best


def find_project_by_name(name, projects):
    """Look a project up by section name or report-as label."""
    for project in projects:
        if name in (project["name"], project.get("report_as")):
            return project
    return None


def resolve_log_path(cfg, date):
    raw = str(cfg.get("log") or DEFAULTS["log"])
    raw = (raw.replace("{yyyy}", "%04d" % date.year)
              .replace("{mm}", "%02d" % date.month)
              .replace("{dd}", "%02d" % date.day))
    return os.path.abspath(os.path.expanduser(raw))


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------

def git(args, cwd=None, timeout=3):
    try:
        res = subprocess.run(["git"] + args, cwd=cwd, timeout=timeout,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if res.returncode != 0:
            return ""
        return res.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return ""


def main_repo_root(cwd):
    """Repository root, collapsing a git worktree onto its main checkout.

    Worktrees are the same project as the repo they came from, so they must
    map to the same configured project rather than looking like a new one.
    """
    common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"],
                 cwd=cwd)
    if common.endswith(os.sep + ".git"):
        return os.path.dirname(common)
    return git(["rev-parse", "--show-toplevel"], cwd=cwd)


def repo_info(cwd):
    return main_repo_root(cwd), git(["rev-parse", "--abbrev-ref", "HEAD"],
                                    cwd=cwd)


def git_email(cwd=None):
    return git(["config", "user.email"], cwd=cwd)


def commits_on(repo, date, email):
    if not repo:
        return []
    args = ["log", "--no-merges",
            "--since", "%s 00:00" % date.isoformat(),
            "--until", "%s 23:59:59" % date.isoformat(),
            "--format=%h %s", "-n", "40"]
    if email:
        args[2:2] = ["--author", email]
    out = git(args, cwd=repo, timeout=5)
    return [l for l in out.splitlines() if l.strip()]


# --------------------------------------------------------------------------
# hook plumbing
# --------------------------------------------------------------------------

def read_hook_input():
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def emit_context(text):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": text,
    }}, ensure_ascii=False))


def export_env(name, value):
    """Persist an env var for the rest of the session via $CLAUDE_ENV_FILE."""
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file or not value:
        return
    try:
        escaped = "'" + str(value).replace("'", "'\"'\"'") + "'"
        with open(env_file, "a", encoding="utf-8") as fh:
            fh.write("export %s=%s\n" % (name, escaped))
    except Exception:
        pass


# --------------------------------------------------------------------------
# time maths
# --------------------------------------------------------------------------

def blocks_from_beats(beats, idle_gap_minutes, lead_in_minutes):
    """Collapse beat timestamps into active blocks.

    A gap longer than idle_gap ends a block - that gap is the meeting, the
    lunch, the school run. Each block is extended backwards by lead_in to
    account for the time spent writing the prompt before the turn ran.
    """
    if not beats:
        return []
    beats = sorted(beats)
    gap = timedelta(minutes=idle_gap_minutes)
    lead = timedelta(minutes=lead_in_minutes)
    blocks = []
    run = [beats[0]]
    for ts in beats[1:]:
        if ts - run[-1] > gap:
            blocks.append((run[0] - lead, run[-1]))
            run = [ts]
        else:
            run.append(ts)
    blocks.append((run[0] - lead, run[-1]))

    # Lead-in can push a block back into its predecessor; keep them disjoint.
    merged = []
    for start, end in blocks:
        if merged and start < merged[-1][1]:
            start = merged[-1][1]
        if end > start:
            merged.append((start, end))
    return merged


def clamp_blocks(blocks, day_start, day_end):
    out = []
    for start, end in blocks:
        start = max(start, day_start)
        end = min(end, day_end)
        if end > start:
            out.append((start, end))
    return out


def split_overlaps(blocks_by_sid):
    """Credit each minute of wall clock to the sessions that were live in it.

    Two sessions running at once for an hour yield 30 minutes each, not 60
    each. The overlapped total is returned separately so the split is visible
    in the report rather than silently baked into the numbers.
    """
    edges = set()
    for blocks in blocks_by_sid.values():
        for start, end in blocks:
            edges.add(start)
            edges.add(end)
    edges = sorted(edges)

    credited = dict((sid, 0.0) for sid in blocks_by_sid)
    overlap_minutes = 0.0
    union_minutes = 0.0

    for i in range(len(edges) - 1):
        seg_start, seg_end = edges[i], edges[i + 1]
        length = (seg_end - seg_start).total_seconds() / 60.0
        if length <= 0:
            continue
        active = [sid for sid, blocks in blocks_by_sid.items()
                  if any(s <= seg_start and e >= seg_end for s, e in blocks)]
        if not active:
            continue
        union_minutes += length
        if len(active) > 1:
            overlap_minutes += length
        share = length / len(active)
        for sid in active:
            credited[sid] += share

    return credited, overlap_minutes, union_minutes


def round_split(values, step):
    """Round to `step` while keeping the parts summing to the rounded whole.

    Independent rounding produces reports where three 15-minute lines are
    claimed to total 50 minutes. Largest-remainder avoids that.
    """
    if step <= 0 or not values:
        return list(values)
    total_units = int(round(sum(values) / float(step)))
    ideal = [v / float(step) for v in values]
    units = [int(math.floor(x)) for x in ideal]
    remainder = total_units - sum(units)
    order = sorted(range(len(values)), key=lambda i: ideal[i] - units[i],
                   reverse=True)
    if remainder > 0:
        for i in order[:remainder]:
            units[i] += 1
    elif remainder < 0:
        for i in reversed(order):
            if remainder == 0:
                break
            if units[i] > 0:
                units[i] -= 1
                remainder += 1
    return [u * step for u in units]


def fmt_minutes(minutes):
    minutes = int(round(minutes))
    if minutes < 60:
        return "%dm" % minutes
    hours, rest = divmod(minutes, 60)
    return "%dh" % hours if rest == 0 else "%dh%02dm" % (hours, rest)


def fmt_clock(dt):
    return dt.strftime("%H:%M")


# --------------------------------------------------------------------------
# subcommand: session-start
# --------------------------------------------------------------------------

def first_run_context():
    """First-run pointer, deliberately evidence-free.

    Gathering candidate repositories, branches and ticket conventions is the
    agent's job at setup time - the procedure lives in the `alibi` skill. An
    earlier version did all of that here (~250 lines of filesystem scanning
    and transcript reading) and it was the buggiest part of the script.
    """
    return "\n".join([
        "<alibi-first-run>",
        "The Alibi work-log plugin is installed but not configured "
        "(~/.alibi/projects.md does not exist). Alibi records nothing at all "
        "until it is configured.",
        "",
        "YOUR FIRST ACTION in this session is to offer setup. Say briefly "
        "what Alibi does (records which repo/branch/ticket you worked on and "
        "for how long, then reconciles a day into a timesheet-ready log; "
        "everything local, no network, no issue-tracker access), then follow "
        "the first-run procedure in the `alibi` skill: gather the evidence "
        "yourself and propose a draft ~/.alibi/projects.md for the user to "
        "correct.",
        "",
        "If the user declines or wants to do it later, run "
        "`python3 \"%s\" decline` and never bring it up again. "
        "They can run /alibi-setup whenever they want." % os.path.abspath(__file__),
        "</alibi-first-run>",
    ])


def unreconciled_days(cfg, limit=7):
    """Days with real activity and no rollup record, most recent first."""
    out = []
    try:
        entries = sorted(os.listdir(os.path.join(home(), "journal")),
                         reverse=True)
    except Exception:
        return out
    today = now().date()
    for name in entries[:limit + 3]:
        if not name.endswith(".jsonl"):
            continue
        try:
            date = datetime.strptime(name[:-6], "%Y-%m-%d").date()
        except Exception:
            continue
        if date >= today:
            continue
        records = read_journal(date)
        # Match the marker's own date, as cmd_day does. Accepting any rollup
        # record in the file made a marker misfiled from another day clear this
        # one too, hiding a day that was never reconciled.
        if any(r.get("t") == "rollup" and r.get("date") == date.isoformat()
               for r in records):
            continue
        if sum(1 for r in records if r.get("t") == "beat") < cfg["min_turns"]:
            continue
        out.append(date.isoformat())
        if len(out) >= limit:
            break
    return out


def cmd_session_start(argv):
    data = read_hook_input()
    sid = data.get("session_id") or ""
    cwd = data.get("cwd") or os.getcwd()

    export_env("ALIBI_SID", sid)
    export_env("ALIBI_SCRIPT", os.path.abspath(__file__))

    if not os.path.exists(projects_path()):
        if os.path.exists(declined_marker()):
            return 0
        emit_context(first_run_context())
        return 0

    prune_state()
    cfg, projects = load_config_and_projects()
    repo, branch = repo_info(cwd)
    project = match_project(repo or cwd, projects)

    stamp = now()
    append_record({"t": "session", "at": stamp.isoformat(), "sid": sid,
                   "cwd": cwd, "repo": repo, "branch": branch,
                   "project": project["name"] if project else ""})
    write_state(sid, {"sid": sid, "started": stamp.isoformat(), "turns": 0,
                      "nudged": False, "noted": False, "cwd": cwd,
                      "repo": repo, "branch": branch})

    # The path is stated here as well as exported, because $ALIBI_SCRIPT only
    # reaches the agent's shell on hosts with an env-file mechanism. Codex has
    # hooks and the same context shape but no env file, so the context is the
    # one channel that carries the path everywhere.
    parts = ["<alibi>",
             "Alibi is tracking this session for work reporting. Use the "
             "`alibi` skill when logging or reconciling work.",
             "Script path (use if $ALIBI_SCRIPT is unset): %s"
             % os.path.abspath(__file__),
             ""]
    if project:
        parts.append("Current directory maps to project: %s" % project["name"])
        if not project.get("report", True):
            parts.append("This project is marked `report: false` - personal, "
                         "not work. Time here is captured but excluded from "
                         "work reports, and Alibi will not ask for a session "
                         "note.")
        if project.get("ticket"):
            parts.append("Ticket hint for this project: %s" % project["ticket"])
        if project.get("report_as"):
            parts.append("Report it as: %s" % project["report_as"])
        if project.get("note"):
            parts.append("Note: %s" % project["note"])
    else:
        parts.append("Current directory is not in projects.md. Record it "
                     "silently; do NOT interrupt this session to ask about it. "
                     "Unmapped directories are raised at reconciliation time, "
                     "in /alibi-day, where the user is already thinking about "
                     "reporting.")
    if repo:
        parts.append("Repository: %s" % repo)
    if branch:
        parts.append("Branch: %s" % branch)
        parts.append("Read the ticket, if any, off the branch name yourself - "
                     "Alibi does not guess at ticket formats.")

    pending = unreconciled_days(cfg)
    if pending:
        parts.append("")
        parts.append("Unreconciled day(s) with recorded activity: %s"
                     % ", ".join(pending))
        parts.append("Mention this once, early, and offer to run /alibi-day "
                     "for the most recent one. Do not push if declined.")

    parts.append("")
    parts.append("Configured projects (~/.alibi/projects.md):")
    for project in projects:
        bits = [project["name"]]
        if project.get("ticket"):
            bits.append("ticket:%s" % project["ticket"])
        if project.get("report_as"):
            bits.append("report-as:%s" % project["report_as"])
        if not project.get("report", True):
            bits.append("report:false (personal - never reported)")
        parts.append("  - %s" % "  ".join(bits))
        for path in project["paths"]:
            parts.append("      %s" % path)
        if project.get("note"):
            parts.append("      note: %s" % project["note"])
    parts.append("</alibi>")

    emit_context("\n".join(parts))
    return 0


# --------------------------------------------------------------------------
# subcommand: turn
# --------------------------------------------------------------------------

def cmd_turn(argv):
    if not os.path.exists(projects_path()):
        return 0

    data = read_hook_input()
    sid = data.get("session_id") or os.environ.get("ALIBI_SID") or ""
    stamp = now()
    append_record({"t": "beat", "at": stamp.isoformat(), "sid": sid})

    cfg, projects = load_config_and_projects()
    state = read_state(sid)
    state["sid"] = sid
    state["turns"] = int(state.get("turns") or 0) + 1
    if not state.get("started"):
        state["started"] = stamp.isoformat()
    write_state(sid, state)

    if not cfg["nudge"] or state.get("nudged") or state.get("noted"):
        return 0
    if state["turns"] < cfg["min_turns"]:
        return 0

    # Personal (`report: false`) projects never reach a report, so asking for
    # a session note would be pure interruption.
    project = match_project(state.get("repo") or state.get("cwd"), projects)
    if project and not project.get("report", True):
        return 0

    started = parse_ts(state.get("started")) or stamp
    elapsed = (stamp - started).total_seconds() / 60.0
    if elapsed < cfg["min_session_minutes"]:
        return 0

    state["nudged"] = True
    write_state(sid, state)

    reason = (
        "Before finishing: record this session in the Alibi work log. "
        "Use the `alibi` skill. Decide which ticket or project this "
        "session's work belongs to (branch, directory and ~/.alibi/projects.md "
        "are in your context; ask the user if genuinely ambiguous), then run "
        "`python3 \"$ALIBI_SCRIPT\" note` with --ticket/--project and 2-4 "
        "concrete --bullet items describing what actually changed. "
        "If nothing worth reporting happened, run it with --skip instead. "
        "Keep this to one short line to the user, then stop. "
        "This fires at most once per session."
    )
    print(json.dumps({"decision": "block", "reason": reason},
                     ensure_ascii=False))
    return 0


# --------------------------------------------------------------------------
# subcommand: session-end
# --------------------------------------------------------------------------

def cmd_session_end(argv):
    if not os.path.exists(projects_path()):
        return 0
    data = read_hook_input()
    sid = data.get("session_id") or os.environ.get("ALIBI_SID") or ""
    append_record({"t": "end", "at": now().isoformat(), "sid": sid})
    try:
        os.remove(state_path(sid))
    except Exception:
        pass
    return 0


# --------------------------------------------------------------------------
# subcommand: note / decline / status / mark-rolled / config
# --------------------------------------------------------------------------

def _arg(argv, name, default=""):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def _args_all(argv, name):
    out = []
    for i, token in enumerate(argv):
        if token == name and i + 1 < len(argv):
            out.append(argv[i + 1])
    return out


def newest_open_sid():
    try:
        d = os.path.join(home(), "state")
        best, best_mtime = "", -1
        for name in os.listdir(d):
            path = os.path.join(d, name)
            mtime = os.path.getmtime(path)
            if mtime > best_mtime:
                state = read_state(name[:-5])
                best, best_mtime = state.get("sid") or name[:-5], mtime
        return best
    except Exception:
        return ""


def cmd_note(argv):
    sid = _arg(argv, "--sid") or os.environ.get("ALIBI_SID") or newest_open_sid()
    skip = "--skip" in argv

    record = {"t": "note", "at": now().isoformat(), "sid": sid}
    if skip:
        record["skip"] = True
    else:
        ticket = _arg(argv, "--ticket")
        if ticket:
            record["ticket"] = ticket
        project = _arg(argv, "--project")
        if project:
            record["project"] = project
        bullets = _args_all(argv, "--bullet") + _args_all(argv, "--bullets")
        record["bullets"] = [b for b in bullets if b.strip()]
        if not record["bullets"] and not ticket and not project:
            print("nothing to record: pass --ticket/--project and --bullet, "
                  "or --skip")
            return 1

    if not append_record(record):
        print("could not write to the journal")
        return 1

    state = read_state(sid)
    state["noted"] = True
    write_state(sid, state)

    print("recorded" if not skip else "recorded as not worth reporting")
    return 0


def cmd_decline(argv):
    try:
        os.makedirs(home(), exist_ok=True)
        with open(declined_marker(), "w", encoding="utf-8") as fh:
            fh.write("Alibi setup was declined on %s.\n"
                     "Delete this file or run /alibi-setup to enable it.\n"
                     % now().isoformat())
        print("Alibi will stay silent. Run /alibi-setup if you change your mind.")
    except Exception:
        pass
    return 0


def cmd_status(argv):
    cfg, projects = load_config_and_projects()
    if not os.path.exists(projects_path()):
        print("not configured: %s does not exist" % projects_path())
        return 0
    print("config:   %s" % projects_path())
    print("journal:  %s" % os.path.join(home(), "journal"))
    print("projects: %d" % len(projects))
    pending = unreconciled_days(cfg)
    print("unreconciled: %s" % (", ".join(pending) if pending else "none"))
    return 0


def cmd_mark_rolled(argv):
    date = parse_date(argv[0] if argv else "")
    if not append_record({"t": "rollup", "at": now().isoformat(),
                          "date": date.isoformat()}, date=date):
        print("could not write the rollup marker to %s -- %s is still pending"
              % (journal_path(date), date.isoformat()))
        return 1
    print("marked %s as reconciled" % date.isoformat())
    return 0


def cmd_config(argv):
    cfg, projects = load_config_and_projects()
    date = parse_date(argv[0] if argv else "")
    out = dict(cfg)
    out["log_path"] = resolve_log_path(cfg, date)
    out["alibi_home"] = home()
    out["projects"] = [p["name"] for p in projects]
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def parse_date(text):
    text = (text or "").strip().lower()
    today = now().date()
    if not text or text == "today":
        return today
    if text == "yesterday":
        return today - timedelta(days=1)
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return today


# --------------------------------------------------------------------------
# subcommand: day
# --------------------------------------------------------------------------

def cmd_day(argv):
    date = parse_date(argv[0] if argv else "")
    cfg, projects = load_config_and_projects()

    records = read_journal(date - timedelta(days=1)) + read_journal(date)
    if not records:
        print("No Alibi records for %s." % date.isoformat())
        return 0

    day_start = datetime.combine(date, datetime.min.time()).astimezone()
    day_end = day_start + timedelta(days=1)

    sessions = {}
    beats = {}
    notes = {}
    rolled = False

    for record in records:
        kind = record.get("t")
        sid = record.get("sid") or ""
        stamp = parse_ts(record.get("at"))
        if kind == "session":
            sessions[sid] = record
        elif kind == "beat" and stamp and day_start <= stamp < day_end:
            beats.setdefault(sid, []).append(stamp)
        elif kind == "note" and stamp and day_start <= stamp < day_end:
            notes.setdefault(sid, []).append(record)
        elif kind == "rollup" and record.get("date") == date.isoformat():
            rolled = True

    blocks_by_sid = {}
    for sid, stamps in beats.items():
        blocks = clamp_blocks(
            blocks_from_beats(stamps, cfg["idle_gap_minutes"],
                              cfg["lead_in_minutes"]),
            day_start, day_end)
        if blocks:
            blocks_by_sid[sid] = blocks

    if not blocks_by_sid:
        print("No activity recorded on %s." % date.isoformat())
        return 0

    credited, overlap_minutes, union_minutes = split_overlaps(blocks_by_sid)

    # Group sessions into reporting buckets.
    buckets = {}
    dropped = []
    unmapped = set()

    for sid, minutes in credited.items():
        session = sessions.get(sid, {})
        cwd = session.get("repo") or session.get("cwd") or ""
        session_notes = notes.get(sid, [])
        real_notes = [n for n in session_notes if not n.get("skip")]

        span = blocks_by_sid[sid]
        raw_minutes = sum((e - s).total_seconds() / 60.0 for s, e in span)
        if raw_minutes < cfg["min_session_minutes"] and not real_notes:
            dropped.append((sid, cwd, raw_minutes))
            continue

        # Tickets only ever come from notes the agent wrote. The script does
        # not read them off branches, because it has no idea what a ticket
        # looks like here - the branch name is reported instead, and the agent
        # fills the gap during reconciliation.
        ticket = ""
        project_name = ""
        for note in real_notes:
            ticket = note.get("ticket") or ticket
            project_name = note.get("project") or project_name
        if project_name:
            # An explicit project on a note always wins - including a
            # `report: false` one, which is how a personal session inside a
            # work directory is rerouted off the log.
            project = find_project_by_name(project_name, projects)
        else:
            project = match_project(cwd, projects)
            if project:
                project_name = project.get("report_as") or project["name"]
            else:
                project_name = os.path.basename(cwd) or "unknown"
                unmapped.add(cwd or "unknown")

        key = (project_name, ticket)
        bucket = buckets.setdefault(key, {
            "minutes": 0.0, "bullets": [], "repos": set(), "skipped": 0,
            "branches": set(), "sessions": 0, "first": None, "last": None,
            "off": False,
        })
        if project and not project.get("report", True):
            bucket["off"] = True
        bucket["minutes"] += minutes
        bucket["sessions"] += 1
        if session.get("branch"):
            bucket["branches"].add(session["branch"])
        if any(n.get("skip") for n in session_notes) and not real_notes:
            bucket["skipped"] += 1
        if cwd:
            bucket["repos"].add(cwd)
        for note in real_notes:
            for bullet in note.get("bullets") or []:
                if bullet not in bucket["bullets"]:
                    bucket["bullets"].append(bullet)
        starts = [s for s, _ in span]
        ends = [e for _, e in span]
        bucket["first"] = min([bucket["first"]] + starts) if bucket["first"] else min(starts)
        bucket["last"] = max([bucket["last"]] + ends) if bucket["last"] else max(ends)

    if not buckets:
        print("Nothing on %s reached the %d-minute reporting threshold."
              % (date.isoformat(), cfg["min_session_minutes"]))
        return 0

    # Personal (`report: false`) buckets are split out before rounding and
    # normalization - exclusion is arithmetic, so it happens here, not in the
    # agent's head. They are still rendered below so nothing vanishes silently.
    keys = sorted((k for k in buckets if not buckets[k]["off"]),
                  key=lambda k: buckets[k]["minutes"], reverse=True)
    off_keys = sorted((k for k in buckets if buckets[k]["off"]),
                      key=lambda k: buckets[k]["minutes"], reverse=True)
    actual = [buckets[k]["minutes"] for k in keys]
    actual_rounded = round_split(actual, cfg["round_minutes"])

    # Normalizing is only honest when the measured day is in the same league
    # as the target. Stretching 20 recorded minutes to fill 8 hours is not a
    # rounding artifact, it is an invented number that could reach a timesheet.
    normalized_rounded = None
    normalize_note = ""
    target = cfg["target_hours"] * 60.0
    if target > 0 and sum(actual) > 0:
        if sum(actual) >= target * 0.5:
            scale = target / sum(actual)
            normalized_rounded = round_split([v * scale for v in actual],
                                             cfg["round_minutes"])
        else:
            normalize_note = (
                "Normalized column suppressed: only %s was measured against "
                "the %gh target, too little to scale up honestly. Report the "
                "actual figures and add non-Claude work (meetings, review, "
                "ops) yourself."
                % (fmt_minutes(sum(actual_rounded)), cfg["target_hours"]))

    wall_start = min(b[0] for blocks in blocks_by_sid.values() for b in blocks)
    wall_end = max(b[1] for blocks in blocks_by_sid.values() for b in blocks)

    # ---- report ----------------------------------------------------------
    out = []
    out.append("ALIBI DAY REPORT  %s%s"
               % (date.isoformat(), "  (already reconciled)" if rolled else ""))
    out.append("")
    out.append("Wall clock span: %s-%s (%s)"
               % (fmt_clock(wall_start), fmt_clock(wall_end),
                  fmt_minutes((wall_end - wall_start).total_seconds() / 60.0)))
    out.append("Active time:     %s  (idle gaps over %d min excluded)"
               % (fmt_minutes(union_minutes), cfg["idle_gap_minutes"]))
    if overlap_minutes >= 1:
        out.append("Parallel work:   %s of that had more than one session "
                   "running; those minutes were split evenly between them."
                   % fmt_minutes(overlap_minutes))
    out.append("")

    if keys:
        header = "  %-28s %-12s %10s" % ("PROJECT", "TICKET", "ACTUAL")
        if normalized_rounded:
            header += " %12s" % ("OF %gh" % cfg["target_hours"])
        out.append(header)
        for i, key in enumerate(keys):
            project_name, ticket = key
            row = "  %-28s %-12s %10s" % (project_name[:28], ticket or "-",
                                          fmt_minutes(actual_rounded[i]))
            if normalized_rounded:
                row += " %12s" % fmt_minutes(normalized_rounded[i])
            out.append(row)
        total_row = "  %-28s %-12s %10s" % ("TOTAL", "", fmt_minutes(sum(actual_rounded)))
        if normalized_rounded:
            total_row += " %12s" % fmt_minutes(sum(normalized_rounded))
        out.append("  " + "-" * (len(total_row) - 2))
        out.append(total_row)
        if normalize_note:
            out.append("")
            out.append(normalize_note)
    else:
        out.append("  All of the day's activity is in `report: false` "
                   "projects - there is nothing to put on the work log.")

    if keys:
        out.append("")
        out.append("DETAIL")
    email = git_email()
    for i, key in enumerate(keys):
        project_name, ticket = key
        bucket = buckets[key]
        out.append("")
        out.append("- %s%s  %s-%s  %s  (%d session%s)"
                   % (project_name, "  [%s]" % ticket if ticket else "",
                      fmt_clock(bucket["first"]), fmt_clock(bucket["last"]),
                      fmt_minutes(actual_rounded[i]), bucket["sessions"],
                      "" if bucket["sessions"] == 1 else "s"))
        if bucket["branches"]:
            out.append("    branches: %s" % ", ".join(sorted(bucket["branches"])))
        for bullet in bucket["bullets"]:
            out.append("    note: %s" % bullet)
        if not bucket["bullets"]:
            if bucket["skipped"] == bucket["sessions"]:
                out.append("    note: (marked at the time as not worth "
                           "reporting - the time is real, but do not invent "
                           "a description for it)")
            else:
                out.append("    note: (none recorded - reconstruct from the "
                           "commits below, or ask)")
        for repo in sorted(bucket["repos"]):
            commits = commits_on(repo, date, email)
            if commits:
                out.append("    commits in %s:" % repo)
                for line in commits:
                    out.append("      %s" % line)

    if off_keys:
        out.append("")
        out.append("NOT REPORTED  (report: false in projects.md)")
        for key in off_keys:
            project_name, ticket = key
            bucket = buckets[key]
            out.append("  - %s%s  %s-%s  %s  (%d session%s)"
                       % (project_name, "  [%s]" % ticket if ticket else "",
                          fmt_clock(bucket["first"]), fmt_clock(bucket["last"]),
                          fmt_minutes(bucket["minutes"]), bucket["sessions"],
                          "" if bucket["sessions"] == 1 else "s"))
        out.append("  Personal time, excluded from the table, the total and "
                   "normalization. Do not put it in the work log.")

    if dropped:
        out.append("")
        out.append("Dropped, under the %d-minute threshold:"
                   % cfg["min_session_minutes"])
        # Rolled up per directory: a test harness or a burst of short-lived
        # sessions in one repo would otherwise print the same path dozens of
        # times and bury the rest of the report.
        rollup = {}
        for _, cwd, minutes in dropped:
            entry = rollup.setdefault(cwd or "unknown", [0, 0.0])
            entry[0] += 1
            entry[1] += minutes
        for cwd in sorted(rollup, key=lambda key: (-rollup[key][1], key)):
            count, minutes = rollup[cwd]
            out.append("  - %s (%s%s)"
                       % (cwd, fmt_minutes(minutes),
                          "" if count == 1 else ", %d sessions" % count))

    if unmapped:
        out.append("")
        out.append("PROPOSED PROJECT ADDITIONS")
        out.append("These directories produced work today but are not in "
                   "~/.alibi/projects.md. Reconciliation is the right moment "
                   "to ask - show each draft, let the user rename or reject "
                   "it, then append the accepted ones to projects.md.")
        for path in sorted(unmapped):
            if not path or path == "unknown":
                continue
            name = os.path.basename(path).replace("-", " ").replace("_", " ")
            branches = git(["for-each-ref", "--sort=-committerdate",
                            "refs/heads", "--format=%(refname:short)",
                            "--count=6"], cwd=path)
            out.append("")
            out.append("  ## %s" % name.title())
            out.append("  - paths: %s" % path)
            if branches:
                out.append("    (recent branches: %s - add a `ticket:` hint "
                           "if they reveal a ticket convention)"
                           % ", ".join(branches.splitlines()[:4]))

    out.append("")
    out.append("Log file for this date: %s" % resolve_log_path(cfg, date))
    if cfg.get("heading"):
        out.append("Append under heading: %s" % cfg["heading"])
    out.append("After the user confirms and the entry is written, run: "
               "python3 \"$ALIBI_SCRIPT\" mark-rolled %s" % date.isoformat())

    print("\n".join(out))
    return 0


# --------------------------------------------------------------------------

COMMANDS = {
    "session-start": cmd_session_start,
    "turn": cmd_turn,
    "session-end": cmd_session_end,
    "note": cmd_note,
    "decline": cmd_decline,
    "status": cmd_status,
    "mark-rolled": cmd_mark_rolled,
    "config": cmd_config,
    "day": cmd_day,
}

HOOK_COMMANDS = ("session-start", "turn", "session-end")


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        print("\nsubcommands: %s" % ", ".join(sorted(COMMANDS)))
        return 0
    command = COMMANDS.get(argv[0])
    if command is None:
        print("unknown subcommand: %s" % argv[0])
        return 1
    return command(argv[1:]) or 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        # Hooks must never surface an error; anything else may.
        if len(sys.argv) > 1 and sys.argv[1] in HOOK_COMMANDS:
            sys.exit(0)
        raise
