---
description: Record what this session worked on, without waiting for the nudge.
argument-hint: "[optional ticket or project]"
allowed-tools: Bash(python3:*), Read
---

Record a work note for the current session. If **$1** is given, treat it as the
ticket key or project name and do not second-guess it.

Otherwise work out the ticket/project using the priority order in the `alibi`
skill — what the user said, then the configured project for this directory,
then the branch name, then the day's commits — and ask only if genuinely
ambiguous.

Write 2–4 bullets describing what actually changed, then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/alibi.py" note \
  --ticket <KEY> --project "<name>" \
  --bullet "..." --bullet "..."
```

Omit `--ticket` when there is no ticket. Never invent a ticket key. Confirm in
one short line.
