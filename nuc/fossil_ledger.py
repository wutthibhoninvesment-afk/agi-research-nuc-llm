#!/usr/bin/env python3
"""The summary-fire fossil, unioned over every capture and made durable.

Round 484 (NUC-integration E), closing round 478's next-steps 4 and 5.

WHY THIS EXISTS
---------------
`nuc/summary_fossil.py` reads ONE capture and answers, per day, whether the
00:07 `sysstat-summary` fire ran. Round 478 shipped it and then wrote down two
things it could not do:

  4. "Make the fossil durable. Re-run `summary_fossil.py fires` on every
     capture and append to a JSONL ledger the way reachability does. Once
     `sa29` rotates away the 2026-08-30 miss survives only inside a capture."
  5. "Analyse over the UNION of captures. The A/B shows the choice of capture
     silently moves the pooled window in both directions."

Round 484 watched item 4 stop being hypothetical. The 2026-09-04T00:07:18
sweep -- the first sweep this program has ever observed -- deleted `sa23`,
`sa24`, `sa25`, `sa26` and their receipts. Rerun on the live box, the fossil
went from **10 decidable fires to 8**. Three of the days it lost
(2026-08-24, -25, -26) now exist in NO place except
`state/nuc-capture-r478/sysstat-binary.tar.xz` and the three older captures'
`ls -l` text. A ledger that is only ever rebuilt from the newest capture
forgets, on a seven-day clock, faster than this track's six-round cadence can
read.

WHAT A UNION IS ALLOWED TO DO
-----------------------------
Not average, and not prefer the newest. Two captures that both decide a day
must AGREE -- they are reading the same filesystem at different times, and the
underlying fact (did a fire happen at that instant) is immutable. So:

* agreement is the null hypothesis and every violation is reported by
  instant, never reconciled;
* a day one capture decides and another cannot is NOT a disagreement --
  `no_day_file` and `fire_pending` are refusals, not verdicts, and a refusal
  loses to a verdict;
* `fire_ran` beats `fire_missed` only when they genuinely conflict, and that
  case is reported as a DISAGREE row rather than resolved, because a receipt
  cannot un-exist.

WHAT `now` MEANS FOR A CAPTURE, AND WHY IT IS NOT A FILE MTIME
--------------------------------------------------------------
`ls -l` prints `Mon DD HH:MM` with no year, so `parse_sysstat_ls` needs the
instant the listing was taken. The obvious source -- the mtime of the capture
file in this repo -- is wrong: git does not preserve mtimes, so a fresh clone
would date every capture to its checkout. This module derives `now` from
INSIDE the capture: the LAST ENTRY column of boot index 0 in
`journal-boots.txt` is the newest journal line at capture time. Captures that
predate step 3b of the capture plan have no boot table, and for those the
caller must declare `now` explicitly; the ledger records which of the two it
used per capture (`now_source`), so a reader can tell a derived date from a
declared one.

Pure text-in / dict-out. It opens no socket and runs no command, so it cannot
reach the NUC's port 8001.

Usage:
    python3 nuc/fossil_ledger.py build   --captures state/nuc-capture-r*
    python3 nuc/fossil_ledger.py append  --captures state/nuc-capture-r* \
                                         --ledger state/nuc-fossil-ledger.jsonl
    python3 nuc/fossil_ledger.py verify  --ledger state/nuc-fossil-ledger.jsonl
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import summary_fossil as sf  # noqa: E402

#: A verdict is a claim about the world; a refusal is the module declining to
#: make one. Only verdicts can conflict, and only verdicts count as coverage.
VERDICTS = ("fire_ran", "fire_missed")
REFUSALS = ("fire_pending",)

#: `now` for captures taken before the capture plan grew a boot table
#: (step 3b, round 424). Round 478's `RETRO` table in
#: nuc/tests/test_summary_fossil.py had to pick these same values and they are
#: reproduced -- not re-guessed -- here. Each is after that capture's newest
#: sar sample and before the next 00:07.
DECLARED_NOW = {
    "nuc-capture-r400": "2026-08-31T12:00:00Z",
}

_BOOT0_RE = re.compile(
    r"^\s*0\s+[0-9a-f]{32}\s+\w{3}\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}"
    r"\s+\w+\s+\w{3}\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+\w+\s*$")


def capture_now(capture_dir: str) -> tuple:
    """(now_utc, source) for a capture. Never a filesystem mtime -- see module docstring."""
    name = os.path.basename(capture_dir.rstrip("/"))
    boots = os.path.join(capture_dir, "journal-boots.txt")
    if os.path.exists(boots):
        with open(boots, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = _BOOT0_RE.match(line)
                if m:
                    return f"{m.group(1)}T{m.group(2)}Z", "boot_table"
    if name in DECLARED_NOW:
        return DECLARED_NOW[name], "declared"
    return None, "unknown"


def read_capture(capture_dir: str, now_utc: str = None) -> dict:
    """One capture -> {ok, now_utc, now_source, fires|reason}.

    A capture with no sysstat listing is NOT skipped. Round 406's lesson is
    that the expensive failure is not a missing input, it is a missing input
    that leaves no trace: the down-round captures in this repo have no
    `sar-all.txt` at all, and a `glob` that quietly drops them would report
    the union as covering every capture the program has ever taken.
    """
    name = os.path.basename(capture_dir.rstrip("/"))
    derived, source = capture_now(capture_dir)
    if now_utc:
        derived, source = now_utc, "argument"
    if derived is None:
        return {"capture": name, "ok": False, "now_utc": None,
                "now_source": source,
                "reason": "no journal-boots.txt and no declared `now`; "
                          "an `ls -l` year cannot be reconstructed"}
    try:
        ls_text = sf.read_listing(capture_dir)
    except SystemExit as exc:
        return {"capture": name, "ok": False, "now_utc": derived,
                "now_source": source, "reason": str(exc)}
    if not any(sf._SA_RE.match(e["name"]) or sf._SAR_RE.match(e["name"])
               for e in sf.parse_sysstat_ls(ls_text, derived)):
        return {"capture": name, "ok": False, "now_utc": derived,
                "now_source": source,
                "reason": "listing present but holds no sa/sar day files"}
    rep = sf.fires(ls_text, derived)
    return {"capture": name, "ok": True, "now_utc": derived,
            "now_source": source, "fires": rep}


def build(capture_dirs: list, now_overrides: dict = None) -> dict:
    """Union the per-capture fire tables, keyed by fire instant."""
    now_overrides = now_overrides or {}
    read, unusable = [], []
    for d in sorted(capture_dirs):
        name = os.path.basename(d.rstrip("/"))
        got = read_capture(d, now_overrides.get(name))
        (read if got["ok"] else unusable).append(got)

    # instant -> {verdict -> [(capture, evidence)]}
    votes = collections.defaultdict(lambda: collections.defaultdict(list))
    for got in read:
        for row in got["fires"]["fires"]:
            if row["verdict"] in REFUSALS or row["fire_utc"] is None:
                continue
            votes[row["fire_utc"]][row["verdict"]].append(
                (got["capture"], row.get("evidence", "day_file")))

    days, disagree = [], []
    for instant in sorted(votes):
        cast = votes[instant]
        sources = sorted({c for v in cast.values() for c, _ in v})
        rec = {
            "fire_utc": instant,
            "verdict": None,
            "n_captures": len(sources),
            "captures": sources,
            "evidence": sorted({e for v in cast.values() for _, e in v}),
        }
        if len(cast) == 1:
            rec["verdict"] = next(iter(cast))
        else:
            rec["verdict"] = "DISAGREE"
            rec["claims"] = {v: sorted(c for c, _ in pairs)
                             for v, pairs in cast.items()}
            disagree.append(rec)
        days.append(rec)

    # Count what the capture actually CONTRIBUTES, not what `fires` scored.
    # The two differ: with no receipt anywhere in a listing there is no
    # schedule to derive (round 448 -- never hardcode 00:07), so every row
    # comes back with `fire_utc: None` while still carrying a verdict word.
    # Summing `counts` there reports a number that reads as coverage and
    # unions to nothing, which is the exact failure mode this module exists
    # to make impossible. Found by
    # test_a_capture_with_no_receipts_contributes_nothing_and_says_so.
    per_capture = {}
    for got in read:
        per_capture[got["capture"]] = sum(
            1 for row in got["fires"]["fires"]
            if row["verdict"] in VERDICTS and row["fire_utc"] is not None)
    best = max(per_capture.items(), key=lambda kv: (kv[1], kv[0]),
               default=(None, 0))

    only_one = [d["fire_utc"] for d in days if d["n_captures"] == 1]
    sole = collections.Counter(
        d["captures"][0] for d in days if d["n_captures"] == 1)

    return {
        "n_captures_read": len(read),
        "n_captures_unusable": len(unusable),
        "unusable": unusable,
        "captures": [{"capture": g["capture"], "now_utc": g["now_utc"],
                      "now_source": g["now_source"],
                      "n_decidable": per_capture[g["capture"]]}
                     for g in read],
        "n_fire_days_union": len(days),
        "n_fire_days_best_single": best[1],
        "best_single_capture": best[0],
        "union_gain": len(days) - best[1],
        "days": days,
        "n_disagree": len(disagree),
        "disagreements": disagree,
        "n_sole_source": len(only_one),
        "sole_source_fires_utc": only_one,
        "sole_source_by_capture": dict(sole),
        "counts": dict(collections.Counter(d["verdict"] for d in days)),
        "note": "a fire in `sole_source_fires_utc` is one that survives in "
                "exactly one capture; delete that capture and the record of "
                "that instant leaves this program entirely.",
    }


def append(report: dict, ledger_path: str) -> dict:
    """Append one JSONL record per fire instant, idempotently.

    Idempotent on (fire_utc, verdict): re-running on the same captures adds
    nothing. A CHANGED verdict for an instant already in the ledger is
    appended anyway and flagged -- the ledger is append-only and a
    contradiction against history is exactly what a reader must see, not
    something a writer gets to silently overwrite.
    """
    seen = {}
    if os.path.exists(ledger_path):
        with open(ledger_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "fire_utc" in rec:
                    seen[rec["fire_utc"]] = rec.get("verdict")

    added, contradictions, unchanged = [], [], 0
    for d in report["days"]:
        prior = seen.get(d["fire_utc"], "\x00")
        if prior == d["verdict"]:
            unchanged += 1
            continue
        rec = dict(d)
        if prior != "\x00":
            rec["contradicts_prior"] = prior
            contradictions.append(d["fire_utc"])
        added.append(rec)

    os.makedirs(os.path.dirname(ledger_path) or ".", exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as fh:
        for rec in added:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return {"ledger": ledger_path, "n_appended": len(added),
            "n_unchanged": unchanged, "n_contradictions": len(contradictions),
            "contradictions": contradictions,
            "appended_fires_utc": [r["fire_utc"] for r in added]}


def verify(ledger_path: str) -> dict:
    """Read the ledger back and report its own internal consistency."""
    by_instant = collections.defaultdict(list)
    n_lines, bad = 0, []
    with open(ledger_path, "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            n_lines += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                bad.append({"line": i, "error": str(exc)})
                continue
            by_instant[rec.get("fire_utc")].append(rec.get("verdict"))
    conflict = {k: sorted(set(v)) for k, v in by_instant.items()
                if len(set(v)) > 1}
    return {
        "ledger": ledger_path,
        "n_lines": n_lines,
        "n_unparseable": len(bad),
        "unparseable": bad,
        "n_instants": len(by_instant),
        "n_conflicting_instants": len(conflict),
        "conflicting_instants": conflict,
        "counts": dict(collections.Counter(
            v[-1] for v in by_instant.values())),
        "span_utc": ([min(by_instant), max(by_instant)]
                     if by_instant else None),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="mode", required=True)
    for name, helptext in (
            ("build", "union the fire tables of every capture given"),
            ("append", "build, then append to the durable JSONL ledger")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--captures", nargs="+", required=True,
                        help="capture directories (globs are fine)")
        sp.add_argument("--now", action="append", default=[],
                        metavar="CAPTURE=UTC",
                        help="declare `now` for a capture with no boot table")
        sp.add_argument("--strict", action="store_true",
                        help="exit 1 on any DISAGREE row")
        if name == "append":
            sp.add_argument("--ledger",
                            default="state/nuc-fossil-ledger.jsonl")
    vp = sub.add_parser("verify", help="read the ledger back, report conflicts")
    vp.add_argument("--ledger", default="state/nuc-fossil-ledger.jsonl")
    vp.add_argument("--strict", action="store_true",
                    help="exit 1 on any conflicting instant")
    args = p.parse_args(argv)

    if args.mode == "verify":
        rep = verify(args.ledger)
        print(json.dumps(rep, indent=2))
        return 1 if (args.strict and (rep["n_conflicting_instants"] or
                                      rep["n_unparseable"])) else 0

    dirs = []
    for pat in args.captures:
        hit = sorted(glob.glob(pat))
        dirs.extend(hit if hit else [pat])
    overrides = dict(kv.split("=", 1) for kv in args.now)
    rep = build(dirs, overrides)
    if args.mode == "append":
        rep["ledger"] = append(rep, args.ledger)
    print(json.dumps(rep, indent=2))
    return 1 if (args.strict and rep["n_disagree"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
