# Alibi — design notes

Context for anyone (human or agent) picking this up cold. The code says *what*
it does; this says *why*, and which of the obvious-looking changes are traps.

---

## The problem

Developers report time against tickets and internal areas. Reconstructing that
at the end of a week is guesswork, yet the evidence — which repository, which
branch, which ticket, when, for how long — passes through Claude Code sessions
and is thrown away.

The naive version, "write a log line when the session ends", fails immediately
on a real day:

- several sessions run **in parallel**, so summed durations exceed wall clock;
- wall clock includes lunch, meetings and school runs;
- one ticket is touched **five times** across a day and deserves one line;
- some work has a ticket, some has only a project, some has neither.

A log built that way is noise, and a noisy log gets abandoned in a week.

## The central idea: two layers

**Capture is dumb, automatic and allowed to be messy.**
Hooks append raw records to an append-only journal. Nobody ever reads it by
hand. It is cheap enough to run on every assistant turn.

**Reconcile is deliberate, once a day, and human-confirmed.**
`day` collapses the mess into per-project totals; the agent turns those into
prose; the user approves before anything reaches their work log.

Everything else follows from keeping these separate. If you find yourself
making capture smarter — inferring, summarising, deduplicating at write time —
you are collapsing the layers and will end up with the naive version again.

```
capture (silent, automatic)              reconcile (deliberate, confirmed)
─────────────────────────────            ─────────────────────────────────
SessionStart ─┐                                    /alibi-day
Stop (turn)  ─┼─► ~/.alibi/journal/  ──────────►  aggregate → propose → confirm
SessionEnd   ─┘   YYYY-MM-DD.jsonl                          │
                  (append-only, machine)                    ▼
                                                 ~/.alibi/YYYY-MM.md
                                                 or an Obsidian daily note
```

---

## Division of labour: script vs agent

This is the single most important principle in the codebase.

| The script does | The agent does |
|---|---|
| Records timestamps, paths, branch names | Decides what the work *was* |
| Merges intervals, splits overlaps, rounds | Writes prose, asks the user |
| Reports raw evidence (branches, commits) | Interprets that evidence |
| Arithmetic | Judgement |

**Arithmetic lives in the script** because a model doing interval maths in its
head will quietly get it wrong, and nobody will notice until a timesheet is
wrong. **Judgement lives in the agent** because it has context the script never
will.

### The script never parses ticket identifiers

There is no regex, no configurable pattern, no allow-list. The script records
raw branch names and commit subjects; the agent decides what — if anything —
is a ticket.

This was not the first design. An earlier version matched `[A-Z][A-Z0-9]{1,9}-\d+`,
which also matches `UTF-8`, `ISO-8601`, `CVE-2024-1234` and `RFC-7231`. The fix
was a denylist of non-ticket tokens, and that growing table of exceptions was
the signal that the rule itself was wrong. Trackers name issues in every
imaginable way — `ABC-123`, `#4821`, `sc-9912`, `TASK_77` — and only the agent
can tell a ticket from a standards reference.

**Do not reintroduce ticket parsing.** If a ticket is missing from a report, the
answer is to give the agent better evidence (the report already prints
`branches:` per bucket), not to teach the script a pattern.

`ticket:` in `projects.md` is a free-text *hint* for the agent (`ABC-*`,
`#<number>`, `no tickets, internal`). It is never parsed. `jira:` is accepted
as a synonym so a Jira shop can write what comes naturally.

### First-run discovery is agent-side

Setup evidence — candidate repositories, recent branches, ticket conventions,
Obsidian vaults — is gathered by the agent at setup time, following the
procedure in the `alibi` skill. It used to be gathered by the script
(`scan_repos`, `recent_claude_projects`, `bootstrap_context`, ~250 lines,
injected into context at SessionStart). That was the heaviest block in the
file, home to two of the bugs below, and a duplicate of what the agent can do
with a handful of shell commands once `/alibi-setup` (or the first-run offer)
is running. The SessionStart hook now emits only a short "installed but not
configured" pointer.

**Do not grow discovery back into the script.** If setup drafts come out poor,
improve the evidence-gathering steps in the skill — same division of labour as
tickets: the script announces, the agent investigates.

---

## Why the hooks are shaped this way

Three findings from the harness drove the design. Each is easy to get wrong.

**1. `SessionEnd` cannot involve the model.** It runs a shell command; there is
no agent to write a summary. So an entry with real content *must* come from a
`Stop` hook that blocks once and asks. This is why the nudge exists — it is
mechanism, not preference.

**2. `Stop` fires on every assistant turn**, not once at session end. That makes
it a free heartbeat, which is what gives *active* time instead of "the terminal
was open 09:00–18:00", and what makes parallel sessions separable at all. The
nudge is layered on top, guarded by a per-session marker so it fires at most
once and cannot loop.

**3. `SessionStart` silently never fires without a matcher.** It needs
`"matcher": "startup|resume|clear|compact"`. This is documented the hard way in
`ai-marketplace/docs/claude-code-plugin-hooks.md`; `lnd-liferay-upgrade` omits
it and is probably broken as a result.

Other harness constraints that bit during development:

- `hooks/hooks.json` is **auto-discovered**. Also referencing it from
  `plugin.json` causes "Duplicate hooks file detected".
- `systemMessage` is user-visible; `hookSpecificOutput.additionalContext` is
  agent-only. Claude Code reads both `additional_context` and
  `hookSpecificOutput` **without deduplication**, so emit exactly one form.
- Hooks load **at startup only**. Config and hook edits need a restart, and the
  setup flow must say so.
- `AskUserQuestion` allows at most **4 options** per question. `lnd-core` had to
  split a question for this reason. Never route a project list through it.
- `$ALIBI_SID` and `$ALIBI_SCRIPT` are exported at SessionStart via
  `$CLAUDE_ENV_FILE`, so later Bash calls in the session can find them.

---

## Data

Everything lives in **one directory**, `~/.alibi/` (override `$ALIBI_HOME`).

```
~/.alibi/
├── projects.md              config + project map (user-edited)
├── journal/YYYY-MM-DD.jsonl raw records, append-only
├── state/<session>.json     per-session counters; pruned after 7 days
├── .declined                setup was declined; stay silent forever
└── YYYY-MM.md               reconciled log (path comes from config)
```

`$CLAUDE_PLUGIN_DATA` was considered for the journal and rejected: an
unreconciled journal is worth keeping across an uninstall, and one visible
directory is easier to explain to a colleague than two hidden ones.

### Journal records

```jsonc
{"t":"session","at":"…","sid":"…","cwd":"…","repo":"…","branch":"…","project":"…"}
{"t":"beat","at":"…","sid":"…"}          // one per assistant turn
{"t":"note","at":"…","sid":"…","ticket":"…","project":"…","bullets":["…"]}
{"t":"note","at":"…","sid":"…","skip":true}   // nothing worth reporting
{"t":"end","at":"…","sid":"…"}
{"t":"rollup","at":"…","date":"YYYY-MM-DD"}   // day reconciled
```

Beats carry only `sid`; everything else is on the session record. Records are
never rewritten — the journal is append-only, which is what makes concurrent
sessions safe without locking.

A session started before midnight has its `session` record in the *previous*
day's file, so `day` always loads `DATE-1` and `DATE` and filters beats by
timestamp.

### `projects.md` is deliberately dual-audience

Frontmatter and `paths:` are parsed mechanically; `note:` and free prose are
read by the agent. One file, human-editable, no separate config format.

---

## The aggregation algorithm

In `cmd_day`, in order. Each step exists for a reason.

1. **Beats → activity blocks.** Consecutive beats form a block; a gap longer
   than `idle_gap_minutes` (20) ends it. Each block is extended backwards by
   `lead_in_minutes` (3) to account for time spent writing the prompt before
   the turn ran. Lead-in can push a block into its predecessor, so blocks are
   clamped to stay disjoint.
2. **Overlap splitting.** All sessions' blocks go onto one timeline. Where N
   sessions are live in a segment, each is credited `1/N` of it. The total
   overlapped minutes are reported separately, so the split is *visible* rather
   than silently baked in. v1 splits evenly; weighting by beat density is a
   plausible improvement, but even-split is explainable and that matters more.
3. **Session → project.** Longest-prefix match of the repo root against
   `paths`. An explicit `project` on a note always wins.
4. **Rounding uses largest-remainder**, not independent rounding. Rounding each
   bucket separately produces reports where three 15-minute lines claim to total
   50 minutes. The parts must sum to the whole or the user loses trust in the
   entire report.
5. **Two columns.** *Actual* is measured. *Normalized* scales the proportions
   to `target_hours` for timesheets that demand a full day. **Normalization is
   suppressed below 50% of target** — stretching 20 measured minutes into 8
   hours is not rounding, it is a fabricated number that could reach a
   timesheet. It says why it was suppressed rather than hiding the column.
6. **Git evidence.** That day's commits per repository, filtered to the user's
   `git config user.email`, as raw material for the detail bullets.

---

## Behavioural rules that must not be broken

These are the difference between a plugin colleagues keep and one they
uninstall in a week.

- **Fail open, always.** Every hook path exits 0 and stays silent on any
  unexpected condition. `mempalace` returns 1 when its runtime is missing and
  prints an error on *every* Stop; that is the counterexample. If `python3` is
  absent, `hooks/run.sh` exits 0 and the plugin simply does nothing.
- **Inert until configured.** No journal is written before `projects.md`
  exists. Decline is permanent, recorded in `.declined`, and never raised again;
  `/alibi-setup` is the way back.
- **Never interrupt working sessions with reporting questions.** Unmapped
  directories are recorded silently and raised at reconciliation, when the user
  is already thinking about timesheets. The one-per-session note nudge is the
  only interruption, and it is capped and configurable (`nudge: false`).
- **Nothing is written to the work log without explicit approval.** The agent
  drafts; the user confirms; only then does `mark-rolled` run.
- **Never invent a ticket.** An entry with an honest gap beats one with a
  plausible-looking wrong number.
- **No network, no credentials, no tracker access, nothing written into user
  repositories.** The journal records timestamps, paths and branch names — never
  prompts, code, or conversation content. This is a distributed plugin; the
  privacy claim in the README must stay true.

---

## Bugs found during development

Recorded because each is easy to reintroduce.

**Dedupe set collapse.** Worktree-collapsing added `cwd` to a `seen` set, then
rejected `root` if it was in `seen` — but for a normal repository those are the
same path, so *every plain git repo* was silently dropped from the recency
list. Only worktrees survived. Fixed with separate `seen_cwd` / `seen_root`.
(The script-side scanner has since been deleted — discovery is agent-side now —
but the lesson survives as the worktree-collapsing step in the skill.)

**Filesystem-root crawl.** With `cwd=/tmp`, the first-run scan took
`dirname(cwd)` as a root and walked `/`. Scan roots are now confined to the
user's home directory. (Also deleted with the scanner; the skill now says
"never scan `/`, never crawl the whole home directory".)

**Undefined variable behind fail-open.** `cmd_session_start` referenced a
`ticket` variable left over from the deleted ticket-regex era. In any git repo
with a branch — i.e. every real session — it raised `NameError`, the fail-open
handler swallowed it, and no context was emitted: capture kept working, but
the agent never learned Alibi existed. Fail-open hides exactly this class of
bug, so the happy path needs a positive check, not just silent error paths:
run `session-start` with a configured `ALIBI_HOME` *inside a git repo* and
assert that `<alibi>` context is actually printed.

**Normalizing a tiny day.** A 20-minute day reported 8h in the normalized
column. Hence the 50% floor.

**Worktrees as new projects.** Without `--git-common-dir` collapsing, every
worktree looks like an unmapped project. This matters a lot for anyone who uses
worktrees heavily.

**Ticket regex false positives.** See above — deleted rather than patched.

---

## Deliberately not done

- **Jira/tracker write-back.** Needs credentials, and is risky to distribute
  company-wide. If asked, say it is out of scope.
- **Weekly rollup** (`/alibi-week`) and **backfill** for days before install.
  Both are plausible v2 features.
- **Beat-density weighting** for overlap splits — see step 2 above.
- **Prompt text in the journal.** It would improve recall considerably and was
  explicitly rejected: prompts on disk in plaintext is the wrong trade for a
  tool handed to colleagues.

---

## Testing

The aggregation is the only part with real correctness risk, and it is testable
without launching Claude Code:

```bash
python3 tests/make_fixture.py /tmp/alibi-test
ALIBI_HOME=/tmp/alibi-test python3 scripts/alibi.py day 2026-08-01
```

The fixture covers two sessions overlapping by 90 minutes, a 40-minute gap
inside a session, a 2-minute session that must be dropped, a repository absent
from `projects.md`, and a session crossing midnight. Expected: 56m overlap split
evenly, 4h27m active within a 14h58m span, line items summing to exactly 4h30m
actual and exactly 8h normalized.

Fail-open paths worth re-checking after any change:

```bash
echo -n '' | bash hooks/run.sh turn                  # empty stdin
echo 'notjson{' | bash hooks/run.sh turn             # malformed stdin
ALIBI_HOME=/nonexistent bash hooks/run.sh session-end </dev/null
```

All must exit 0 and print nothing.

The inverse matters just as much — fail-open swallows real bugs (see
"Undefined variable behind fail-open" above), so check the happy path
*positively*: from inside a git repository, with a configured `ALIBI_HOME`,
`session-start` must print `<alibi>` context, not exit silently.

```bash
cd /some/git/repo && echo '{"session_id":"t","cwd":"'$PWD'"}' \
  | ALIBI_HOME=/tmp/alibi-test python3 scripts/alibi.py session-start
```

End-to-end still requires an install and a restart:

```
/plugin marketplace add /path/to/alibi
/plugin install lnd-alibi@alibi-dev
```

Check `/hooks` lists all three, that a `session` record and one `beat` per turn
appear, that the nudge fires exactly once, and that a second Stop does not
re-nudge.

---

## Publishing to `ai-marketplace`

Per that repo's `NAMING-CONVENTIONS.md`:

1. Delete `.claude-plugin/marketplace.json` — local development only.
2. Copy the folder to `plugins/lnd-alibi/`.
3. Add entries to **both** catalogs: `.claude-plugin/marketplace.json` (string
   `source`) and `.agents/plugins/marketplace.json` (object `source`, plus
   `policy` and `category: "Productivity"`).
4. Add a `CODEOWNERS` line.
5. Run the `marketplace-plugin-auditor` skill; it must report no ERRORs.

Version bumps must land in **both** manifests, or `/plugin marketplace update`
is a no-op for existing users.
