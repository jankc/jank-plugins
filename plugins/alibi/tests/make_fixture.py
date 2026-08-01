#!/usr/bin/env python3
"""Build a synthetic Alibi journal so `day` can be checked without a session.

Scenario for 2026-08-01, chosen to exercise every branch of the aggregation:

  s1  09:00-10:30  client-web        solid morning block
  s1  11:10-12:00  client-web        after a 40-minute gap (a meeting)
  s2  09:45-11:15  internal-tools    overlaps s1 by 90 minutes
  s3  14:00-14:02  scratch           2 minutes, must be dropped
  s4  15:00-16:00  unmapped-thing    not in projects.md
  s5  23:40-00:20  client-web        crosses midnight
  s6  20:00-21:00  own-stuff         report: false - captured, never reported

Usage: python3 tests/make_fixture.py <target-alibi-home>
"""

import json
import os
import sys
from datetime import datetime, timedelta

DATE = "2026-08-01"

SESSIONS = [
    ("s1", "/repos/client-web", "feature/ABC-123-pdf", "ABC-123"),
    ("s2", "/repos/internal-tools", "main", ""),
    ("s3", "/repos/scratch", "main", ""),
    ("s4", "/repos/unmapped-thing", "main", ""),
    ("s5", "/repos/client-web", "feature/ABC-124-auth", "ABC-124"),
    ("s6", "/repos/own-stuff", "main", ""),
]

RUNS = [
    ("s1", "09:00", "10:30"),
    ("s1", "11:10", "12:00"),
    ("s2", "09:45", "11:15"),
    ("s3", "14:00", "14:02"),
    ("s4", "15:00", "16:00"),
    ("s5", "23:40", "23:59"),
    ("s6", "20:00", "21:00"),
]

NOTES = [
    ("s1", "11:58", "ABC-123", "Client web",
     ["Implemented invoice PDF export", "Fixed date parsing in summary view"]),
    ("s2", "11:14", "", "Internal tooling",
     ["Added the alibi plugin scaffold"]),
]

PROJECTS_MD = """---
log: "{home}/{{yyyy}}-{{mm}}.md"
heading: ""
idle_gap_minutes: 20
min_session_minutes: 5
min_turns: 3
round_minutes: 15
target_hours: 8
nudge: true
---

## Client web
- ticket: ABC-*
- paths: /repos/client-web

## Internal tooling
- paths: /repos/internal-tools, /repos/scratch
- report-as: Internal development
- note: no ticket, report as internal

## Own stuff
- paths: /repos/own-stuff
- report: false
"""


def at(hhmm, day=DATE):
    stamp = datetime.strptime("%s %s" % (day, hhmm), "%Y-%m-%d %H:%M")
    return stamp.astimezone()


def main():
    home = os.path.abspath(sys.argv[1])
    os.makedirs(os.path.join(home, "journal"), exist_ok=True)

    with open(os.path.join(home, "projects.md"), "w") as fh:
        fh.write(PROJECTS_MD.format(home=home))

    records = []
    for sid, cwd, branch, ticket in SESSIONS:
        first = min(start for s, start, _ in RUNS if s == sid)
        records.append({"t": "session", "at": at(first).isoformat(), "sid": sid,
                        "cwd": cwd, "repo": cwd, "branch": branch,
                        "ticket": ticket, "project": ""})

    # One beat every 5 minutes across each run.
    for sid, start, end in RUNS:
        cursor, stop = at(start), at(end)
        while cursor <= stop:
            records.append({"t": "beat", "at": cursor.isoformat(), "sid": sid})
            cursor += timedelta(minutes=5)

    for sid, when, ticket, project, bullets in NOTES:
        record = {"t": "note", "at": at(when).isoformat(), "sid": sid,
                  "bullets": bullets, "project": project}
        if ticket:
            record["ticket"] = ticket
        records.append(record)

    records.sort(key=lambda r: r["at"])
    path = os.path.join(home, "journal", "%s.jsonl" % DATE)
    with open(path, "w") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")

    # s5 spills past midnight into the next day's file.
    nxt = (datetime.strptime(DATE, "%Y-%m-%d") + timedelta(days=1)).date()
    spill = []
    cursor, stop = at("00:00", nxt.isoformat()), at("00:20", nxt.isoformat())
    while cursor <= stop:
        spill.append({"t": "beat", "at": cursor.isoformat(), "sid": "s5"})
        cursor += timedelta(minutes=5)
    with open(os.path.join(home, "journal", "%s.jsonl" % nxt), "w") as fh:
        for record in spill:
            fh.write(json.dumps(record) + "\n")

    print("fixture written to %s" % home)


if __name__ == "__main__":
    main()
