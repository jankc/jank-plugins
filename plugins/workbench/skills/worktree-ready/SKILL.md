---
name: worktree-ready
description: >-
  Check whether the current git worktree is finished and safe to delete: clean tree, pushed
  commits, MR/PR merged, branch changes contained in the base, OpenSpec change archived, no
  child worktrees or running agents left. Then either propose fixes or remove the worktree
  with whichever tool manages it (Orca, worktrunk, plain git). Use when the user says "is this
  worktree done", "can I remove this worktree", "worktree ready", "clean up this worktree",
  or "/worktree-ready".
---

# Worktree ready?

Read-only audit first. Never delete anything until the user confirms.

## 1. Who manages this worktree

```bash
git rev-parse --git-common-dir     # differs from .git ⇒ linked worktree
```

Then identify the manager, because it decides how removal happens later:

- **Orca** — `orca worktree current --json` succeeds. Follow the `orca-cli` skill for the
  executable name and commands; do not guess Orca flags.
- **worktrunk** — `wt list` knows this path. Removal is `wt remove` (it also drops the branch
  when merged).
- **plain git** — neither of the above. Removal is `git worktree remove <path>`.

Not a linked worktree at all? Say so and stop — there is nothing to remove.

## 2. Gather git state

Run from the worktree root, after `git fetch origin --prune` (otherwise every remote comparison is stale).

```bash
BASE=$(git symbolic-ref -q --short refs/remotes/origin/HEAD || echo origin/main)   # confirm per repo
BR=$(git branch --show-current)
echo "== branch: $BR  base: $BASE"
git status --porcelain                                    # must be empty
git log --oneline @{u}..HEAD 2>&1                         # must be empty (or "no upstream" = never pushed)
git diff --quiet $BASE HEAD && echo "CONTAINED in base" || git log --oneline $BASE..HEAD
git stash list | grep -i "$BR" || true                    # stack is shared across worktrees
# agent artifacts may be symlinks into another repo — check whatever repo they really live in
for p in openspec .claude .agents CLAUDE.md AGENTS.md; do
  [ -L "$p" ] && git -C "$(dirname "$(readlink -f "$p")")" rev-parse --show-toplevel 2>/dev/null
done | sort -u | while read -r r; do
  echo "== artifacts repo: $r"; git -C "$r" status --porcelain; git -C "$r" log --oneline @{u}..HEAD 2>&1
done
```

The tip-vs-tip `git diff` is the merge check that survives squash and rebase merges — an empty diff means the
base already contains everything this branch did, which `git branch --merged` misses after a squash. A non-empty
diff is *inconclusive*, not a blocker: it also shows up when base commits were merged into the branch afterwards.
Then read the `$BASE..HEAD` log and let the MR state in step 3 decide.

## 3. MR / PR state

Pick the CLI from the `origin` remote host:

| host | command |
|---|---|
| gitlab | `glab mr list --source-branch "$BR" --all` then `glab mr view <id>` |
| github | `gh pr view "$BR" --json state,mergedAt,url` |
| codeberg / forgejo | `fj pr view <id>` |

Want: exactly one MR/PR, state merged. Flag: no MR at all, still open, closed-without-merge,
unresolved review threads, failing pipeline on the merge commit.

## 4. OpenSpec

Only if the repo has `openspec/`. Match changes to this branch's ticket or topic:

```bash
openspec list                      # active (unarchived) changes
ls openspec/changes | grep -v '^archive$'
```

A change belonging to this branch that is still in `openspec/changes/` is a blocker — archiving is what syncs
the delta specs into the main specs. Fix with the project's archive skill (`openspec-archive-change` / `opsx:archive`).
If `openspec/` is a symlink, that commit lands in the repo it points at, which step 2 already covers.

## 5. Manager state

Only for a managed worktree. Ask the manager, do not infer:

- Orca: `ORCA worktree current --json`, `ORCA worktree list --json` (children still parented here),
  `ORCA worktree ps --json` (live agents or terminals).
- worktrunk: `wt list`.

Blockers: child worktrees parented here (removing this one orphans them), or an agent still running in it.

## 6. Verdict

Report one line per check — `ok` / `blocker` / `n/a` — then:

- **Ready**: say so, then ask before removing. On yes, use the manager from step 1:
  `ORCA worktree rm --worktree id:<repoId>::<path> --force --json` (via the `orca-cli` skill), `wt remove`,
  or `git worktree remove <path>`. Run it from outside the worktree.
  With plain git the local branch survives; offer `git branch -d "$BR"` (safe: refuses if unmerged), and remote
  branch deletion only if the forge did not auto-delete it.
- **Not ready**: list each blocker with its one-line fix (push, open MR, archive the change, commit the artifacts
  repo, stop the agent, remove the child worktree first). Do not offer removal.

Anything ambiguous — an MR you cannot find, a diff against a base you are not sure of — say so and stop.
Deleting a worktree with unpushed work is unrecoverable.
