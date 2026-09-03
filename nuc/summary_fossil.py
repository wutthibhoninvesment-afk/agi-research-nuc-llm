#!/usr/bin/env python3
"""`sarNN` presence/absence as a witness of the box at 00:07Z. Round 478.

Round 400 read the CONTENTS of `/var/log/sysstat/saNN` and got a 10-minute
uptime witness (`nuc/sysstat_archive.py`). This module reads something the
same directory has been publishing the whole time and which no round has ever
looked at: the FILE SET, and specifically the `sarNN` files sitting beside the
`saNN` ones.

WHY THE FILE SET SAYS SOMETHING THE CONTENTS CANNOT
---------------------------------------------------
`sysstat-summary.timer` fires `OnCalendar=00:07:00`. Its service runs
`/usr/lib/sysstat/sa2`, which renders YESTERDAY's binary day file to a text
report `sarNN` and then sweeps `find $SA_DIR -mtime +$HISTORY | xargs rm -f`.
So `sarNN` is not a copy of `saNN` -- it is the **receipt of a fire**, stamped
with the instant the fire happened.

Round 478 read `Persistent=` off the unit for the first time and it is **no**
on both sysstat timers. A `Persistent=no` timer that misses its window does
NOT catch up at the next boot. Therefore:

    `sarNN` exists  <=>  the box was running at 00:07Z on day NN+1.

That is a witness at an instant, derived from filesystem metadata, on a
schedule this program does not control and cannot perturb. Every other
availability instrument in this track answers a question about a window
(`sar` samples every 10 min; our own ssh probes once an hour at best, and
never at 00:07 -- the E rounds run in daylight). This one answers about a
point, and it answers about the ONE point per day that no probe has ever
covered.

THE RETENTION THEOREM -- why an absence here cannot be rotation
---------------------------------------------------------------
The obvious objection is that a missing `sarNN` might just have been swept.
It cannot have been, whenever `saNN` is still present:

* `saNN` is stamped at the last collect of day NN (~23:50).
* `sarNN` is stamped at 00:07 on day NN+1, i.e. **17 minutes younger**.
* The sweep is `-mtime +7`: `int(age_s // 86400) > 7`, whole days truncated.
* At any fire instant T (itself 00:07), `saNN`'s age is an integer number of
  days plus 0:17, and `sarNN`'s age is that same integer exactly. Both floor
  to the same integer, so the two files always share a verdict.

So `saNN` present AND `sarNN` absent means the fire did not write it -- never
that the sweep took it. `saNN` absent is a different matter and this module
refuses to answer there (`no_day_file`), because a day file the box never
created and a day file rotation deleted look identical from outside.

WHAT THIS MODULE WILL NOT DO
----------------------------
It will not call a missed fire "the box was off". A masked timer, a failed
`sa2`, or a full disk produce the same hole. The verdict word is
`fire_missed`, and `crosscheck` against `journalctl --list-boots` is what
promotes it to downtime. Round 478 ran that cross-check over 10 decidable
fires and got 10/10 -- reported, not assumed.

It will not score the newest day. Its fire has not happened yet
(`fire_pending`); counting it as a miss would report every capture as ending
in an outage.

Pure text-in / dict-out like `nuc/sysstat_archive.py` and
`nuc/perturbation.py`: it opens no socket and runs no command, so it cannot
reach the NUC's port 8001.

Usage:
    python3 nuc/summary_fossil.py fires      --capture state/nuc-capture-rNNN \
                                             --now 2026-09-03T17:10:00Z
    python3 nuc/summary_fossil.py crosscheck --capture ... --now ...
    python3 nuc/summary_fossil.py blindspot  --capture ... --now ...
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_manifest import parse_sysstat_ls  # noqa: E402

# `sa23` / `sar23`, uncompressed only. A compressed day file (`.xz`, past
# COMPRESSAFTER=10) is still a day file, but its mtime is the COMPRESSION's,
# not the collector's, so it cannot carry the 17-minute argument the retention
# theorem rests on. Those are reported as `compressed` and not scored.
_SA_RE = re.compile(r"^sa(\d{2})$")
_SAR_RE = re.compile(r"^sar(\d{2})$")
_COMPRESSED_RE = re.compile(r"^sar?(\d{2})\.(Z|gz|bz2|xz|lz|lzo)$")

_LS_SECTION = "### SYSSTAT_FILES"


def _parse(stamp: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _fmt(when: _dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def read_listing(capture_dir: str) -> str:
    """The `ls -l /var/log/sysstat/` text out of a capture directory.

    Two files in every capture carry it -- `sar-all.txt` under a
    `### SYSSTAT_FILES` marker (step 2 of the plan) and
    `collector-evidence.txt` unmarked (step 3d). Prefer the marked one: an
    unmarked listing concatenated with other `ls` output would silently pick
    up rows from a different directory, which is round 436's user-journal bug
    in a new costume.
    """
    marked = os.path.join(capture_dir, "sar-all.txt")
    if os.path.exists(marked):
        with open(marked, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if _LS_SECTION in text:
            body = text.split(_LS_SECTION, 1)[1]
            # up to the next marker
            return body.split("\n### ", 1)[0]
    eviden = os.path.join(capture_dir, "collector-evidence.txt")
    if os.path.exists(eviden):
        with open(eviden, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    raise SystemExit(
        f"summary-fossil ERROR: {capture_dir}: no sar-all.txt "
        f"({_LS_SECTION} section) and no collector-evidence.txt")


def fire_time_of_day(entries: list) -> tuple:
    """(hh, mm) of the summary fire, DERIVED from the receipts, not hardcoded.

    Round 448's rule: never hardcode 00:07, because a box whose timer moves
    would be scored against a lattice it does not use. The `sarNN` mtimes ARE
    the fires, so the modal time-of-day over them is the schedule. Returns the
    mode and how many receipts voted for it, so a caller can see disagreement
    rather than inherit a silent majority.
    """
    votes = collections.Counter()
    for e in entries:
        if _SAR_RE.match(e["name"]):
            t = _parse(e["mtime_utc"])
            votes[(t.hour, t.minute)] += 1
    if not votes:
        return None, 0, 0
    # `Counter.most_common` breaks a tie by insertion order, i.e. by whatever
    # order `ls` happened to print. That is a silent arbitrary choice, and it
    # decides every fire instant in the report -- round 478's own test caught
    # it picking the LATER of two one-vote times and scoring a receipt 1920 s
    # "early". Sort explicitly: most votes first, then earliest time of day.
    # A caller that cares whether the mode was earned reads `fire_tod_votes`
    # against `fire_tod_receipts`.
    (hh, mm), n = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return (hh, mm), n, sum(votes.values())


#: A fire this recent has not necessarily written its receipt yet, so it is
#: reported `fire_pending` rather than `fire_missed`. Round 478 found this by
#: mutation: `fire > now` and `fire >= now` were indistinguishable to the test
#: suite, which means NOTHING pinned the behaviour at the boundary -- and the
#: unpinned direction is the one that invents an outage out of a capture taken
#: a second after midnight. One `sysstat-collect` interval is the natural
#: grace: if the box were up, the receipt would be there well inside it.
DEFAULT_SETTLE_S = 600


def fires(ls_text: str, now_utc: str, settle_s: int = DEFAULT_SETTLE_S) -> dict:
    """Per-day verdict on the summary fire that should have rendered that day.

    A day is keyed by its `saNN` file. The fire that renders it is at the
    derived time-of-day on the NEXT calendar day, computed from `saNN`'s own
    mtime rather than from NN, because NN is a day-of-month with no year and
    the mtime is the only thing in the listing that has one.
    """
    now = _parse(now_utc)
    entries = parse_sysstat_ls(ls_text, now_utc)
    tod, n_votes, n_receipts = fire_time_of_day(entries)

    day_files, receipts, compressed, mismatched = {}, {}, [], []
    for e in entries:
        m = _SA_RE.match(e["name"])
        if m:
            stamp = _parse(e["mtime_utc"])
            if stamp.day != int(m.group(1)):
                # `saNN` is written by the collector on day NN; an mtime on a
                # different day-of-month means the year reconstruction in
                # parse_sysstat_ls put it in the wrong month. Refuse it rather
                # than derive a fire instant from it.
                mismatched.append({"name": e["name"],
                                   "mtime_utc": e["mtime_utc"]})
                continue
            day_files[e["name"]] = e
            continue
        m = _SAR_RE.match(e["name"])
        if m:
            receipts[e["name"]] = e
            continue
        if _COMPRESSED_RE.match(e["name"]):
            compressed.append(e["name"])

    out = []
    for name, e in sorted(day_files.items(),
                          key=lambda kv: kv[1]["mtime_utc"]):
        nn = _SA_RE.match(name).group(1)
        covers = _parse(e["mtime_utc"]).date()
        if tod is None:
            fire = None
        else:
            fire = _dt.datetime.combine(
                covers + _dt.timedelta(days=1),
                _dt.time(tod[0], tod[1]), tzinfo=_dt.timezone.utc)
        receipt = receipts.get("sar" + nn)
        if fire is not None and (now - fire).total_seconds() < settle_s:
            verdict, note = "fire_pending", (
                "the fire that renders this day has not happened yet, or "
                f"happened less than {settle_s}s ago and may not have "
                "written its receipt")
        elif receipt is not None:
            verdict, note = "fire_ran", (
                "receipt present: the summary timer fired, so the box was "
                "running at this instant")
        else:
            verdict, note = "fire_missed", (
                "day file present but no receipt; the retention theorem "
                "forbids the sweep having taken the receipt while sparing "
                "the day file, so the fire did not run")
        row = {
            "day_file": name,
            "covers_date": covers.isoformat(),
            "day_file_mtime_utc": e["mtime_utc"],
            "day_file_size": e["size"],
            "fire_utc": _fmt(fire) if fire else None,
            "receipt": receipt["name"] if receipt else None,
            "receipt_mtime_utc": receipt["mtime_utc"] if receipt else None,
            "verdict": verdict,
            "note": note,
        }
        if receipt is not None and fire is not None:
            row["receipt_lag_s"] = (
                _parse(receipt["mtime_utc"]) - fire).total_seconds()
        out.append(row)

    # A receipt with no day file: the sweep cannot produce this (the receipt is
    # younger and dies no earlier), so it is a genuine anomaly worth naming.
    orphans = [n for n in receipts
               if "sa" + _SAR_RE.match(n).group(1) not in day_files]

    # Calendar days inside the span with NO day file at all. The fire that
    # would render them is NOT decidable here: the box never created the file,
    # so there was nothing for `sa2` to render and the receipt's absence is
    # overdetermined.
    dates = [_dt.date.fromisoformat(r["covers_date"]) for r in out]
    holes = []
    if dates:
        d = min(dates)
        while d <= max(dates):
            if d not in dates:
                holes.append(d.isoformat())
            d += _dt.timedelta(days=1)

    counts = collections.Counter(r["verdict"] for r in out)
    return {
        "now_utc": now_utc,
        "settle_s": settle_s,
        "fire_time_of_day": (f"{tod[0]:02d}:{tod[1]:02d}"
                             if tod else None),
        "fire_tod_votes": n_votes,
        "fire_tod_receipts": n_receipts,
        "n_day_files": len(day_files),
        "n_receipts": len(receipts),
        "fires": out,
        "counts": dict(counts),
        "missed_fires_utc": [r["fire_utc"] for r in out
                             if r["verdict"] == "fire_missed"],
        "no_day_file_dates": holes,
        "orphan_receipts": sorted(orphans),
        "compressed_not_scored": sorted(compressed),
        "day_file_month_mismatch": mismatched,
        "note": "`fire_missed` means the timer did not run, which is downtime "
                "ONLY once a second instrument agrees; run `crosscheck`.",
    }


_BOOT_RE = re.compile(
    r"^\s*(-?\d+)\s+([0-9a-f]{32})\s+\w{3}\s+(\d{4}-\d{2}-\d{2}\s+"
    r"\d{2}:\d{2}:\d{2})\s+\w+\s+\w{3}\s+(\d{4}-\d{2}-\d{2}\s+"
    r"\d{2}:\d{2}:\d{2})\s+(\w+)\s*$")


def parse_boots(text: str) -> list:
    """`journalctl --list-boots --no-pager` -> [{idx, boot_id, first, last}]."""
    out = []
    for line in text.splitlines():
        m = _BOOT_RE.match(line)
        if not m:
            continue
        idx, bid, first, last, _tz = m.groups()
        out.append({
            "idx": int(idx),
            "boot_id": bid,
            "first_utc": first.replace(" ", "T") + "Z",
            "last_utc": last.replace(" ", "T") + "Z",
        })
    return sorted(out, key=lambda b: b["first_utc"])


def crosscheck(ls_text: str, boots_text: str, now_utc: str,
               settle_s: int = DEFAULT_SETTLE_S) -> dict:
    """Every decidable fire, scored against the journal's boot table.

    The two sources share nothing: one is filesystem mtimes written by `sa2`,
    the other is journald's boot index. Agreement is therefore evidence; a
    disagreement is a real defect in one of them and is named, not averaged.

    A fire is only scorable while the boot table still REACHES it. journald
    evicts old boots (round 478 watched three boots leave the table between
    two captures nine days apart), so a fire before the table's first entry is
    `boot_table_too_short`, never a disagreement.
    """
    f = fires(ls_text, now_utc, settle_s)
    boots = parse_boots(boots_text)
    if not boots:
        raise SystemExit("summary-fossil ERROR: no boot rows parsed")
    horizon = boots[0]["first_utc"]

    rows, agree, disagree, unscorable = [], 0, 0, 0
    for r in f["fires"]:
        if r["verdict"] == "fire_pending" or r["fire_utc"] is None:
            continue
        fire = r["fire_utc"]
        if fire < horizon:
            rows.append({**r, "boot_says": None,
                         "scored": "boot_table_too_short"})
            unscorable += 1
            continue
        covering = [b for b in boots
                    if b["first_utc"] <= fire <= b["last_utc"]]
        boot_up = bool(covering)
        fossil_up = r["verdict"] == "fire_ran"
        ok = boot_up == fossil_up
        rows.append({
            **r,
            "boot_says": "up" if boot_up else "down",
            "boot_id": covering[0]["boot_id"] if covering else None,
            "scored": "agree" if ok else "DISAGREE",
        })
        agree += ok
        disagree += not ok

    return {
        "now_utc": now_utc,
        "boot_table_first_entry_utc": horizon,
        "n_boots": len(boots),
        "n_scored": agree + disagree,
        "n_agree": agree,
        "n_disagree": disagree,
        "n_unscorable_boot_table_too_short": unscorable,
        "agreement": (round(agree / (agree + disagree), 4)
                      if (agree + disagree) else None),
        "rows": rows,
        "disagreements": [r for r in rows if r["scored"] == "DISAGREE"],
        "note": "the fossil and the boot table share no input; agreement is "
                "evidence that `fire_missed` is downtime rather than a "
                "masked timer.",
    }


def blindspot(ls_text: str, now_utc: str, log_path: str,
              settle_s: int = DEFAULT_SETTLE_S) -> dict:
    """How many fire instants our OWN probe log could have decided.

    The point of the fossil is that it witnesses an instant nothing else in
    this track covers. That claim is checkable: for each fire, does the
    reachability log hold a probe close enough on both sides to bracket it?
    """
    f = fires(ls_text, now_utc, settle_s)
    stamps = []
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                at = rec.get("checked_at_utc") or rec.get("at_utc")
                if at:
                    stamps.append((at, bool(rec.get("reachable"))))
    stamps.sort()

    rows = []
    for r in f["fires"]:
        if r["verdict"] == "fire_pending" or r["fire_utc"] is None:
            continue
        fire = r["fire_utc"]
        before = [s for s in stamps if s[0] <= fire]
        after = [s for s in stamps if s[0] >= fire]
        gap = None
        if before and after:
            gap = (_parse(after[0][0]) - _parse(before[-1][0])).total_seconds()
        rows.append({
            "fire_utc": fire,
            "fossil": r["verdict"],
            "probe_before_utc": before[-1][0] if before else None,
            "probe_after_utc": after[0][0] if after else None,
            "probe_bracket_s": gap,
            "bracketed_within_1h": bool(gap is not None and gap <= 3600),
        })
    n = len(rows)
    tight = sum(r["bracketed_within_1h"] for r in rows)
    return {
        "log_path": log_path,
        "n_probe_records": len(stamps),
        "n_fires_scored": n,
        "n_fires_bracketed_within_1h": tight,
        "fraction_bracketed_within_1h": round(tight / n, 4) if n else None,
        "rows": rows,
        "note": "a fire nothing brackets tightly is an instant this track had "
                "no opinion about before this module existed.",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="mode", required=True)
    for name, helptext in (
            ("fires", "per-day verdict on the 00:07 summary fire"),
            ("crosscheck", "score the fossil against journalctl --list-boots"),
            ("blindspot", "which fires our own probe log could decide")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--capture", required=True)
        sp.add_argument("--now", required=True,
                        help="UTC the `ls -l` was taken; `ls` omits the year")
        sp.add_argument("--settle-s", type=int, default=DEFAULT_SETTLE_S,
                        help="a fire this recent is `fire_pending`, not "
                             "`fire_missed` (default %(default)s)")
        if name == "blindspot":
            sp.add_argument("--log-path",
                            default="state/nuc-reachability-log.jsonl")
        if name == "crosscheck":
            sp.add_argument("--strict", action="store_true",
                            help="exit 1 on any DISAGREE row")
    args = p.parse_args(argv)

    ls_text = read_listing(args.capture)
    if args.mode == "fires":
        print(json.dumps(fires(ls_text, args.now, args.settle_s), indent=2))
        return 0
    if args.mode == "blindspot":
        print(json.dumps(blindspot(ls_text, args.now, args.log_path,
                                   args.settle_s), indent=2))
        return 0

    boots_path = os.path.join(args.capture, "journal-boots.txt")
    if not os.path.exists(boots_path):
        raise SystemExit(
            f"summary-fossil ERROR: {boots_path} missing; crosscheck needs "
            f"`journalctl --list-boots` from the same capture")
    with open(boots_path, "r", encoding="utf-8", errors="replace") as fh:
        rep = crosscheck(ls_text, fh.read(), args.now, args.settle_s)
    print(json.dumps(rep, indent=2))
    return 1 if (args.strict and rep["n_disagree"]) else 0


if __name__ == "__main__":
    sys.exit(main())
