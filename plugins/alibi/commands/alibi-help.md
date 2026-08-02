---
description: Show the Alibi guide — commands, configuration, how time is measured, FAQ.
argument-hint: "[topic]"
allowed-tools: Read
---

Show the user the Alibi guide from
`${CLAUDE_PLUGIN_ROOT}/skills/alibi/HELP.md`.

If **$1** names a topic (setup, commands, config, personal, time, privacy,
faq, ...), show only the matching section, verbatim. Otherwise show the whole
guide.

Render it faithfully — it is written for the user, not for you. Do not
summarize it, reorder it, or wrap it in commentary; at most one orienting
sentence before it. If the user then asks a follow-up the guide does not
answer, use the `alibi` skill and `python3 "$ALIBI_SCRIPT" status` / `config`
to answer from their actual setup.
