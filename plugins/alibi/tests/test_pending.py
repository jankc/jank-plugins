#!/usr/bin/env python3
"""unreconciled_days: no file window, markers count from any file.

Usage: python3 tests/test_pending.py
"""

import json
import os
import sys
import tempfile
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import alibi  # noqa: E402


def main():
    home = tempfile.mkdtemp()
    os.environ["ALIBI_HOME"] = home
    os.makedirs(os.path.join(home, "journal"))
    today = alibi.now().date()

    def write(date, records):
        with open(alibi.journal_path(date), "a") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")

    def beats(n):
        return [{"t": "beat", "at": "x", "sid": "s"}] * n

    # 20 active days back from yesterday, plus today.
    for back in range(0, 21):
        write(today - timedelta(days=back), beats(5))
    old = today - timedelta(days=20)        # skipped long ago
    legacy = today - timedelta(days=15)     # marker filed in a later day's file
    quiet = today - timedelta(days=3)       # below min_turns
    open(alibi.journal_path(quiet), "w").close()
    write(quiet, beats(1))
    for back in range(1, 20):
        day = today - timedelta(days=back)
        if day not in (legacy, quiet):
            write(day, [{"t": "rollup", "at": "x", "date": day.isoformat()}])
    write(today - timedelta(days=10),
          [{"t": "rollup", "at": "x", "date": legacy.isoformat()}])

    got = alibi.unreconciled_days({"min_turns": 3})
    assert got == [old.isoformat()], got
    print("OK - pending days")


if __name__ == "__main__":
    main()
