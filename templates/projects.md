---
# Where the reconciled work log is written.
# {yyyy} {mm} {dd} are substituted. Obsidian daily note example:
#   log: "~/Obsidian/Vault/Daily/{yyyy}-{mm}-{dd}.md"
#   heading: "## Work log"
log: "~/.alibi/{yyyy}-{mm}.md"
heading: ""

idle_gap_minutes: 20      # a longer gap ends an activity block (meeting, lunch)
min_session_minutes: 5    # shorter sessions never nudge and never report
min_turns: 3              # minimum turns before a session counts
round_minutes: 15         # reporting granularity
target_hours: 8           # normalized column; 0 disables it
lead_in_minutes: 3        # credited before each block, for writing the prompt
nudge: true               # ask for a session note before finishing
---

# Projects

# One section per project or area. `paths` is what maps a working directory
# to a project, so it is the only field that really has to be right.
#
#   ticket:     free-text hint about how this project's tickets look,
#               e.g. "ABC-*", "#<number>", "no tickets". Just a hint for the
#               agent - no format is assumed anywhere.
#   paths:      comma-separated directories (a repo root, or a parent of
#               several); git worktrees resolve to their main checkout
#   report-as:  label to use in the log, when it differs from the section name
#   note:       anything the agent should know when reporting this work

## Example client project
- ticket: ABC-*
- paths: ~/dev/work/example-frontend, ~/dev/work/example-backend

## Internal tooling
- paths: ~/dev/internal
- report-as: Internal development
- note: no ticket, report as internal development
