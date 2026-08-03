---
description: Set up or reconfigure Alibi — the projects you work on and where the log goes.
allowed-tools: Bash(python3:*), Bash(git:*), Read, Write, Edit, AskUserQuestion
---

Set up Alibi for this user, following the first-run procedure in the `alibi`
skill.

Check what already exists:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/alibi.py" status
```

If `~/.alibi/projects.md` already exists, this is a reconfiguration: read it,
show the current setup, and ask what to change rather than starting over. If a
`.declined` marker exists, remove it — running this command is the user
changing their mind.

If it does not exist, gather the evidence yourself — directories the user has
recently worked in, git repositories near the current directory and under the
usual places code lives, their recent branches and commit subjects, and any
ticket convention you can infer from those — then **propose a complete draft
`projects.md`** for the user to correct. Do not ask them to list their projects
from memory, and do not assume any particular ticket format.

Use `AskUserQuestion` only for the log destination and `target_hours`.

After writing the file, tell them capture begins in their next session, since
hooks are only loaded at startup.

Then offer to add Alibi's permission allow rules to `~/.claude/settings.json`,
per the first-run procedure in the skill — without them, every note and
reconcile prompts for permission, because everything Alibi touches lives
outside the project directory.
