---
description: Reconcile recorded work into the final work log - every pending day, or one date.
argument-hint: "[pending | date | yesterday | today]"
allowed-tools: Bash(python3:*), Read, Write, Edit, AskUserQuestion
---

Reconcile Alibi's raw records for **$1** into the user's work log.

With no argument, or `pending`, reconcile every unreconciled day before today:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/alibi.py" status
```

The `unreconciled:` line lists them. If it says `none`, say so and offer today.
Then follow "Reconciling several days" in the `alibi` skill.

With a date (`yesterday`, `today`, `2026-08-01`), reconcile that one day:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/alibi.py" day $1
```

Then follow "Reconciling a day" in the `alibi` skill: show both columns,
resolve anything the report flags, draft the entry, get confirmation, write it,
and only then mark the day reconciled.

Do not write anything to the log file before the user has seen and approved the
draft entry.
