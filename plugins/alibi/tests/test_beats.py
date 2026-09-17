#!/usr/bin/env python3
"""Beat -> activity block accounting.

The case that matters: Stop fires once per response, not once per exchange,
so a prompt driving a long tool loop leaves a single beat at the end. Paired
with the start beat from UserPromptSubmit, that span counts as work; without
a pair, the idle gap applies as it always did.

Usage: python3 tests/test_beats.py
"""

import datetime
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "alibi", os.path.join(HERE, os.pardir, "scripts", "alibi.py"))
alibi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alibi)

T0 = datetime.datetime(2026, 9, 15, 9, 0, tzinfo=datetime.timezone.utc)


def at(minutes):
    return T0 + datetime.timedelta(minutes=minutes)


def total(beats, gap=30, lead=3):
    blocks = alibi.blocks_from_beats(beats, gap, lead)
    return sum((end - start).total_seconds() for start, end in blocks) / 60


# One prompt, a 40-minute run, one Stop beat at the end: the bug this fixes.
assert total([(at(40), "stop")]) == 3, "lone stop beat is lead-in only"
assert total([(at(0), "start"), (at(40), "stop")]) == 43, \
    "a 40-minute response must count as 40 minutes, not zero"

# The idle gap still applies between a response and the next prompt.
assert total([(at(0), "start"), (at(5), "stop"),
              (at(60), "start"), (at(65), "stop")]) == 16, \
    "two 5m turns plus two lead-ins; the 55m gap between them is idle"

# Turns closer together than the gap stay one block.
assert total([(at(0), "start"), (at(5), "stop"),
              (at(10), "start"), (at(20), "stop")]) == 23, \
    "one block 09:00-09:20 plus lead-in"

# A start with no stop (session killed mid-run) must not swallow the day.
assert total([(at(0), "start"), (at(600), "start"), (at(605), "stop")]) == 11, \
    "an orphan start does not glue ten hours into one block"

# Journals written before start beats existed collapse exactly as before.
legacy = [(at(0), None), (at(5), None), (at(90), None)]
assert total(legacy) == total([(at(0), "stop"), (at(5), "stop"),
                               (at(90), "stop")]) == 11, \
    "untagged beats behave as stops"

assert alibi.blocks_from_beats([], 30, 3) == []

print("OK - beat accounting")
