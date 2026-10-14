# Alibi — guide

Alibi records which repository, branch and ticket you worked on and for how
long, then turns a messy day — parallel sessions, meetings, five visits to the
same ticket — into one timesheet-ready entry per project. Everything stays on
your machine.

It has two layers, and the split is the whole idea:

- **Capture** is automatic and silent. Hooks write timestamps to a journal on
  every assistant turn. You never look at it.
- **Reconcile** is deliberate. `/alibi-day` collapses a day into per-project
  totals and proposes a log entry. Nothing is written until you approve it.

## Quick start

1. `/alibi-setup` — Claude gathers your recent projects and proposes a
   configuration; you correct it. One file: `~/.alibi/projects.md`.
2. Restart Claude Code (hooks load at startup). Capture begins.
3. Work normally. Once per session, after real work, Claude asks to record a
   short note of what changed.
4. Next morning: `/alibi-day yesterday`. Review the table, approve the entry,
   done.

Alibi records **nothing** until it is configured, and stays permanently silent
if you decline setup.

## Commands

| Command | Purpose |
|---|---|
| `/alibi-setup` | Set up or reconfigure projects and log destination |
| `/alibi-note` | Record what this session worked on, right now |
| `/alibi-day [date]` | Reconcile a day into the work log (`yesterday`, `today`, `2026-08-01`) |
| `/alibi-help [topic]` | This guide |

## Configuration

One file, `~/.alibi/projects.md`. Frontmatter holds settings, `##` sections
are projects. Edits take effect next session.

| Setting | Default | Meaning |
|---|---|---|
| `log` | `~/.alibi/{yyyy}-{mm}.md` | Where entries go, newest day on top; `{yyyy}` `{mm}` `{dd}` are substituted |
| `heading` | *(none)* | Insert under this heading — for Obsidian daily notes |
| `idle_gap_minutes` | 20 | A longer silence ends an activity block (meeting, lunch) |
| `min_session_minutes` | 5 | Shorter sessions never nudge and never report |
| `min_turns` | 3 | Minimum turns before a session counts |
| `round_minutes` | 15 | Reporting granularity |
| `target_hours` | 8 | Normalized column scales to this; 0 disables it |
| `lead_in_minutes` | 3 | Credited before each block, for writing the prompt |
| `nudge` | true | Ask for a session note before finishing |

Each project section can carry:

| Field | Meaning |
|---|---|
| `paths:` | Comma-separated directories mapping work to this project — the only field that has to be right. Worktrees resolve to their main checkout, so one entry covers all of them. |
| `ticket:` | Free-text hint about this project's ticket convention (`ABC-*`, `#<number>`, `no tickets`). Never parsed — Claude reads it. `jira:` works as a synonym. |
| `report-as:` | Label used in the log when it differs from the section name |
| `report:` | `false` marks a personal project — see below |
| `note:` | Anything Claude should know when reporting this work |

## Personal time — keeping your own stuff off the report

Mark a project `report: false`:

```markdown
## Own stuff
- paths: ~/dev/personal
- report: false
```

Its time is captured but never reported: no note nudges, excluded from totals
and the normalized column, shown only as a `NOT REPORTED` line in
`/alibi-day` so you can see the exclusion happened.

For a one-off personal session inside a work directory, tell Claude it was
personal — a note recorded against any `report: false` project reroutes that
session off the log.

## How time is measured

- Submitting a prompt leaves a timestamp, and so does the end of the response
  it produces. Consecutive timestamps form an activity block; a gap over
  `idle_gap_minutes` ends it — that gap is your meeting or lunch, and it is
  not counted. So you get *active* time, not "the terminal was open
  09:00–18:00". The stretch between your prompt and the end of its response
  always counts, however long Claude worked on it.
- Each block is extended `lead_in_minutes` backwards, crediting the time you
  spent writing the prompt.
- When two sessions run at once, each minute is split evenly between them —
  an hour of parallel work is 30 + 30, not 60 + 60. The report says how much
  was split.
- Line items are rounded to `round_minutes` so that they add up exactly to
  the total — no tables claiming three 15-minute lines make 50 minutes.
- The report shows two columns: **Actual** (measured) and **Of 8h** (the same
  proportions scaled to `target_hours`, for timesheets that demand a full
  day). If less than half the target was measured, the scaled column is
  suppressed rather than stretching 20 minutes into a working day — Alibi
  does not invent numbers.
- Meetings, code review and everything outside Claude Code are yours to add
  when you approve the entry.

## Privacy and data

- **No network, no credentials, no issue-tracker access, no telemetry.**
- The journal records timestamps, repository paths, branch names and the
  notes you approve — never your prompts, your code, or conversation content.
- Everything lives in one directory: `~/.alibi/` (override with
  `$ALIBI_HOME`). Delete it and Alibi has forgotten everything.
- Nothing is ever written into your repositories.

## FAQ

**Nothing is being recorded.**
Alibi is inert until `~/.alibi/projects.md` exists — run `/alibi-setup`. If
you just created or edited it, restart: hooks and config load at startup.

**A day is missing from `/alibi-day`.**
Sessions under `min_turns` turns or `min_session_minutes` minutes are
dropped as noise. Also check the date argument — a session that crossed
midnight is counted on the days the time actually fell.

**The nudge annoys me.**
Set `nudge: false` and record notes yourself with `/alibi-note`. Without any
notes, `/alibi-day` still measures time and falls back to that day's commits
for the description.

**Work landed under the wrong project.**
Fix the `paths:` lines — longest match wins. Directories in no project are
raised as drafts during `/alibi-day`, never guessed at silently.

**The ticket is wrong or missing.**
Alibi never parses tickets; Claude reads them off branch names and commit
subjects. Give the project a `ticket:` hint describing your convention, or
just say the right ticket when reconciling.

**Claude asks permission every time Alibi records or reconciles.**
Everything Alibi touches lives in `~/.alibi`, outside your project, so each
session prompts anew. Add these to the `"permissions": { "allow": [...] }`
array in `~/.claude/settings.json` (merge with what is already there):

```json
"Read(~/.alibi/**)",
"Edit(~/.alibi/**)",
"Bash(python3 \"$ALIBI_SCRIPT\" *)"
```

The Bash rule is safe to allow: the script is local-only, writes nowhere but
`~/.alibi`, and never touches the network or an issue tracker. Takes effect
in new sessions.

**I declined setup and changed my mind.**
`/alibi-setup` — it removes the decline marker.

**I want to stop for a while / forever.**
`nudge: false` quiets it; renaming `~/.alibi/projects.md` disables capture;
deleting `~/.alibi/` erases everything. Uninstalling the plugin removes the
hooks but leaves `~/.alibi/` for you to keep or delete.
