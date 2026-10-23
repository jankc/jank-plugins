---
name: ship-openspec-change
description: Autonomously drive one or more existing OpenSpec changes from proposal to done — fast-forward the remaining artifacts (Opus), implement with a Sonnet high-effort subagent, triage the diff (S/M/L) to size the review, verify (Opus) + multi-agent code review (Opus) + a high-level senior adviser review (Fable) in parallel, apply fixes with a cold Opus high-effort subagent and have Fable re-check them, then summarize. Runs multiple changes sequentially. Use when the user names one or more existing OpenSpec changes and wants them implemented / shipped end-to-end.
license: MIT
compatibility: Requires the openspec CLI, the opsx skills, and the pr-review-toolkit plugin (its review agents). Uses the user-level `sonnet-high` and `opus-high` agents when present.
metadata:
  author: jank
  version: "1.6"
---

# OpenSpec: Ship Change

You are the **orchestrator** for an autonomous implementation loop over one or more **already-existing** OpenSpec changes. A proposal (at minimum) already exists for each — this skill does **not** create changes from scratch.

Run the whole pipeline **autonomously**. Do not pause for confirmation between phases. Only stop and ask the user if something is genuinely blocked (missing change, tool unavailable, ambiguous change name with multiple candidates, or a phase fails in a way you cannot resolve).

## Input

One or more change names (kebab-case), passed as arguments, e.g.
`ship-openspec-change add-user-avatars migrate-settings-to-v2`.

- **One name** → run the pipeline once for it.
- **Multiple names** → process them **sequentially**, in the order given (see "Running multiple changes" below).
- **No name** → run `openspec list --json`; if exactly one change is in progress, use it; otherwise use **AskUserQuestion** to let the user pick (allow selecting several). Do not guess.
- **Optional `--tier S|M|L`** → overrides the Phase 3 triage for every change in this run. Announce the forced tier in the summary and carry on; do not ask.

For each change you process, set `CHANGE=<name>` and run Phases 1–5 for it before moving to the next.

## Running multiple changes (sequential)

When given a list `CHANGES = [c1, c2, …]`:

1. **Validate up front**: run `openspec list --json` (or `openspec status --change <c> --json` per item) and confirm every named change exists. Report any unknown names and drop them before starting; if none remain, stop.
2. **Order**: process in the order the user gave them (they may encode dependencies). Do not reorder or parallelize across changes — implementation, verify, and fixes touch the working tree, so overlapping changes would collide. (The verify + review *within* a single change still run in parallel; that's Phase 3.)
3. **Per-change loop**: for each `CHANGE`, run Phases 1–5. Emit the Phase 5 per-change summary before starting the next one, so progress is visible incrementally.
4. **On hard failure**: stop the sequence at the failing change (a later change may depend on it). Report which change failed, at which phase, with the error; list the changes already completed and the ones **not started**, and give the manual command to resume from the failure. Do not silently continue.
5. **Final roll-up**: after the last change (or after stopping), write a single combined summary — a one-line status per change (shipped / fixed-with-residuals / failed / skipped) followed by the individual Phase 5 summaries.

Everything below describes the pipeline for a **single** `CHANGE`.

## Orchestration rules (read before starting)

- **Only the Phase 3c adviser review and its Phase 4 re-check of the fixes run on Fable.** Every other subagent runs on Opus or Sonnet as stated in its phase; set `model` (or use an agent type that pins it) on every `Agent` call so nothing inherits Fable by accident.
- **Implementation uses a fresh Sonnet subagent at high effort** — `Agent` with `subagent_type: "sonnet-high"` (pins `model: sonnet`, `effort: high`). If that agent type is not available, use `subagent_type: "general-purpose"` with `model: "sonnet"` and `effort: "high"`.
- **Opus subagents** (`Agent` with `model: "opus"`, `subagent_type: "general-purpose"`) do the spec fast-forward and the verify pass. Tell each one, in its prompt, to invoke the relevant skill via the **Skill** tool and to return a structured result.
- **Code review is a fan-out of `pr-review-toolkit` agents** (Phase 3b), launched by YOU in parallel, **every one of them pinned to `model: "opus"`**. Pass each reviewer the diff scope explicitly and require structured findings back. Do not wrap them in another subagent, and do not use an external review service.
- **The fix pass uses a fresh (non-fork) Opus subagent at high effort** — `Agent` with `subagent_type: "opus-high"` (or `general-purpose` with `model: "opus"`, `effort: "high"` if that type is unavailable). "Cold" means no inherited conversation context: it gets only the change name, repo paths, and the consolidated findings list.
- Keep the main context lean: subagents return **compact structured summaries**, not raw dumps.

---

## Phase 1 — Ensure the change is fully specified

1. Read status:
   ```bash
   openspec status --change "$CHANGE" --json
   ```
   If the command errors (change not found), stop and tell the user.

2. Decide if it's apply-ready:
   - **Apply-ready** when `isComplete` is `true`, i.e. every artifact listed in `applyRequires` has `status: "done"` in `artifacts`.
   - If apply-ready → skip to Phase 2.

3. If **not** apply-ready, spawn an **Opus** subagent to fast-forward the remaining artifacts:
   - `Agent` with `model: "opus"`, `subagent_type: "general-purpose"`.
   - Prompt it to: invoke the OpenSpec fast-forward skill for this change — `Skill(opsx:ff)` with args `"$CHANGE"` (equivalently the `openspec-ff-change` skill) — generating all artifacts needed for implementation (proposal → design → specs → tasks as required by `applyRequires`). It must NOT start implementation. Ask it to return: the list of artifacts it created/completed and any assumptions or open questions.

4. Re-run `openspec status --change "$CHANGE" --json` and confirm `isComplete: true`. If still incomplete after one fast-forward pass, surface the blocking artifact(s) to the user and stop.

## Phase 2 — Implement (Sonnet, high effort)

Nothing is committed during a run, so earlier changes in the same run and any work that was already uncommitted share the working tree with this change. Before spawning the implementer, snapshot the baseline so this change's own files can be told apart later:

```bash
git rev-parse HEAD            # BASE
git status --porcelain        # BASELINE_DIRTY — files already modified or untracked
```

Spawn a fresh implementation subagent (you, the orchestrator):

- `Agent` with `subagent_type: "sonnet-high"` (fallback: `general-purpose` + `model: "sonnet"` + `effort: "high"`).
- Prompt: implement the OpenSpec change `$CHANGE` in the repo at `<repo root>` — invoke `Skill(opsx:apply)` with args `"$CHANGE"` (equivalently `openspec-apply-change`) and complete every task in `openspec/changes/$CHANGE/tasks.md`, following its `proposal.md`, `design.md`, and delta specs under `specs/`. Read the project's `AGENTS.md` / `CLAUDE.md` first and follow its conventions. Check off tasks as they are completed. Run the relevant type-check / tests / lint before reporting. Do not commit.
- Require a compact structured return: tasks completed, tasks not completed (with reason), files touched, checks run and their result, and any assumptions or open questions.

If the subagent reports it is blocked (e.g. a task needs a decision only the user can make), stop and surface it.

## Phase 3 — Triage, then Verify + Review (in parallel)

**3.0 Scope — fix the file list this change owns.** Every later step (triage, 3a–3c, the fixer, the re-check, the summary) works on this one list, called `SCOPE`, never on "everything since `HEAD`".

1. Start from the implementer's "files touched" list.
2. Cross-check with `git status --porcelain` and `git log --name-only BASE..HEAD`: add any file that is modified, untracked or committed now but was not in `BASELINE_DIRTY`, which the implementer forgot to list. Ignore files that were dirty at baseline and not touched by the implementer.
3. If a `SCOPE` file was already dirty at baseline, its diff mixes earlier work with this change — note that for the reviewers and the summary.
4. **Empty scope** (the change was already implemented before this run): look for its commits — `git log` grepped for the change name or its ticket key, or the branch's commits since its merge-base with the default branch. If found, review that range: `SCOPE` = the files it touches, and reviewers diff that range instead of the working tree. If nothing is found, run 3a only and report "nothing to review" in the summary.

**3.1 Triage — size the review to the change.** Do this yourself (no subagent), on `SCOPE` only:

```bash
git diff --numstat HEAD -- <SCOPE tracked files>
wc -l <SCOPE untracked files>   # new files do not show up in git diff
```

Measure:
- **Size** — added + removed **code** lines and the number of code files. Do not count tests, translation/locale files, generated code (e.g. generated API clients), lockfiles, or OpenSpec artifacts. Also note how many apps / packages / libs `SCOPE` touches.
- **Risk flags** — each one that applies:
  - shared code: shared libraries/packages, shared hooks or utils, exported types
  - validation, requiredness, visibility or other cross-field rules
  - persisted or prefilled data: drafts, saved state, caches, prefill, migrations
  - contracts: API definitions, schemas, events, public interfaces
  - more than one app, or more than one product/form version, affected
  - a new module or a new dependency

Pick the tier:

| Tier | When | Runs | Skipped |
| --- | --- | --- | --- |
| **S — trivial** | Only labels, translations, copy, constants or config; ≤ ~30 code lines and ≤ ~3 code files; **no risk flag** | 3a verify + `code-reviewer` | conditional 3b reviewers, 3c adviser |
| **M — standard** | Neither S nor L | 3a + `code-reviewer` + conditional 3b reviewers by the table below + 3c adviser | conditional 3b reviewers whose trigger does not apply |
| **L — large or risky** | > ~300 code lines, or several apps / packages / libs, or ≥ 2 risk flags | everything; when unsure whether a conditional reviewer applies, run it | nothing |

The Phase 4 re-check is decided by what gets fixed, not only by tier — see Phase 4 step 4.

Rules:
- **Err upward.** Any single risk flag rules out S. When the signals disagree, take the higher tier.
- `--tier` from the input overrides this decision.
- Record the tier with its numbers and flags; it goes in the Phase 5 summary. Every reviewer the tier skips is listed there as "skipped by triage (tier X)".

Then kick off **3a and every reviewer the tier selects (3b, 3c) in a single message** (multiple `Agent` calls) so they all run concurrently.

**3a. Verify (Opus subagent)**
- `Agent` with `model: "opus"`, `subagent_type: "general-purpose"`.
- Prompt it to invoke `Skill(opsx:verify)` with args `"$CHANGE"` (equivalently `openspec-verify-change`) to check the implementation against the change artifacts (specs, tasks, design). Pass it the `SCOPE` file list so it does not attribute other uncommitted work to this change.
- It must return a **structured list of gaps**: unmet requirements, unchecked/incomplete tasks, spec/impl mismatches — each with a short description and file/location. Empty list if fully verified.

**3b. Code review fan-out (`pr-review-toolkit` agents)**

`code-reviewer` always runs. The rest are conditional on what the diff touches — and only on tier M and L (tier S runs `code-reviewer` alone):

| Agent (`subagent_type`) | Run when |
| --- | --- |
| `pr-review-toolkit:code-reviewer` | **Always** — bugs, project-guideline / CLAUDE.md compliance, general quality |
| `pr-review-toolkit:silent-failure-hunter` | Diff adds/changes error handling, `try`/`catch`, fallbacks, or swallowed rejections |
| `pr-review-toolkit:type-design-analyzer` | Diff introduces or reshapes types, interfaces, schemas, or public API shapes |
| `pr-review-toolkit:pr-test-analyzer` | Diff touches test files, or adds logic that ought to have tests |
| `pr-review-toolkit:comment-analyzer` | Diff adds or edits comments, docstrings, or docs |

For each selected agent:
- `Agent` with that `subagent_type` **and `model: "opus"`**. Pass `model: "opus"` on *every* reviewer call, without exception — see the note below on why this is not optional.
- In the prompt, state explicitly: the change name `$CHANGE`, the repo root, the `SCOPE` file list as the only files to review (with how to diff them — working tree vs `HEAD`, or the commit range from 3.0 step 4 — and which of them mix in earlier uncommitted work), and the path to `openspec/changes/$CHANGE/` for intent.
- Require the return value to be a **structured list of findings** — each with `severity` (critical / important / suggestion), a one-line description, and `file:line`. Empty list if clean. Tell it to return findings only, not a narrative report, and not to edit any files.

Notes:
- **Reviewers always run on Opus, regardless of what the launcher runs on.** Of the five agents, only `code-reviewer` pins `model: opus` in its own definition; `silent-failure-hunter`, `type-design-analyzer`, `pr-test-analyzer` and `comment-analyzer` all declare `model: inherit`. If this skill is being driven from a Fable context, those four would silently review on Fable. Review quality is the one thing this pipeline cannot afford to downgrade — it is the only gate between the implementer's output and the fix pass. The explicit `model: "opus"` on the `Agent` call takes precedence over the agent's own frontmatter, so set it every time, on all of them (harmless for `code-reviewer`, load-bearing for the other four).
- Never include `pr-review-toolkit:code-simplifier` here — it *modifies* code, which would collide with the Phase 4 fix pass. Simplification is out of scope for this pipeline.
- If a reviewer is skipped, record which one and why; that goes in the Phase 5 summary so coverage is never silently narrowed.

**3c. Senior adviser review (cold Fable subagent)**

Runs on tier M and L; skipped on tier S. 3a checks the change against its checklist and 3b checks the code line by line; 3c is the senior engineer who steps back and asks whether this is the right change, done in the right place, with nothing broken around it. It does **not** do standard code review — no style, naming, local bugs or per-line nits; those belong to 3b.

- `Agent` with `model: "fable"`, `subagent_type: "general-purpose"`. Fresh, not a fork: it gets only what you put in the prompt. Record its agent ID — Phase 4 step 4 continues it.
- Give it: the change name, the repo root, the path to `openspec/changes/$CHANGE/`, any source the proposal cites (ticket export, customer documents), the `SCOPE` file list (and how to diff it), and the implementer's Phase 2 report (including its assumptions). Do not pass your own opinion of the change.
- Tell it to read the proposal, design, delta specs and tasks first, then the diff, then whatever surrounding code it needs to judge impact. Read-only — it must not edit files.
- Ask it to assess:
  1. **Requirement fidelity** — does the change deliver the *intent* of the proposal and its source, not just the letter of the tasks? Did the spec itself misread the source?
  2. **Scope** — anything requested but silently missing; anything changed that nobody asked for.
  3. **Side effects and blast radius** — other callers of touched code, shared modules, other apps, variants or configurations (e.g. other form versions, feature flags) that now behave differently.
  4. **Placement** — is the logic in the right layer and the right shared place (root cause, not one caller's symptom)? Does it reuse existing patterns or reinvent something the codebase already has?
  5. **Data and state over time** — data saved before this change (drafts, persisted state, cached responses), migrations, backward compatibility, ordering and lifecycle effects.
  6. **Contracts** — API, schema, translation keys, events or public types whose consumers are not in the diff.
  7. **Design and spec coherence** — design decisions honored or silently overridden; will the delta specs, once archived, describe what the code really does?
  8. **Proof** — is the requirement actually demonstrated by tests or checks, or only exercised? What would a tester need to check by hand?
  9. **Proportion** — is the change bigger or more complex than the problem needs?
  10. **Unvalidated assumptions** — decisions the implementer or spec made that belong to a human.
- Require a structured return: a verdict (`ready` / `ready-with-notes` / `not-ready`), **findings** — each with `severity` (critical / important / suggestion), the category above, a one-line description, why it matters, and `file:line` or area — and a separate list of **questions for the user** (things only a human can decide). No narrative report.

Wait for 3a and every launched reviewer to complete.

## Phase 4 — Consolidate and fix (single pass, cold Opus subagent)

1. Merge the verify gaps, **all** 3b finding lists, and the 3c adviser findings (when 3c ran) into one set. Questions for the user from 3c are not fixes — carry them straight to the summary. De-duplicate aggressively — several reviewers legitimately flag the same line from different angles; keep the clearest phrasing and note which reviewers agreed (agreement is a signal the finding is real). Decide what **must be fixed** — anything that is a correctness bug, an unmet spec requirement, an incomplete required task, or a review finding at a severity that warrants action. Drop pure nits/opinions unless trivial; note anything you deliberately defer.

2. If the must-fix list is **empty**, skip to Phase 5.

3. Otherwise hand the consolidated list to a **fresh Opus subagent at high effort** (cold — no conversation context):
   - `Agent` with `subagent_type: "opus-high"` (fallback: `general-purpose` + `model: "opus"` + `effort: "high"`).
   - Give it: the change name, the repo root, the paths of the relevant artifacts (`openspec/changes/$CHANGE/…`), and the numbered must-fix list with file:line for each.
   - Instruct it to apply the fixes, keep changes scoped to what's listed, run the same type-check / tests / lint as Phase 2, and return a per-item report of what it changed (item → files touched → what it did, or why it couldn't) plus the check results. Add any new file it touches to `SCOPE`.

4. **Fable re-check of the fixes** — only when step 3 ran, then: on tier **L** always; on any tier when a critical or important item was fixed; otherwise skip. Nothing else looks at the fix pass, so Fable takes one short look:
   - If 3c ran, continue it with `SendMessage` (load it via `ToolSearch` if deferred) so it keeps its understanding of the change. If 3c did not run, or it can no longer be reached, spawn a fresh `Agent` with `model: "fable"`, `subagent_type: "general-purpose"` and give it the 3c brief plus what follows.
   - Send it the numbered must-fix list and the fixer's per-item report. Ask it to read the touched files (read-only) and return, per item, `resolved` / `not-resolved` / `regressed`, plus any **new** issue the fixes introduced, same severity scale. Keep it to the fixes — not a second full review.

This is a **single fix pass** — do not loop back to Phase 3, and do not run another fix pass on the re-check's result. `not-resolved`, `regressed` and new issues go into the summary for the user to decide, along with residual/deferred items.

## Phase 5 — Review the run and summarize

You (the orchestrator) review the whole pipeline and write a concise, user-facing summary. Include:

- **Change**: name and one-line intent.
- **Spec**: whether Phase 1 fast-forwarded artifacts (which ones) or the change was already apply-ready.
- **Implementation**: what the Sonnet subagent did — key changes, checks run, and its stated status.
- **Files**: the final `SCOPE` list (noting any that also carry earlier uncommitted work), so the user can commit each change on its own.
- **Tier**: S / M / L with the numbers and risk flags behind it (or "forced by `--tier`"), and each reviewer skipped by triage.
- **Verify**: gaps found by `opsx:verify` (or "clean").
- **Review**: which reviewers ran (and which were skipped, with the reason), then findings by severity (or "clean").
- **Adviser**: the Fable verdict and its high-level findings (or "clean").
- **Fixes**: what the Opus subagent fixed, per item, with the Fable re-check status (resolved / not-resolved / regressed) and any new issues it found.
- **Questions for you**: the adviser's questions that only a human can decide.
- **Remaining / deferred**: anything not fixed, with a recommendation.
- **Next step**: e.g. run tests, then `/opsx:archive $CHANGE` if satisfied.

Keep it scannable (short sections / bullets). Do not archive the change automatically — leave that decision to the user.

---

## Failure handling

- Any phase that hard-fails: stop, report which phase, include the error, and suggest the manual command the user can run to continue from there.
- If a subagent returns `null` (skipped or died), note it and either retry once or surface it — do not silently proceed as if the phase succeeded.
- Phase 3b is a fan-out, so it can fail **partially**. If some reviewers return and others die, continue with the findings you have, but name the dead reviewers in the Phase 5 summary — a missing reviewer is missing coverage, not a clean result. If `code-reviewer` itself dies, retry it once; if it dies again, treat Phase 3b as failed.
- If the 3c adviser dies, retry it once; if it dies again, continue without it and list the adviser as missing coverage in the Phase 5 summary. Same for the Phase 4 re-check.
