---
description: Reconcile a day of recorded work into the final work log.
argument-hint: "[date | yesterday | today]"
allowed-tools: Bash(python3:*), Read, Write, Edit, AskUserQuestion
---

Reconcile Alibi's raw records for **$1** (default: yesterday if it has
unreconciled activity, otherwise today) into the user's work log.

Run the aggregation, then follow the reconciliation procedure in the `alibi`
skill — show both columns, resolve anything the report flags, draft the entry,
get confirmation, write it, and only then mark the day reconciled.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/alibi.py" day $1
```

Do not write anything to the log file before the user has seen and approved the
draft entry.
