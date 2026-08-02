---
name: alibi
description: Record and reconcile work for time reporting. Use when logging what was worked on, when the Alibi Stop hook asks for a session note, when reconciling a day into a work log ("what did I work on", "log this", "reconcile yesterday", "alibi"), when setting Alibi up for the first time, when a ticket is mentioned and it is unclear which project the current work should be reported under, or when the user asks how Alibi works or what one of its settings means.
---

# Alibi — work-log capture and reconciliation

Alibi turns Claude Code sessions into a timesheet-ready record. It has two
layers, and keeping them separate is the whole point:

- **Capture** is automatic and messy. Hooks append raw records to
  `~/.alibi/journal/YYYY-MM-DD.jsonl`. Nobody reads that file by hand.
- **Reconcile** is deliberate. `day` collapses the mess into per-project
  totals; you turn those into prose and the user confirms before anything is
  written to their work log.

Everything is local. Never contact an issue tracker, never send anything
anywhere.

## Answering questions about Alibi

`HELP.md`, next to this file, is the user-facing guide: quick start, command
and configuration reference, how time is measured, privacy, FAQ. When the
user asks what Alibi is, what a setting means, why something was or was not
recorded, or how to change its behaviour, read it and answer from it — do not
improvise from memory. `/alibi-help` renders it directly.

## Running the script

Use `$ALIBI_SCRIPT` (exported at session start):

```bash
python3 "$ALIBI_SCRIPT" <subcommand>
```

If `$ALIBI_SCRIPT` is empty, the slash commands pass the path explicitly.
Subcommands: `note`, `day`, `status`, `config`, `mark-rolled`, `decline`.

## Working out which project or ticket

In priority order. Stop at the first that gives a confident answer:

1. What the user said in this session — always wins.
2. A `note` already recorded for this session.
3. The project whose `paths` in `~/.alibi/projects.md` contain the working
   directory. The session-start context already tells you this.
4. A ticket identifier in the branch name — whatever form this team uses.
   `feature/ABC-123-pdf`, `fix/#4821`, `sc-9912-retry` are all plausible;
   the project's `ticket:` hint tells you what to expect.
5. Ticket identifiers in the day's commit messages.
6. Ask the user. One short question, with your best guess as the default.

**Never invent a ticket key.** If you cannot find one, record the project with
no ticket — an entry with an honest gap beats an entry with a plausible-looking
wrong number in it. Some projects legitimately have no ticket at all; those
carry `report-as:` in `projects.md` instead.

### Tickets are yours to judge; new projects are asked about

**The script never parses ticket identifiers.** It has no pattern, no
allow-list, no assumption that tickets look like `ABC-123`. It hands you raw
branch names and commit subjects; deciding what is a ticket is your job,
because only you can tell `ABC-123` from `UTF-8` or recognise that this team
writes `#4821` or `sc-9912`.

Consequently:

- **Ticket hints are yours to maintain.** When you work out how a project
  identifies its tickets, add or update a `ticket:` line on that project in
  `projects.md` — free text, whatever describes the convention (`ABC-*`,
  `#<number>`, `no tickets, internal`). Do this silently when confident; it is
  enrichment of a project the user already wrote.
- **New projects are only ever proposed interactively** — during `/alibi-day`
  or `/alibi-setup`. If the working directory is not in `projects.md`, note it
  and carry on. **Do not interrupt a working session to ask about it.** The
  user is thinking about their code, not their timesheet; reconciliation is
  when that question is welcome.

## Writing a session note

When the Stop hook asks for a note, or the user says "log this":

1. Work out the ticket/project as above.
2. Write 2–4 bullets describing **what changed**, not what happened
   conversationally. "Fixed date parsing in the invoice summary" — not
   "investigated an issue the user reported and discussed options".
3. Record it, then tell the user in one line and stop:

```bash
python3 "$ALIBI_SCRIPT" note \
  --ticket ABC-123 --project "Client web" \
  --bullet "Implemented invoice PDF export" \
  --bullet "Fixed date parsing in summary view"
```

Omit `--ticket` when there is genuinely no ticket. If the session produced
nothing worth reporting — a question answered, a file read — record that
honestly instead, which also stops the nudge repeating:

```bash
python3 "$ALIBI_SCRIPT" note --skip
```

Keep this to one short line to the user. The nudge fires at most once per
session; do not turn it into a conversation.

## Personal and non-work time

Projects marked `report: false` in `projects.md` are personal, not work: their
time is captured, but they are never nudged for a note, never enter the totals
or the normalized column, and `/alibi-day` lists them only under
`NOT REPORTED`. Leave them out of the log entry.

When the user says a session was personal ("that was my own stuff"), record a
note against a `report: false` project — an explicit project on a note always
beats the directory mapping, so this also reroutes a personal session that
happened inside a work directory:

```bash
python3 "$ALIBI_SCRIPT" note --project "Own stuff" --bullet "personal tinkering"
```

If no `report: false` project exists yet, offer to add one (a section with
just `- report: false` is enough; `paths` is optional) rather than inventing a
work label for personal time.

## Reconciling a day

```bash
python3 "$ALIBI_SCRIPT" day 2026-08-01     # or: yesterday, today
```

The report gives you measured active time per project, with overlapping
parallel sessions already split, plus that day's commits as raw material.

Then:

1. **Show the user the table.** Both columns, actual and normalized. Do not
   pick for them — actual is honest, normalized fills a target day. If the
   normalized column is suppressed, say why rather than hiding it.
2. **Resolve what the report flags.** Under `PROPOSED PROJECT ADDITIONS` the
   report drafts a `projects.md` section for each unmapped directory that
   produced work. Show each draft, let the user rename or reject it, and append
   the accepted ones to `projects.md` — this is the one moment where asking
   about new projects is appropriate. Buckets with no notes: reconstruct from
   the commits, and say that is what you did. Anything under `NOT REPORTED`
   is personal time — it may be mentioned in conversation, but it never goes
   into the entry.
3. **Draft the entry** in the format below and show it before writing.
4. **Write it** to the log path named at the bottom of the report. Append; if
   a `heading` is configured, append under it; create the file with a
   `# YYYY-MM` title if it does not exist. **Never rewrite an existing day** —
   if the date is already present, show the user the conflict and ask.
5. **Mark it done**: `python3 "$ALIBI_SCRIPT" mark-rolled 2026-08-01`

Only run `mark-rolled` after the entry is actually written and the user has
confirmed it. It is what stops the day being nudged again.

### Entry format

```markdown
## 2026-08-01

- **09:00–12:00** (2h) · `ABC-123` · client-web
  - Implemented invoice PDF export
  - Fixed date parsing in summary view
  - 3 commits, 7 files
- **09:45–11:15** (1h15m) · Internal development
  - Added the Alibi plugin scaffold and catalog entries
```

Times come from the report's DETAIL section. The third bullet is optional
volume context — include it only when it adds something.

## First-run setup

When `~/.alibi/projects.md` does not exist, session start tells you Alibi is
unconfigured — and nothing more. Gathering the evidence is your job, and it is
what makes setup painless: do not ask the user to describe their projects from
memory. Build a draft from evidence and let them correct it.

### Gather the evidence first

A few quick commands, a few seconds total — not an exhaustive survey:

1. **Recently worked-in directories** — the strongest signal. Claude Code
   session history lives under `~/.claude/projects/` (respect
   `$CLAUDE_CONFIG_DIR` if set). Take the most recently modified entries;
   each one's newest `*.jsonl` transcript records the real working directory
   as `"cwd"` in its first few lines. The directory names themselves are a
   lossy encoding of the path — read the transcript, do not decode the name.
2. **Git repositories where code usually lives**: the parent of the current
   directory, plus common roots such as `~/dev`, `~/projects`, `~/src`,
   `~/code`, `~/work`, `~/repos` — e.g.
   `find ~/dev -maxdepth 3 -type d -name .git 2>/dev/null`. Never scan `/`,
   and never crawl the whole home directory.
3. **Discard noise**: temp and scratchpad paths, hidden directories, the home
   directory itself. Collapse each candidate onto its main checkout with
   `git rev-parse --path-format=absolute --git-common-dir` so a worktree and
   its parent repository count as one project, not two.
4. **Collect ticket evidence per candidate**: recent branches
   (`git for-each-ref --sort=-committerdate refs/heads
   --format='%(refname:short)' --count=8`) and the user's recent commit
   subjects (`git log --author="$(git config user.email)" --since=30.days
   --format=%s -n 8`). Read them yourself to infer each project's ticket
   convention — Alibi assumes no format.
5. **Obsidian**: a directory containing `.obsidian` is a vault — offer its
   daily note as the log destination directly instead of asking in the
   abstract.

### Then run the dialog

1. Say in two sentences what Alibi does and that it is entirely local.
2. Ask the structured choices with `AskUserQuestion` — at most two questions,
   maximum 4 options each:
   - Where the log should go: `~/.alibi/{yyyy}-{mm}.md` (monthly file) or an
     Obsidian daily note (then ask for the daily-note path, and set `heading`).
   - `target_hours` for the normalized column, or 0 to disable it.
3. **Draft the whole `projects.md`.** Combine every source you have:
   - the recently-worked-in directories from session history — the strongest
     evidence; lead with these
   - the branch names and commit subjects you collected — the ticket
     conventions you inferred become `ticket:` hints
   - **your own knowledge**: your memory directory and `MEMORY.md`, projects
     the user named earlier in this conversation, `CLAUDE.md` files in the
     candidate repositories, and directory naming that groups repos into one
     client or product

   Group related repositories into a single project rather than listing one
   section per repo — a frontend and backend for the same client are one
   reporting line. Show the draft, let the user rename projects, drop
   irrelevant ones and add what you missed. Do not force the project list
   through `AskUserQuestion`.
4. Write `~/.alibi/projects.md`, then tell them capture starts next session —
   hooks only load at startup.

If they decline or want to do it later, run
`python3 "$ALIBI_SCRIPT" decline` and never raise it again. `/alibi-setup`
is how they come back. A colleague nagged every session uninstalls the plugin.

## Configuration reference

`~/.alibi/projects.md` — frontmatter is settings, sections are projects.

| Key | Default | Meaning |
|---|---|---|
| `log` | `~/.alibi/{yyyy}-{mm}.md` | Output path; `{yyyy}` `{mm}` `{dd}` are substituted |
| `ticket` (per project) | *(none)* | Free-text hint describing this project's ticket convention |
| `heading` | *(none)* | Append under this heading if present in the file |
| `idle_gap_minutes` | 20 | A gap longer than this ends an activity block |
| `min_session_minutes` | 5 | Shorter sessions never nudge and never report |
| `min_turns` | 3 | Minimum turns before a session counts |
| `round_minutes` | 15 | Reporting granularity |
| `target_hours` | 8 | Normalized column; 0 disables it |
| `lead_in_minutes` | 3 | Time credited before each block for writing the prompt |
| `nudge` | true | Whether the Stop hook asks for a session note |

Project sections take `ticket:` (free-text hint about how this project's
tickets are identified; `jira:` is accepted as a synonym), `paths:`
(comma-separated), `report-as:` (the label to use in the log when it differs
from the section name), `report:` (`false` marks a personal project — captured
but never nudged, never reported) and `note:` (free text you should read when
deciding how to report the work).

Git worktrees resolve to their main checkout, so one `paths` entry for the
repository covers every worktree of it.

## Changing Alibi itself

If you are asked to modify the plugin rather than use it, read `DESIGN.md` at
the plugin root first. It records the reasoning behind the two-layer design,
why the script deliberately never parses ticket identifiers, and which
obvious-looking changes have already been tried and reverted.

## What Alibi does not do

It does not touch any issue tracker, log time anywhere remote, or record
prompt or code
content — only timestamps, repository paths, branch names, and the notes you
write. If a user asks for tracker write-back, tell them it is deliberately out of
scope.
