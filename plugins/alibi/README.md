# Alibi

Work-log capture and daily reconciliation for Claude Code.

Alibi records which repository, branch and ticket you worked on and for how
long, then turns a messy day — parallel sessions, meetings, five visits to the
same ticket — into one timesheet-ready entry per project.

## What it actually does

Two layers, deliberately separate:

**Capture** is automatic and silent. A hook appends a line to a raw journal on
every assistant turn. This gives *active* time rather than "the terminal was
open from 09:00 to 18:00", and it is what makes two sessions running at once
separable afterwards.

**Reconcile** is deliberate. `/alibi-day` collapses a day into per-project
totals, splits time that overlapping sessions both claim, pulls that day's
commits as raw material, and proposes an entry. Nothing reaches your work log
until you have seen it and said yes.

```
## 2026-08-01

- **09:00–12:00** (2h) · `ABC-123` · client-web
  - Implemented invoice PDF export
  - Fixed date parsing in summary view
- **09:45–11:15** (1h15m) · Internal development
  - Added the Alibi plugin scaffold and catalog entries
```

## Install

```
/plugin marketplace add jankc/jank-plugins
/plugin install alibi@jank-plugins
```

(From a local checkout, `/plugin marketplace add /path/to/jank-plugins` works
the same way.)

Restart, and the first session will offer to set you up. It proposes a draft
configuration built from where you have actually been working — recent Claude
Code sessions, git repositories nearby, ticket prefixes read off your branches,
and any Obsidian vault it spots — which you then correct. It asks once. Decline
and it stays silent permanently; `/alibi-setup` is how you come back.

**Alibi records nothing at all until it is configured.**

## Commands

| Command | Purpose |
|---|---|
| `/alibi-setup` | Set up or reconfigure projects and log destination |
| `/alibi-note` | Record what this session worked on, right now |
| `/alibi-day [date]` | Reconcile a day into the work log |

Once per session, after real work, Claude will ask to record a note before
finishing. Set `nudge: false` in your config to turn that off and rely on
`/alibi-note` instead.

## Configuration

One file, `~/.alibi/projects.md` — frontmatter is settings, sections are
projects. See `templates/projects.md` for the annotated version.

```markdown
---
log: "~/.alibi/{yyyy}-{mm}.md"
target_hours: 8
---

## Client web
- ticket: ABC-*
- paths: ~/dev/client-web

## Internal tooling
- paths: ~/dev/internal
- report-as: Internal development
```

Alibi has no idea what a ticket looks like, and does not try to guess — it
records raw branch names and commit subjects and lets Claude work it out, so
`ABC-123`, `#4821` and `sc-9912` all work without configuration. The `ticket:`
line is just a free-text hint, kept up to date for you as conventions become
clear.

**New projects are never created behind your back** — unmapped directories are
raised during `/alibi-day`, with a draft section ready to accept or reject, so
the question arrives when you are thinking about reporting rather than
mid-task.

Git worktrees resolve to their main checkout, so one `paths` entry covers all
of them.

Obsidian users: point `log` at your daily note and set a heading.

```yaml
log: "~/Obsidian/Vault/Daily/{yyyy}-{mm}-{dd}.md"
heading: "## Work log"
```

## Reported time is measured, not invented

The daily report shows two columns. **Actual** is measured active time, rounded
to 15 minutes. **Of 8h** scales those proportions to fill a target day, for
timesheets that demand one.

Time claimed by two sessions at once is split evenly between them and the
overlap is reported, so you can see it rather than having it quietly folded in.
When measured time falls below half the target, the normalized column is
suppressed rather than stretching 20 minutes into a working day.

Alibi only sees what happened in Claude Code. Meetings, code review and
everything else are yours to add.

## Privacy

Everything is local, and stays on your machine.

- **No network. No credentials. No telemetry.**
- **No issue-tracker access.** Ticket identifiers are read off your branch
  names and commit messages. Nothing is ever sent to a tracker or read from it.
- **Nothing is written into your repositories.** Alibi owns exactly one
  directory, `~/.alibi/` (override with `$ALIBI_HOME`). Delete it and Alibi
  has forgotten everything.
- **The journal records timestamps, repository paths and branch names** — plus
  the notes Claude writes and you approve. It does **not** record your prompts,
  your code, or conversation content.
- Inert until configured, and permanently silent if you decline.

## Requirements

`python3` (standard library only) and `git`. If `python3` is missing the hooks
exit silently and the plugin does nothing, rather than erroring on every turn.

## Development

**Read [`DESIGN.md`](DESIGN.md) first** — it covers why the plugin is shaped
this way, the harness constraints behind the hook design, the rules that must
not be broken, and the mistakes already made and fixed.

```bash
python3 tests/make_fixture.py /tmp/alibi-test          # synthetic journal
ALIBI_HOME=/tmp/alibi-test python3 scripts/alibi.py day 2026-08-01
```

The fixture covers overlapping parallel sessions, a meeting-sized gap, a
too-short session, an unmapped repository and a session crossing midnight.

Marketplace notes are at the end of [`DESIGN.md`](DESIGN.md).
