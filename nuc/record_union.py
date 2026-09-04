#!/usr/bin/env python3
"""Union the box's own record — sar day-files and journal — across captures.

Round 490 (NUC-integration E). Round 484 built `fossil_ledger.py`, which
unions the SYSSTAT SWEEP EVIDENCE across every capture in this repo and found
11 fire instants where the newest capture alone sees 8. The same nine capture
directories carry the `sar` day-files and the `systemd` journal that
`perturbation.BucketMap` is built from — and nothing has ever unioned those.

The cost of not doing it, measured before this module existed:

  * `state/nuc-capture-r424/sar-all.txt` is the ONLY sar record any published
    number in this track has been computed from. `grep -rl nuc-capture-r478`
    over `*.py` returns `fossil_ledger.py` and two test files; `perturbation.py`
    and `dose_response.py` name r424 and nothing else.
  * r424 holds 2026-08-23..08-31 plus a 2174-byte 09-01 — three samples, taken
    at 08:12Z while the day was two hours old.
  * r478 holds the SAME 08-23..08-31, a complete 9616-byte 09-01, and 09-03.
  * r484 holds 08-27..09-04 and has LOST 08-23..08-26 to the 00:07 sweep round
    484 itself watched fire.

So the newest capture is not the best one, the best one does not exist, and
the union of the three covers 12 dates where no single capture covers more
than 11. Round 472's central limitation — "round 424's capture IS the end of
the record, and the six most recent E rounds are untestable for want of a
newer one" — was answerable offline from files already committed.

Three rules, taken from `fossil_ledger.py` because they were right there:

  * **Agreement is the null.** Two captures of the same day-file are two reads
    of one append-only file, so they must agree wherever they overlap. A
    disagreement is an instrument or a capture being wrong and is reported as
    a CONFLICT, never averaged, never silently resolved.
  * **The comparison is per timestamped ROW, not per section.** `sar` prints a
    trailing `Average:` computed over the rows it was given, so r424's 09-01
    average is over 3 samples and r478's over 30. A byte- or line-level diff
    calls that a conflict; it is not one, and a module that reported it would
    have taught the next round to distrust a clean union.
  * **An unusable input is named, not skipped.** Five of the nine captures
    carry no sar at all.

Nothing here contacts the box. It is text in, text out.

CLI
    python3 nuc/record_union.py sar     --captures DIR... [--out FILE]
    python3 nuc/record_union.py journal --captures DIR... [--out FILE]
    python3 nuc/record_union.py build   --captures DIR... --out-dir DIR
    python3 nuc/record_union.py frame   --captures DIR...   # what it buys
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from perturbation import (                                   # noqa: E402
    PerturbationError, parse_sar, parse_unit_starts, sar_banner_date,
    sar_sections, window_frame,
)

SAR_FILE = "sar-all.txt"
JOURNAL_FILE = "journal-pid1-full.txt"

_SECTION_KIND = re.compile(r"^(SAR_[A-Z]+)_SA(\d{2})$")
_TIME_TOKEN = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")
_RESTART = re.compile(r"LINUX RESTART", re.I)
_BANNER = re.compile(r"^Linux\b")
_ISO_LEAD = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})")

# `parse_sar` treats a row whose fields are non-numeric as a repeated header.
# We only need to know "is this a data row", and the cheapest honest test is
# the one `parse_sar` itself uses: the second token parses as a float.
def _is_data_row(parts) -> bool:
    body = parts[1:]
    if body and body[0] in ("AM", "PM"):
        body = body[1:]
    if not body:
        return False
    try:
        float(body[0])
    except ValueError:
        return False
    return True


def split_section(body: str) -> dict:
    """One sar section -> its preamble, its data rows keyed by stamp, its tail.

    `stamp` is the raw first token plus any AM/PM, which is what makes two
    captures of the same day comparable without re-deriving a clock. Restart
    markers are attached to the row they precede, because that is what they
    mean to `parse_sar` (`restart_before`) and detaching them would move a
    boot.
    """
    preamble, rows, order, tail = [], {}, [], []
    pending = []
    seen_data = False
    for raw in body.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s:
            (tail if seen_data else preamble).append(line)
            continue
        if _RESTART.search(s):
            pending.append(line)
            continue
        parts = s.split()
        if _BANNER.match(s) or not _TIME_TOKEN.match(parts[0]):
            # `Average:` lands here, in `tail`, because it never carries a
            # `HH:MM:SS` first token. Round 490's mutation pass found the
            # explicit `startswith("Average:")` branch this used to have was
            # DEAD -- both arms reached `tail`, since sar cannot print an
            # average before any data row. Round 466's F7 rule: a branch no
            # test can exercise goes, it does not get a comment promising it
            # is fine.
            (tail if seen_data else preamble).append(line)
            continue
        if not _is_data_row(parts):          # a (possibly repeated) header row
            (tail if seen_data else preamble).append(line)
            continue
        stamp = parts[0]
        if len(parts) > 1 and parts[1] in ("AM", "PM"):
            stamp = parts[0] + " " + parts[1]
        seen_data = True
        if stamp not in rows:
            order.append(stamp)
        rows[stamp] = {"line": line, "restart_before": tuple(pending),
                       "fields": tuple(s.split()[1:])}
        pending = []
    return {"preamble": preamble, "rows": rows, "order": order, "tail": tail,
            "trailing_restart": tuple(pending)}


def _norm(fields) -> tuple:
    return tuple(fields)


def merge_section(candidates: list) -> dict:
    """[(capture, body)] for ONE (kind, date) -> merged text + a verdict.

    `candidates` are reads of the same append-only file at different times, so
    the expected shape is a chain of prefixes and the expected strategy is
    `verbatim_superset`: emit the longest one's own bytes and touch nothing.
    The merge path exists for the case that is not true, and it exists
    *reporting* that it was taken.
    """
    parsed = [(cap, split_section(body)) for cap, body in candidates]
    conflicts = []
    union_stamps: dict = {}
    for cap, p in parsed:
        for stamp in p["order"]:
            row = p["rows"][stamp]
            prev = union_stamps.get(stamp)
            if prev is None:
                union_stamps[stamp] = {"line": row["line"],
                                       "restart_before": row["restart_before"],
                                       "fields": row["fields"], "from": cap}
                continue
            if _norm(prev["fields"]) != _norm(row["fields"]):
                conflicts.append({
                    "stamp": stamp, "a_capture": prev["from"],
                    "b_capture": cap,
                    "a": " ".join(prev["fields"]),
                    "b": " ".join(row["fields"]),
                })
            if prev["restart_before"] != row["restart_before"]:
                conflicts.append({
                    "stamp": stamp, "a_capture": prev["from"],
                    "b_capture": cap, "field": "restart_before",
                    "a": list(prev["restart_before"]),
                    "b": list(row["restart_before"]),
                })

    per_capture = {cap: len(p["rows"]) for cap, p in parsed}
    n_union = len(union_stamps)
    supersets = [cap for cap, p in parsed if len(p["rows"]) == n_union
                 and set(p["rows"]) == set(union_stamps)]

    if supersets and not conflicts:
        # the ordinary case: one capture already holds every row
        best = max(supersets, key=lambda c: len(dict(candidates)[c]))
        return {"strategy": "verbatim_superset", "chosen_capture": best,
                "text": dict(candidates)[best], "n_rows_union": n_union,
                "n_rows_per_capture": per_capture, "conflicts": conflicts,
                "n_conflicts": len(conflicts),
                "average_line_dropped": False,
                "contributing_captures": [c for c, _ in parsed]}

    # merged: preamble from the widest candidate, rows in stamp order, and
    # NO `Average:` -- an average over rows we did not emit is a lie with a
    # colon in it.
    widest = max(parsed, key=lambda cp: len(cp[1]["rows"]))[1]
    order = sorted(union_stamps, key=_stamp_key)
    out = list(widest["preamble"])
    for stamp in order:
        row = union_stamps[stamp]
        out.extend(row["restart_before"])
        out.append(row["line"])
    return {"strategy": "merged_rows", "chosen_capture": None,
            "text": "\n".join(out), "n_rows_union": n_union,
            "n_rows_per_capture": per_capture, "conflicts": conflicts,
            "n_conflicts": len(conflicts),
            "average_line_dropped": True,
            "contributing_captures": [c for c, _ in parsed]}


def _stamp_key(stamp: str):
    parts = stamp.split()
    h, m, s = (int(x) for x in parts[0].split(":"))
    if len(parts) > 1:
        if parts[1] == "PM" and h != 12:
            h += 12
        elif parts[1] == "AM" and h == 12:
            h = 0
    return h * 3600 + m * 60 + s


def read_capture_sar(path: str):
    """(sections, note). A capture with no `sar-all.txt` is NAMED, not dropped."""
    f = os.path.join(path, SAR_FILE)
    if not os.path.exists(f):
        return None, "no %s" % SAR_FILE
    text = open(f, errors="replace").read()
    secs = sar_sections(text)
    if not secs:
        return None, "%s has no `### SECTION` headers" % SAR_FILE
    return secs, None


def union_sar(capture_paths) -> tuple:
    """Every capture's sar day-files unioned into ONE `sar-all.txt` text."""
    by_key: dict = {}
    unusable, used = [], []
    undated = []
    for path in capture_paths:
        secs, note = read_capture_sar(path)
        cap = os.path.basename(path.rstrip("/"))
        if secs is None:
            unusable.append({"capture": cap, "why": note})
            continue
        used.append(cap)
        for name, body in secs.items():
            m = _SECTION_KIND.match(name)
            if not m:
                undated.append({"capture": cap, "section": name,
                                "why": "not a SAR_<KIND>_SA<DD> section"})
                continue
            try:
                date = sar_banner_date(body)
            except PerturbationError as e:
                undated.append({"capture": cap, "section": name,
                                "why": str(e)})
                continue
            if int(m.group(2)) != int(date[8:10]):
                undated.append({"capture": cap, "section": name,
                                "why": "name says day %s, banner says %s"
                                       % (m.group(2), date)})
                continue
            by_key.setdefault((m.group(1), date), []).append((cap, body, name))

    sections, per_key = [], []
    for (kind, date) in sorted(by_key, key=lambda k: (k[1], k[0])):
        cands = by_key[(kind, date)]
        res = merge_section([(c, b) for c, b, _ in cands])
        name = cands[0][2]
        names = sorted({n for _, _, n in cands})
        if len(names) > 1:                                   # pragma: no cover
            raise PerturbationError(
                "kind %s date %s reached this repo under two section names: %s"
                % (kind, date, names))
        sections.append("### %s\n%s" % (name, res["text"]))
        per_key.append({"kind": kind, "date": date, "section": name,
                        "strategy": res["strategy"],
                        "chosen_capture": res["chosen_capture"],
                        "contributing_captures": res["contributing_captures"],
                        "n_rows_per_capture": res["n_rows_per_capture"],
                        "n_rows_union": res["n_rows_union"],
                        "n_conflicts": res["n_conflicts"],
                        "conflicts": res["conflicts"][:8],
                        "average_line_dropped": res["average_line_dropped"]})

    dates = sorted({d for _, d in by_key})
    report = {
        "n_captures_read": len(used),
        "captures_read": used,
        "n_captures_unusable": len(unusable),
        "unusable": unusable,
        "n_sections": len(per_key),
        "dates": dates,
        "n_dates": len(dates),
        "n_conflicts": sum(k["n_conflicts"] for k in per_key),
        "n_merged_sections": sum(1 for k in per_key
                                 if k["strategy"] == "merged_rows"),
        "undated_or_unnamed_sections": undated,
        "per_section": per_key,
        "why": ("two reads of one append-only day-file must agree where they "
                "overlap; the union is only sound because the conflict count "
                "is reported beside it"),
    }
    return "\n".join(sections) + "\n", report


def _multiplicity_losses(streams, mult) -> list:
    """Lines the union carries fewer copies of than some capture does."""
    losses = []
    for cap, lines in streams:
        counts: dict = {}
        for l in lines:
            counts[l] = counts.get(l, 0) + 1
        for line, k in counts.items():
            if mult.get(line, 0) < k:
                losses.append({"capture": cap, "line": line[:120],
                               "in_capture": k, "in_union": mult.get(line, 0)})
    return losses


def union_journal(capture_paths, filename: str = JOURNAL_FILE) -> tuple:
    """Every capture's journal unioned, in time order, as a MULTISET.

    The first draft deduped by whole line and its own `--strict` gate caught
    it: each of the three journals in this repo holds 2-3 lines that are
    byte-identical to another line in the SAME file --

        2026-08-26T12:23:21+00:00 pgain-nuc systemd[1]: Reloading...
        2026-08-30T00:32:34+00:00 pgain-nuc systemd[1]: Starting rsyslog...

    -- and those are two real events one second apart in a log whose
    resolution is one second, not one event written twice. Whole-line dedup
    deletes one of each, and `parse_unit_starts` counts fires, so the deletion
    is a fire.

    So the union rule is per-line MULTIPLICITY, not presence: a line that
    appears k times in the capture that shows it most appears k times in the
    union. That is the only rule consistent with "each capture is a READ of
    one append-only journal": two reads of an overlapping region must show the
    same multiplicity, and a capture that shows fewer saw less of the region.

    Separator lines (`-- Boot <id> --`) carry no timestamp of their own. They
    introduce the boot that follows, so they are attached to the NEXT dated
    line and identified by content: the boot id is unique. Where two captures
    attach the same separator to different instants, journald has eaten the
    front of that boot between the two captures -- round 484 measured 5h30m of
    exactly that -- so the EARLIEST attachment is kept and the disagreement is
    reported rather than smoothed.
    """
    streams, unusable, used = [], [], []
    intra_dupes = {}
    for path in capture_paths:
        cap = os.path.basename(path.rstrip("/"))
        f = os.path.join(path, filename)
        if not os.path.exists(f):
            unusable.append({"capture": cap, "why": "no %s" % filename})
            continue
        lines = open(f, errors="replace").read().splitlines()
        if not lines:
            unusable.append({"capture": cap, "why": "%s is empty" % filename})
            continue
        used.append(cap)
        counts = {}
        for l in lines:
            counts[l] = counts.get(l, 0) + 1
        intra_dupes[cap] = sum(c - 1 for c in counts.values() if c > 1)
        streams.append((cap, lines))

    if not streams:
        raise PerturbationError("no capture carries %s" % filename)

    # -- pass 1: per capture, split into dated lines (with multiplicity) and
    #    separators attached to the dated line that FOLLOWS them.
    mult: dict = {}                       # line -> max multiplicity seen
    first_seen: dict = {}                 # line -> (ts, stream_idx, line_idx)
    sep_at: dict = {}                     # separator line -> ts it introduces
    sep_disagreements = []
    n_sep = 0
    trailing_separators = []
    for si, (cap, lines) in enumerate(streams):
        pending_seps = []
        counts: dict = {}
        for li, line in enumerate(lines):
            m = _ISO_LEAD.match(line)
            if not m:
                n_sep += 1
                pending_seps.append(line)
                continue
            ts = m.group(1) + "T" + m.group(2)
            for sep in pending_seps:
                prev = sep_at.get(sep)
                if prev is None:
                    sep_at[sep] = ts
                    first_seen.setdefault(sep, (ts, si, li - 0.5))
                    mult[sep] = 1
                elif prev != ts:
                    sep_disagreements.append(
                        {"separator": sep, "kept": min(prev, ts),
                         "also_seen_at": max(prev, ts), "capture": cap})
                    if ts < prev:
                        sep_at[sep] = ts
                        first_seen[sep] = (ts, si, li - 0.5)
            pending_seps = []
            counts[line] = counts.get(line, 0) + 1
            k = counts[line]
            if k > mult.get(line, 0):
                mult[line] = k
            first_seen.setdefault(line, (ts, si, li))
        for sep in pending_seps:                             # pragma: no cover
            trailing_separators.append({"capture": cap, "separator": sep})

    items = []
    for line, k in mult.items():
        ts, si, li = first_seen[line]
        for j in range(k):
            items.append((ts, si, li, j, line))
    items.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    out = [t[4] for t in items]

    per_capture = {cap: len(lines) for cap, lines in streams}
    spans = {}
    for cap, lines in streams:
        st = [m.group(0) for m in (_ISO_LEAD.match(l) for l in lines) if m]
        spans[cap] = [st[0], st[-1]] if st else None
    union_stamps = [m.group(0) for m in (_ISO_LEAD.match(l) for l in out) if m]
    per_capture_fires = {}
    for cap, lines in streams:
        per_capture_fires[cap] = len(parse_unit_starts("\n".join(lines)))
    report = {
        "file": filename,
        "n_captures_read": len(used),
        "captures_read": used,
        "n_captures_unusable": len(unusable),
        "unusable": unusable,
        "n_lines_per_capture": per_capture,
        "n_lines_all": sum(per_capture.values()),
        "n_lines_union": len(out),
        "n_distinct_lines": len(mult),
        "n_lines_kept_by_multiplicity": len(out) - len(mult),
        "n_intra_capture_duplicate_lines": intra_dupes,
        # Not an assertion: a re-derivation. For every capture and every line
        # in it, does the union carry AT LEAST as many copies? That is what
        # "the union loses nothing" means, and it is cheap enough to check
        # rather than argue.
        "dedup_is_lossless": not _multiplicity_losses(streams, mult),
        "multiplicity_losses": _multiplicity_losses(streams, mult)[:8],
        "n_separator_lines_seen": n_sep,
        "n_separators_kept": sum(1 for l in mult if l in sep_at),
        "separator_attachment_disagreements": sep_disagreements,
        "trailing_separators": trailing_separators,
        "n_unit_starts_per_capture": per_capture_fires,
        "n_unit_starts_union": len(parse_unit_starts("\n".join(out))),
        "span_per_capture": spans,
        "span_union": ([union_stamps[0], union_stamps[-1]]
                       if union_stamps else None),
        "why": ("journald eats its own front -- round 484 measured 5h30m of "
                "one boot's interior vanishing between two captures -- so the "
                "newest journal is not a superset of the older ones and the "
                "union is the only complete record this program will ever "
                "have of those days"),
    }
    return "\n".join(out) + "\n", report


def frame_gain(capture_paths, sar_text=None, journal_text=None) -> dict:
    """What the union buys `window_frame`, against each capture alone.

    The only number that matters is `n_paired`: a sar day with no journal fire
    on the same date is dropped by `window_frame`, so unioning sar without
    unioning the journal buys much less than it looks like it should.
    """
    if sar_text is None:
        sar_text, _ = union_sar(capture_paths)
    if journal_text is None:
        journal_text, _ = union_journal(capture_paths)

    def frame(st, jt):
        f = window_frame(st, jt)
        return {"n_paired": f["n_paired"], "n_sar_only": f["n_sar_only"],
                "n_journal_only": f["n_journal_only"],
                "poolable_dates": f["poolable_dates"],
                "dropped_dates": f["dropped_dates"],
                "n_buckets_poolable": f["n_buckets_poolable"]}

    singles = {}
    for path in capture_paths:
        cap = os.path.basename(path.rstrip("/"))
        sp = os.path.join(path, SAR_FILE)
        jp = os.path.join(path, JOURNAL_FILE)
        if not (os.path.exists(sp) and os.path.exists(jp)):
            singles[cap] = {"unusable": True}
            continue
        try:
            singles[cap] = frame(open(sp, errors="replace").read(),
                                 open(jp, errors="replace").read())
        except PerturbationError as e:                        # pragma: no cover
            singles[cap] = {"error": str(e)}

    union = frame(sar_text, journal_text)
    with_journal = sorted(p for p in capture_paths
                          if os.path.exists(os.path.join(p, JOURNAL_FILE)))
    if with_journal:
        newest = with_journal[-1]
        mixed = frame(sar_text,
                      open(os.path.join(newest, JOURNAL_FILE),
                           errors="replace").read())
        mixed["journal_from"] = os.path.basename(newest.rstrip("/"))
    else:                                                    # pragma: no cover
        mixed = {"unusable": True}
    best_single = max((v.get("n_paired", -1) for v in singles.values()),
                      default=-1)
    return {
        "union": union,
        "per_capture": singles,
        "union_sar_newest_journal_only": mixed,
        "best_single_n_paired": best_single,
        "union_n_paired": union["n_paired"],
        "gain_over_best_single": union["n_paired"] - best_single,
        "why": ("`n_paired` is the population every window-level number in "
                "this track is computed over; `union_sar_newest_journal_only` "
                "is here because unioning only half the record is the "
                "plausible mistake"),
    }


# ------------------------------------------------------------------ CLI

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="mode", required=True)
    for name, helptext in (("sar", "union the sar day-files"),
                           ("journal", "union the pid-1 journal"),
                           ("frame", "what the union buys `window_frame`"),
                           ("build", "write both unioned files to a directory")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--captures", nargs="+", required=True)
        sp.add_argument("--strict", action="store_true",
                        help="exit 1 on any conflict, lossy dedup, or (for "
                             "`frame`) no gain over the best single capture")
        if name in ("sar", "journal"):
            sp.add_argument("--out", default=None,
                            help="write the unioned text here")
        if name == "build":
            sp.add_argument("--out-dir", required=True)
        if name == "journal":
            sp.add_argument("--file", default=JOURNAL_FILE)

    args = p.parse_args(argv)
    caps = list(args.captures)

    if args.mode == "sar":
        text, rep = union_sar(caps)
        if args.out:
            open(args.out, "w").write(text)
            rep["out"] = args.out
        print(json.dumps(rep, indent=2))
        return 1 if (args.strict and rep["n_conflicts"]) else 0

    if args.mode == "journal":
        text, rep = union_journal(caps, args.file)
        if args.out:
            open(args.out, "w").write(text)
            rep["out"] = args.out
        print(json.dumps(rep, indent=2))
        return 1 if (args.strict and not rep["dedup_is_lossless"]) else 0

    if args.mode == "build":
        st, sr = union_sar(caps)
        jt, jr = union_journal(caps)
        os.makedirs(args.out_dir, exist_ok=True)
        open(os.path.join(args.out_dir, SAR_FILE), "w").write(st)
        open(os.path.join(args.out_dir, JOURNAL_FILE), "w").write(jt)
        rep = {"out_dir": args.out_dir, "sar": sr, "journal": jr}
        print(json.dumps(rep, indent=2))
        bad = sr["n_conflicts"] or not jr["dedup_is_lossless"]
        return 1 if (args.strict and bad) else 0

    rep = frame_gain(caps)
    print(json.dumps(rep, indent=2))
    return 1 if (args.strict and rep["gain_over_best_single"] <= 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
