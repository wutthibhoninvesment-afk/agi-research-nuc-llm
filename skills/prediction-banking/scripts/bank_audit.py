#!/usr/bin/env python3
"""bank_audit.py -- read this program's OWN prediction corpus as data.

Round 471 (skills B). `skills/prediction-banking/SKILL.md` has thirteen
steps, and every one of them was written from the misses of ONE round. The
program has been banking predictions under rule D-013 since round 15 and
scoring them in prose; `state/prediction-bank-ledger.json` records 146 banks
and nothing had ever read the scored rows themselves. This script does.

Two shapes carry a verdict in this tree, and the parser knows both:

  TABLE   `| P3 | text | **MISS** |`  -- a markdown row whose first cell is
          a short prediction id (`P3`, `A1`, `B2b`, `K7`) and one of whose
          other cells holds a verdict word. The verdict column's position is
          NOT fixed across rounds, so it is found by content.
  PROSE   `scored 9 HIT / 6 MISS`, `**10 HIT, 2 HALF, 5 MISS of 17.**` -- an
          aggregate sentence. Rounds that wrote no table still wrote one of
          these, usually in the ledger's own `quote` field.

Having both lets the two be COMPARED, which is the point: the quote is a
sentence somebody typed and the table is data, and this program's history
says that comparison finds things.

Subcommands
-----------
  rows FILE...        parse and print the scoring rows in each file
  aggregate FILE...   parse and print the prose aggregates in each file
  bank FILE           audit ONE PREDICTIONS.md against the SKILL's own
                      mechanical preconditions (step 1 baselines-with-
                      commands, step 2 class tags, the round-468 rate rule,
                      the round-470 read-set, step 9 no-basis)
  corpus              walk the ledger, parse every scored bank's verdicts,
                      cross-check table against prose, and report hit rates
                      split by properties of the prediction TEXT
"""
from __future__ import annotations

import argparse
import glob
import math
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LEDGER = os.path.join(ROOT, "state", "prediction-bank-ledger.json")

# --- verdict vocabulary ----------------------------------------------------
# Order matters: the two-word verdicts and the qualified ones must be tested
# before the bare HIT/MISS they contain, or `WEAK HIT` scores as a full hit
# and `no-basis-reported` never matches at all.
HIT, MISS, HALF, OTHER = "HIT", "MISS", "HALF", "OTHER"

_VERDICT_PATTERNS = [
    (r"\bno[- ]basis[- ]reported\b", OTHER),
    (r"\bunscorable\b|\bunresolvable\b|\bvacuous\b|\bpending\b|\bunscored\b", OTHER),
    (r"\bnot\s+scor\w+\b|\bwithdrawn\b|\bsuperseded\b", OTHER),
    (r"\bweak\s+hit\b|\bhalf\s+hit\b|\bnear\s+hit\b", HALF),
    (r"\bpartial\b|\bhalf\b|\bmixed\b", HALF),
    (r"\bhit\b", HIT),
    (r"\bmiss\b", MISS),
]

# A prediction id: one to three capitals then digits, optionally a trailing
# letter or a prime.  `P3`, `A1`, `B2b`, `K7`, `CP3`, `P10a`.
_ID_RE = re.compile(r"^\*{0,2}([A-Z]{1,3}\d{1,3}[a-z]?)\*{0,2}$")

# Rows whose id cell parses but which are not predictions.  Kept as an
# explicit exclusion list rather than by tightening the regex: the regex is
# what makes the parser work across nine id conventions, and narrowing it to
# dodge a summary row would silently drop real rows in some other round.
_NOT_A_PREDICTION = re.compile(
    r"^\s*(total|sum|overall|all\b|--+|=+)\s*$", re.I)


def classify_verdict(text: str):
    """Return (verdict, matched_span) or (None, None)."""
    low = text.lower()
    for pat, verdict in _VERDICT_PATTERNS:
        m = re.search(pat, low)
        if m:
            return verdict, m.group(0)
    return None, None


# Verdict phrases ANCHORED at the start of a cell. Matching a verdict word
# anywhere in the cell is what broke round 376's P4: its verdict cell reads
# `**HIT** -- 61.6 % partial, ...`, and a scan that looks for `partial`
# before `hit` scores a HIT as a HALF. The note after the verdict is prose
# about the measurement and must not be read as part of the verdict.
_LEAD_VERDICT = [
    (r"no[- ]basis[- ]?\w*", OTHER),
    (r"not\s+(scored|run|established|measured)", OTHER),
    (r"unscor\w*|unresolv\w*|unevaluable|unattributed|vacuous|pending|"
     r"declined|void|abstention", OTHER),
    (r"weak\s+hit|half\s+hit|near\s+hit", HALF),
    (r"partial\w*|half|mixed|split", HALF),
    (r"hits?", HIT),
    (r"miss(es)?", MISS),
]


def leading_verdict(cell: str):
    """(verdict, matched_text) if the cell LEADS with a verdict, else None."""
    lead = cell.lstrip("*_ \t")
    for pat, verdict in _LEAD_VERDICT:
        m = re.match(r"(?:%s)\b" % pat, lead, re.I)
        if m:
            return verdict, m.group(0)
    return None, None


def _split_row(line: str):
    if not line.lstrip().startswith("|"):
        return None
    body = line.strip()
    body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in body.split("|")]


def parse_rows(path: str):
    """Yield dicts for every scoring row in a markdown file."""
    out = []
    with open(path, errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            cells = _split_row(line)
            if not cells or len(cells) < 2:
                continue
            m = _ID_RE.match(cells[0])
            if not m:
                continue
            if _NOT_A_PREDICTION.match(cells[0]):
                continue
            # Pick the VERDICT cell, which is not at a fixed column across
            # rounds. The rule is "a cell that LEADS with a verdict word",
            # preferring a bold one, and taking the last if several qualify.
            #
            # The naive rule -- first cell containing a verdict word -- read
            # round 112's `| R8 | 5 MISS parts | HIT |` as a MISS, because
            # the CLAIM is about how many misses a previous bank would score.
            # That single row was two of the four HIT/MISS discrepancies this
            # script attributed to round 112's headline.
            cands = []
            for i, c in enumerate(cells[1:], 1):
                v, sp = leading_verdict(c)
                if v:
                    cands.append((i, v, sp, c.strip().startswith("**")))
            if cands:
                bold = [c for c in cands if c[3]]
                pick = (bold or cands)[-1]
                vcell, verdict, span = pick[0], pick[1], pick[2]
            else:
                verdict = span = None
                vcell = -1
                for i, c in enumerate(cells[1:], 1):
                    for bmatch in re.findall(r"\*\*([^*]+)\*\*", c):
                        v, sp = classify_verdict(bmatch)
                        if v:
                            verdict, span, vcell = v, sp, i
                            break
                    if verdict:
                        break
                if verdict is None:
                    for i, c in enumerate(cells[1:], 1):
                        v, sp = classify_verdict(c)
                        if v:
                            verdict, span, vcell = v, sp, i
                            break
            if verdict is None:
                continue
            text = " ".join(c for i, c in enumerate(cells) if i not in (0, vcell))
            out.append({
                "file": os.path.relpath(path, ROOT),
                "line": lineno,
                "id": m.group(1),
                "verdict": verdict,
                "matched": span,
                "text": text,
                "verdict_cell": cells[vcell],
            })
    return out


# --- prose aggregates ------------------------------------------------------
# `9 HIT / 6 MISS`, `10 HIT, 2 HALF, 5 MISS of 17`, `7 hits, 3 misses`,
# `6 HIT, 3 PARTIAL, 2 MISS of 11`.
# The leading `(?<![A-Za-z0-9])` is load-bearing and was learned the hard
# way: without it `P11 pending` parses as "11 PENDING", `P4 HIT. P5 HIT.` as
# "4 HIT, 5 HIT", and `M10 HIT (73)` as "10 HIT". The first run of this
# script reported 18 self-inconsistent headlines and 35 headline-vs-table
# disagreements, and the prediction IDS in the prose were manufacturing most
# of them -- the instrument was measuring its own regex.
#
# The OTHER vocabulary is long because this program has invented a new word
# for "not scorable" almost every time it needed one. Every alternative
# below was read off a real headline in `knowledge/`; a term the regex does
# not know does not merely go uncounted, it makes the headline's terms fail
# to sum to its own "of N" and shows up as a fake defect.
_TERM_RE = re.compile(
    r"(?<![A-Za-z0-9])(\d+)\s+"
    r"(clear\s+|outright\s+|further\s+|straight\s+|flat\s+|genuine\s+|real\s+)?"
    r"(HITS?|MISSES|MISS|PARTIALS?|HALVES|HALF|WEAK HITS?|SPLITS?|"
    r"VACUOUS|PENDING|UNSCORABLE|UNSCORED|UNRESOLVED|UNRESOLVABLE[A-Z-]*|"
    r"UNEVALUABLE|VOID|DECLINED|OMISSIONS?|DELIBERATE OMISSIONS?|"
    r"NOT RUN|NOT SCORED|NO-BASIS[A-Z- ]*|BANKED AS NO-BASIS[A-Z- ]*|"
    r"NO-BASIS COMMITMENTS?)\b", re.I)
_OF_RE = re.compile(r"\bof\s+(\d+)\b", re.I)


def parse_aggregates(text: str):
    """Aggregate sentences, with the line each was found on.

    Three things about this tree's prose forced the shape of this function,
    and each was found by hand-checking a false positive it produced:

    * **Headlines WRAP.** `**5 HIT, 3 PARTIAL, 7 MISS of 15**` is split
      across two source lines in round 428, and a line-at-a-time scanner
      saw `3 PARTIAL, 7 MISS of 15` and called the round's arithmetic
      broken. So consecutive prose lines are joined into a paragraph first.
    * **One line can hold FOUR aggregates.** Round 415 wrote
      `... of 5 mechanism; ... of 7 outcome; ... of 3 ledger; ... of 2 cost`.
      So a paragraph is then split on `;`, which survives the join.
    * **Table rows are not headlines.** Round 407's
      `| Q16 | 13-17 HIT of 21 | **MISS** |` is a PREDICTION about a count.
      Table rows, headings and block quotes are excluded from paragraphs.
    """
    out = []
    para, start = [], None
    lines = text.splitlines()

    def flush():
        if not para:
            return
        joined = " ".join(para)
        # Split on `;` AND on sentence boundaries. Round 415 wrote
        # `... of 2 cost. Total 12 HIT / 1 PARTIAL / 4 MISS of 17.` and
        # round 416 `... of 15. By class: ... of 10.` -- one chunk holding
        # two aggregates sums to neither of their totals and reads as an
        # arithmetic error in a round that made none.
        for chunk in re.split(r";|(?<=[.!])\s+(?=[A-Z(])", joined):
            terms = _TERM_RE.findall(chunk)
            if len(terms) < 2:
                continue
            counts = {}
            for n, _adj, word in terms:
                w = word.lower()
                if w.startswith("hit"):
                    k = HIT
                elif w.startswith("miss"):
                    k = MISS
                elif w.startswith(("partial", "half", "halves", "weak")):
                    k = HALF
                else:
                    k = OTHER
                counts[k] = counts.get(k, 0) + int(n)
            # The "of N" must come AFTER the last verdict term and close to
            # it. Searching the whole chunk let round 426's prose supply an
            # "of 93" to a tally 31 lines away, and round 395's environment
            # note supply an "of 2" from "1.5 GiB of 2.0 GiB swap".
            last = None
            for m_ in _TERM_RE.finditer(chunk):
                last = m_
            mo = _OF_RE.search(chunk, last.end(), last.end() + 30) if last else None
            rec = {"counts": counts,
                   "total": int(mo.group(1)) if mo else None,
                   "span": chunk.strip()[:220], "line": start}
            if not any(r["counts"] == rec["counts"] and r["total"] == rec["total"]
                       for r in out):
                out.append(rec)

    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith(("|", "#", ">", "```", "---")):
            flush()
            para, start = [], None
            continue
        if start is None:
            start = i
        para.append(line)
    flush()
    return out


def score(counts):
    """HIT=1, HALF=0.5, MISS=0; OTHER excluded from the denominator."""
    n = counts.get(HIT, 0) + counts.get(HALF, 0) + counts.get(MISS, 0)
    if not n:
        return None, 0
    return (counts.get(HIT, 0) + 0.5 * counts.get(HALF, 0)) / n, n


def two_proportion_z(h1, n1, h2, n2):
    """Pooled two-proportion z. Stdlib only -- no scipy on this box.

    Reported so a gap between two subgroups is not asserted from the point
    estimates alone: `names a path` is 95 rows against 1405, and a 12-point
    gap on 95 rows is a different claim from the same gap on 1000.
    """
    if not n1 or not n2:
        return None, None
    p1, p2 = h1 / n1, h2 / n2
    p = (h1 + h2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (p1 - p2) / se
    # two-sided p from the normal tail, via erfc
    return z, math.erfc(abs(z) / math.sqrt(2))


def subgroup(rows, pred):
    sub = [r for r in rows if pred(r["text"])]
    t = tally(sub)
    r_, k = score(t)
    hits = t.get(HIT, 0) + 0.5 * t.get(HALF, 0)
    return sub, r_, k, hits


def tally(rows):
    c = {}
    for r in rows:
        c[r["verdict"]] = c.get(r["verdict"], 0) + 1
    return c


# --- text properties, for the round-468 and round-470 rules ---------------
_INT_RE = re.compile(r"(?<![\w.])\d+(?![\w.])")
_PATH_RE = re.compile(r"[\w./-]+\.(py|md|json|jsonl|sh|txt|whence)\b")


def has_number(text: str) -> bool:
    """A count/quantity in the prediction text -- round 468's rule."""
    stripped = re.sub(r"`[^`]*`", lambda m: m.group(0), text)
    return bool(_INT_RE.search(stripped))


def names_path(text: str) -> bool:
    """Round 470's rule, through the only proxy the corpus records."""
    return bool(_PATH_RE.search(text))


def _load_ledger():
    with open(LEDGER) as fh:
        return json.load(fh)["banks"]


def _knowledge_files(rnd: str, where: str):
    out = []
    if where:
        p = os.path.join(ROOT, where)
        if os.path.exists(p):
            out.append(p)
    for pad in (rnd.zfill(3), rnd):
        out.extend(glob.glob(os.path.join(ROOT, "knowledge", "round-%s-*.md" % pad)))
    seen, uniq = set(), []
    for p in out:
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


# --- bank audit: the SKILL's own preconditions, mechanically ---------------
# (key, pattern, applies_only_if, why).  `applies_only_if` is None for a
# check that every bank owes, and a regex for one that is conditional: step
# 11's contention rule is about WALL TIMES, and a bank with no duration band
# in it does not owe a contention statement. The first version had no such
# column and reported this round's own bank as failing a rule it could not
# break -- a check that cannot be satisfied gets ignored and then deleted,
# which is `skills/skill-authoring`'s own pitfall.
_BANK_CHECKS = [
    ("banked_before", r"banked\s+BEFORE", None,
     "step 7: the first lines say 'banked BEFORE'"),
    ("baseline_command", r"`(python3|bash|grep|ls|wc|git|pytest|sed|cat)[^`]*`", None,
     "step 1: a baseline carries a runnable command, not a citation"),
    ("class_tag", r"\b(computed|machine-state|STRUCTURAL|RATE)\b", None,
     "step 2: quantities carry a class tag"),
    ("rate_rule_468", r"\bSTRUCTURAL\b[\s\S]{0,600}?\bRATE\b", None,
     "round 468: a structural line with a count in it is banked as a RATE"),
    ("read_set_470", r"already been looked at|read[- ]set|NOT READ|\bUNREAD\b", None,
     "round 470: the bank declares what had been READ when it was written"),
    ("no_basis", r"no[- ]basis", None,
     "step 9: a quantity with no basis says so instead of carrying a number"),
    ("contention",
     r"\bsolo\b|contend\w*|concurrent|under the driver",
     r"\bband\b[^\n]{0,80}?\d+\s*(?:[-\u2013]\s*\d+\s*)?(?:s\b|sec|min|hour|ms\b)"
     r"|\bwall[- ]?(?:clock|time)",
     "step 11: every wall-time band states its contention condition"),
    ("counter_named",
     r"`[^`]*(grep -c|wc -l|--collect-only|len\(|\bcount\b)[^`]*`|"
     r"[Cc]ounter:",
     r"\bband\b[^\n]{0,60}\[\s*\d+\s*,\s*\d+\s*\]|\bcount\b",
     "step 12: every COUNT band names the counter that settles it"),
]

PASS, FAIL, NA = "pass", "fail", "n/a"


def audit_bank(path: str):
    """Return [(key, status, why)] with status in {pass, fail, n/a}."""
    text = open(path, errors="replace").read()
    res = []
    for key, pat, applies, why in _BANK_CHECKS:
        if applies and not re.search(applies, text, re.I):
            res.append((key, NA, why))
            continue
        res.append((key, PASS if re.search(pat, text, re.I) else FAIL, why))
    return res


def cmd_rows(args):
    n = 0
    for pat in args.files:
        for path in sorted(glob.glob(pat)) or [pat]:
            rows = parse_rows(path)
            n += len(rows)
            for r in rows:
                print("%s:%d  %-5s %-5s  %s" % (
                    r["file"], r["line"], r["id"], r["verdict"], r["text"][:110]))
    print("-- %d row(s)" % n)
    return 0


def cmd_aggregate(args):
    for pat in args.files:
        for path in sorted(glob.glob(pat)) or [pat]:
            for a in parse_aggregates(open(path, errors="replace").read()):
                print("%s  %s total=%s\n    %s" % (
                    os.path.relpath(path, ROOT), a["counts"], a["total"], a["span"]))
    return 0


def cmd_bank(args):
    """Audit one or many banks. With more than one file, also print the
    per-check compliance of the whole set -- which is how round 471 measured
    that the corpus obeys the rules it wrote down at very different rates."""
    bad = 0
    agg = {}
    paths = []
    for pat in args.files:
        paths.extend(sorted(glob.glob(pat)) or [pat])
    for path in paths:
        rel = os.path.relpath(os.path.abspath(path), ROOT)
        res = audit_bank(path)
        if not args.quiet:
            print("=== %s" % rel)
        for key, status, why in res:
            agg.setdefault(key, {PASS: 0, FAIL: 0, NA: 0})[status] += 1
            if not args.quiet:
                print("  [%s] %-16s %s" % ({PASS: "x", FAIL: "!", NA: "-"}[status],
                                           key, why))
            if status == FAIL:
                bad += 1
    if len(paths) > 1:
        print("== %d bank(s): per-check compliance ==" % len(paths))
        for key, c in agg.items():
            den = c[PASS] + c[FAIL]
            print("  %-16s %3d/%3d applicable pass (%s)  n/a %d" % (
                key, c[PASS], den, "%.0f%%" % (100.0 * c[PASS] / den) if den else "-",
                c[NA]))
    return 1 if (bad and args.strict) else 0


def _cited_files(banks):
    """path -> set(round) for every file a scored bank points at.

    A bank's `where` may name ANOTHER round's knowledge file -- rounds 31,
    100 and 401 were each scored late, by rounds 109, 106 and 407. So a file
    can be claimed by more than one bank, and the first version of this
    script counted such a file's rows once per claimant: rounds 100 and 106
    both reported the same 22 rows, and round 401 reported 46 because it
    globbed its own file AND the one that scored it. Files are therefore the
    unit here, parsed exactly once, with the claimants recorded.
    """
    owners = {}
    for rnd, e in banks.items():
        if e.get("status") != "scored":
            continue
        for f in _knowledge_files(rnd, e.get("where", "")):
            owners.setdefault(os.path.relpath(f, ROOT), set()).add(int(rnd))
    return owners


def _in_file_aggregates(path):
    """Headline aggregates written IN a knowledge file.

    Skipped for the shared state files: `state/research-state.md` is 28k
    lines covering 470 rounds, so an aggregate found anywhere in it is not
    evidence about the bank that cites it. Three banks (346, 358, 365) point
    there, and the first version of this script attributed the same
    round-381 headline to all three.
    """
    if not path.startswith("knowledge/"):
        return []
    return parse_aggregates(open(os.path.join(ROOT, path), errors="replace").read())


def cmd_corpus(args):
    banks = _load_ledger()
    owners = _cited_files(banks)

    per_file = {}
    for path in sorted(owners):
        rows = parse_rows(os.path.join(ROOT, path))
        per_file[path] = {"rows": rows, "owners": sorted(owners[path])}

    # corpus totals: every row counted ONCE, however many banks cite its file
    rows_all = [r for v in per_file.values() for r in v["rows"]]
    t = tally(rows_all)
    rate, n = score(t)

    print("== corpus ==")
    print("scored banks in ledger      : %d" % sum(
        1 for v in banks.values() if v.get("status") == "scored"))
    print("distinct files cited        : %d" % len(per_file))
    print("files yielding >=1 row      : %d" % sum(1 for v in per_file.values() if v["rows"]))
    print("files claimed by >1 bank    : %d %s" % (
        sum(1 for v in per_file.values() if len(v["owners"]) > 1),
        [(p.split("/")[-1][:28], v["owners"]) for p, v in per_file.items()
         if len(v["owners"]) > 1]))
    print("prediction rows parsed      : %d  (deduped by file:line)" % len(rows_all))
    print("tally                       : %s" % t)
    print("lifetime hit rate           : %.1f%% over %d scorable rows" % (100 * rate, n))

    # per-file rate distribution -- P14 asked for the distribution, not a band
    rates = []
    for p, v in sorted(per_file.items()):
        r_, k = score(tally(v["rows"]))
        if r_ is not None and k >= 3:
            rates.append((p, r_, k))
    vals = sorted(x[1] for x in rates)
    m = len(vals)
    lo = min(rates, key=lambda x: x[1])
    hi = max(rates, key=lambda x: x[1])
    print("per-file rate (>=3 rows, %d files): median %.1f%%  p25-p75 %.1f-%.1f%%"
          "  min %.1f%% (%s)  max %.1f%% (%s)" % (
              m, 100 * vals[m // 2], 100 * vals[m // 4], 100 * vals[3 * m // 4],
              100 * lo[1], lo[0].split("/")[-1][:34],
              100 * hi[1], hi[0].split("/")[-1][:34]))

    # --- A. a headline that does not sum to its own "of N" -----------------
    self_bad = []
    for p, v in sorted(per_file.items()):
        for a in _in_file_aggregates(p):
            s_ = sum(a["counts"].values())
            if a["total"] is not None and s_ != a["total"]:
                self_bad.append((p, s_, a["total"], a["span"][:110]))
    print("\n== A. headline whose own terms do not sum to its own 'of N' (%d) ==" % len(self_bad))
    for p, s_, tot, span in self_bad:
        print("  %-52s terms=%d 'of %d'\n      %s" % (p.split("/")[-1][:52], s_, tot, span))

    # --- B. headline HIT count vs the table in the SAME file ---------------
    # The aggregate compared is the one NEAREST the table, not the largest
    # in the file. Several rounds quote OTHER rounds' scores in their prose
    # (round 449 quotes round 447's `1 PARTIAL / 2 no-basis-reported of 21`),
    # and "largest aggregate in the file" picked those.
    hit_bad = []
    for p, v in sorted(per_file.items()):
        if not v["rows"]:
            continue
        aggs = _in_file_aggregates(p)
        if not aggs:
            continue
        lo = min(r["line"] for r in v["rows"])
        hi = max(r["line"] for r in v["rows"])
        def _dist(a):
            if a["line"] is None:
                return 10 ** 6
            return 0 if lo <= a["line"] <= hi else min(abs(a["line"] - lo),
                                                       abs(a["line"] - hi))
        best = min(aggs, key=_dist)
        if _dist(best) > args.near:
            continue
        th, ah = tally(v["rows"]).get(HIT, 0), best["counts"].get(HIT, 0)
        if th != ah:
            hit_bad.append((p, th, ah, sum(best["counts"].values()),
                            len(v["rows"]), best["span"][:100]))
    print("\n== B. headline HIT count vs the table in the SAME file (%d) ==" % len(hit_bad))
    for p, th, ah, an, nr, span in hit_bad:
        print("  %-46s table %2d HIT of %2d rows | headline %2d HIT of %2d\n      %s"
              % (p.split("/")[-1][:46], th, nr, ah, an, span))

    # --- C. ledger quote vs the file it cites, unambiguous banks only ------
    # Split into two grades, because they need different responses:
    #   CONFIRMED  the quote's term count equals the table's row count -- the
    #              same population -- and the HIT counts still differ. One of
    #              the two is wrong about a row nobody has to re-derive.
    #   CANDIDATE  the counts differ too, so the quote may simply be about a
    #              different set of rows (a sub-lettered P4a/P4b, a row the
    #              bank excluded, a second table). Needs a human.
    q_conf, q_cand = [], []
    for rnd in sorted(banks, key=int):
        e = banks[rnd]
        if e.get("status") != "scored":
            continue
        mine = [p for p in owners if int(rnd) in owners[p] and len(owners[p]) == 1
                and per_file[p]["rows"]]
        if len(mine) != 1:
            continue
        aggs = parse_aggregates(e.get("quote", "") or "")
        if not aggs:
            continue
        best = max(aggs, key=lambda a: sum(a["counts"].values()))
        tt = tally(per_file[mine[0]]["rows"])
        qn = sum(best["counts"].values())
        tn = len(per_file[mine[0]]["rows"])
        if tt.get(HIT, 0) == best["counts"].get(HIT, 0):
            continue
        rec = (int(rnd), mine[0], tt.get(HIT, 0), tn,
               best["counts"].get(HIT, 0), qn, best["span"][:90])
        (q_conf if qn == tn else q_cand).append(rec)
    for label, bucket in (("CONFIRMED (same row count, different HIT count)", q_conf),
                          ("CANDIDATE (row counts differ too)", q_cand)):
        print("\n== C. ledger quote vs the cited file's table -- %s (%d) ==" % (
            label, len(bucket)))
        for rd, p, th, tn, qh, qn, span in bucket:
            print("  r%-4d %-40s table %2d HIT of %2d | quote %2d HIT of %2d\n      %s"
                  % (rd, p.split("/")[-1][:40], th, tn, qh, qn, span))
    q_bad = q_conf + q_cand

    # --- D/E. the two rules, with a z-test rather than two point estimates
    for label, pred, title in (
            ("round 468: a COUNT in the prediction text", has_number,
             "D. round 468's rule"),
            ("round 470 proxy: the text NAMES A REPO PATH", names_path,
             "E. round 470's rule, through the only proxy on disk")):
        yes, ry, ky, hy = subgroup(rows_all, pred)
        no, rn, kn, hn = subgroup(rows_all, lambda s_, p_=pred: not p_(s_))
        z, pv = two_proportion_z(hy, ky, hn, kn)
        print("\n== %s ==" % title)
        print("  %-34s %5d rows  %.1f%% over %d" % ("yes: " + label[:28], len(yes), 100 * ry, ky))
        print("  %-34s %5d rows  %.1f%% over %d" % ("no", len(no), 100 * rn, kn))
        print("  gap %+.1f points   z = %+.2f   two-sided p = %.4f" % (
            100 * (ry - rn), z, pv))

    # --- E2. the 2x2, because the two properties are not independent -------
    print("\n== E2. 2x2: is the path effect just the count effect again? ==")
    print("  %-22s %-24s %s" % ("", "has an integer", "no integer"))
    for pl, pp in (("names a path", True), ("no path", False)):
        cells = []
        for hn_ in (True, False):
            sub, r_, k, _ = subgroup(
                rows_all,
                lambda s_, a=pp, b=hn_: (names_path(s_) == a) and (has_number(s_) == b))
            cells.append("%.1f%% (n=%d)" % (100 * r_, k) if r_ is not None else "-")
        print("  %-22s %-24s %s" % (pl, cells[0], cells[1]))

    # --- F. drift ----------------------------------------------------------
    print("\n== F. drift, by round of the FILE (not of the bank) ==")
    def _rnd_of(path):
        mo = re.search(r"round-(\d+)", path)
        return int(mo.group(1)) if mo else None
    dated = sorted((f for f in per_file if _rnd_of(f) and per_file[f]["rows"]),
                   key=_rnd_of)
    for label, sel in (("first 30 files", dated[:30]), ("last 30 files", dated[-30:])):
        sub = [r for f in sel for r in per_file[f]["rows"]]
        r_, k = score(tally(sub))
        print("  %-15s r%d-r%d  %4d rows  %.1f%% over %d" % (
            label, _rnd_of(sel[0]), _rnd_of(sel[-1]), len(sub), 100 * r_, k))

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({
                "total_rows": len(rows_all), "tally": t, "rate": rate,
                "per_file": {p: {"rows": len(v["rows"]), "tally": tally(v["rows"]),
                                 "owners": v["owners"]} for p, v in per_file.items()},
                "self_inconsistent_headlines": [
                    {"file": a, "terms": b, "of": c, "span": d} for a, b, c, d in self_bad],
                "headline_vs_table": [
                    {"file": a, "table_hit": b, "headline_hit": c,
                     "headline_n": d, "table_rows": e, "span": f}
                    for a, b, c, d, e, f in hit_bad],
                "quote_vs_table": [
                    {"round": a, "file": b, "table_hit": c, "table_rows": d,
                     "quote_hit": e, "quote_n": f, "span": g,
                     "grade": "confirmed" if (a, b, c, d, e, f, g) in q_conf
                              else "candidate"}
                    for a, b, c, d, e, f, g in q_bad],
            }, fh, indent=1, sort_keys=True)
        print("\nwrote %s" % args.json)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("rows"); p.add_argument("files", nargs="+"); p.set_defaults(fn=cmd_rows)
    p = sub.add_parser("aggregate"); p.add_argument("files", nargs="+"); p.set_defaults(fn=cmd_aggregate)
    p = sub.add_parser("bank"); p.add_argument("files", nargs="+")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(fn=cmd_bank)
    p = sub.add_parser("corpus"); p.add_argument("--json"); p.add_argument("--near", type=int, default=40,
        help="max line distance from the table for an aggregate to be its headline")
    p.set_defaults(fn=cmd_corpus)
    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
