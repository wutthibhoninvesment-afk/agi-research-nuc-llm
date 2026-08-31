#!/usr/bin/env python3
"""Who takes whose cases: a displacement matrix over the probe archive.

Round 405. Every analysis this corpus has ever run is PER SKILL and per
case — recall, precision, a Wilson interval on `did MY skill fire`. That
frame can only ever say "skill X is weak", so every remedy it has
suggested has been "rewrite X's description", and rounds 393 and 381 both
recorded that rewriting one side of a pair made things worse.

A probe that misses is not silent. It names a winner. Pooling those
winners across the archive answers a different question:

    is a case lost because ITS skill is vague, or because some OTHER
    skill's description is wide enough to take it?

An IMPORTER is a skill that fires on cases belonging to others far more
often than it loses its own. Narrowing one importer can return cases to
several skills at once; rewriting each victim cannot, because they are
not competing with each other.

    python3 displacement.py                 # matrix + importer ranking
    python3 displacement.py --reports DIR   # default state/trigger-eval
    python3 displacement.py --only round-405  # substring filter on basenames
    python3 displacement.py claims          # named confusables vs measured takers
    python3 displacement.py check           # exit 1 if an importer is real

Only same-digest probes count (the description on disk is the one being
judged), errored probes are dropped, and NEGATIVE cases are included as
victims of nobody: a fire on an `expect: []` case is a false positive for
the firer and is counted in its `false` column, never as displacement.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trigger_eval as te  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def displacement(catalog, cases, reports):
    """Returns (matrix, stats).

    ``matrix[(victim, taker)] = n`` — probes where ``victim`` was expected,
    did NOT fire, and ``taker`` (a catalog skill, not a host skill) did.
    ``stats[name]`` = {lost, taken, false, own_probes, other_probes} where
      lost          own positive probes where the skill failed to fire
      taken         probes of OTHER skills' positive cases that it won
      false         fires on negative (`expect: []`) cases
      own_probes    own positive probes, non-errored
      abstained     of `lost`, the probes where NO catalog skill fired at
                    all — a loss with no taker, which no pair rewrite can
                    reach because there is no competitor in the room
      other_probes  probes of OTHER skills' positive cases — the
                    DENOMINATOR for `taken`, without which `net` is not
                    comparable across skills: in this corpus `own_probes`
                    ranges 3..88, so a raw difference ranks probe volume.
    """
    digests = {n: te.description_digest(d) for n, d, _ in catalog}
    names = set(digests)
    by_id = {c["id"]: c for c in cases}
    matrix, stats = {}, {n: dict(lost=0, taken=0, false=0, own_probes=0,
                                 other_probes=0, abstained=0) for n in names}
    for path, _, data in reports:
        have = data.get("descriptions") or {}
        # A skill only counts in this report if the report probed the
        # description that is on disk NOW; otherwise the row is about dead
        # text. Depends on the report alone, so it is computed once.
        fresh = {n for n in names if have.get(n) == digests[n]}
        for r in data["results"]:
            if r.get("error"):
                continue
            cid = r.get("id")
            if cid not in by_id:
                continue
            expect = set(r.get("expect") or by_id[cid]["expect"])
            fired = set(r.get("fired") or []) & names
            expect &= fresh
            fired &= fresh
            if not expect:                       # negative case
                for f in fired:
                    stats[f]["false"] += 1
                continue
            for n in fresh - expect:
                stats[n]["other_probes"] += 1
            for v in expect:
                stats[v]["own_probes"] += 1
                if v in fired:
                    continue
                stats[v]["lost"] += 1
                if not fired:
                    stats[v]["abstained"] += 1
                for t in fired - expect:
                    matrix[(v, t)] = matrix.get((v, t), 0) + 1
                    stats[t]["taken"] += 1
    return matrix, stats


#: Every `(other-skill-name)` a description mentions. Descriptions in this
#: corpus disambiguate with a parenthesised skill name -- "NOT for a value
#: the corpus cannot distinguish from a constant (would-a-constant-have-
#: passed)". That is the DURABLE home of the confusable claim; the same
#: claim in state/known-unprobed-skills.json is deleted the moment the
#: skill is probed, so a check that read the registry would evaporate on
#: the round that made it answerable.
def named_confusables(catalog):
    names = {n for n, _, _ in catalog}
    out = {}
    for n, desc, _ in catalog:
        hit = set()
        for cand in names:
            if cand == n:
                continue
            if "(%s)" % cand in (desc or "") or "(%s;" % cand in (desc or ""):
                hit.add(cand)
        out[n] = hit
    return out


def render_claims(catalog, matrix, stats):
    """Does a description's own NOT-clause name the skill that actually
    takes its cases? Round 405 measured: on this corpus, no."""
    named = named_confusables(catalog)
    print("%-34s %5s %5s %-30s %-30s %s"
          % ("skill", "lost", "abst", "top MEASURED taker", "NAMED in its description",
             "hit?"))
    hits = tested = 0
    for n, s in sorted(stats.items(), key=lambda kv: -kv[1]["lost"]):
        if not s["lost"] or not named[n]:
            continue
        takers = {t: c for (v, t), c in matrix.items() if v == n}
        if not takers:
            print("%-34s %5d %5d %-30s %-30s %s"
                  % (n, s["lost"], s["abstained"], "(nothing fired)",
                     ",".join(sorted(named[n]))[:30], "n/a"))
            continue
        top = max(takers.items(), key=lambda kv: kv[1])[0]
        tested += 1
        ok = top in named[n]
        hits += 1 if ok else 0
        print("%-34s %5d %5d %-30s %-30s %s"
              % (n, s["lost"], s["abstained"], top,
                 ",".join(sorted(named[n]))[:30], "YES" if ok else "no"))
    print("\n%d of %d skill(s) whose description names a confusable AND that "
          "lost at least one probe to some taker had that NAMED skill as its "
          "top measured taker." % (hits, tested))
    return hits, tested


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="report",
                    choices=("report", "claims", "check"))
    ap.add_argument("--reports", default=os.path.join(REPO, "state", "trigger-eval"))
    ap.add_argument("--skills", action="append",
                    default=[os.path.join(REPO, "skills")])
    ap.add_argument("--cases", default=os.path.join(REPO, "skills", "trigger-cases.json"))
    ap.add_argument("--only", help="substring filter on report basenames")
    ap.add_argument("--max-take-rate", type=float, default=0.05,
                    help="check mode: fail if a skill wins more than this "
                         "fraction of OTHER skills' probes (needs --min-other)")
    ap.add_argument("--min-other", type=int, default=40,
                    help="check mode: ignore skills with fewer than this many "
                         "other-skill probes -- a rate off 3 probes is noise")
    a = ap.parse_args(argv)

    catalog = te.load_catalog(a.skills)
    cases = te.load_cases(a.cases)
    reports = te.load_reports(a.reports)
    if a.only:
        reports = [r for r in reports if a.only in os.path.basename(r[0])]
    if not reports:
        print("no reports under %s%s" % (a.reports,
                                         " matching %r" % a.only if a.only else ""))
        return 2
    matrix, stats = displacement(catalog, cases, reports)

    def take_rate(s):
        return s["taken"] / float(s["other_probes"]) if s["other_probes"] else 0.0

    def loss_rate(s):
        return s["lost"] / float(s["own_probes"]) if s["own_probes"] else 0.0

    rows = sorted(((take_rate(s), n, s) for n, s in stats.items()
                   if s["taken"] or s["lost"] or s["false"]), reverse=True)
    print("%d report(s), %d skill(s) with any traffic\n" % (len(reports), len(rows)))
    print("take_rate = taken / probes of OTHER skills' cases (how often it "
          "reaches across)\nloss_rate = lost / its own probes\n")
    print("%-34s %9s %9s %5s %5s %5s %5s %6s %6s" %
          ("skill", "take_rate", "loss_rate", "take", "lost", "abst", "fals",
           "own_n", "oth_n"))
    for tr, n, s in rows:
        print("%-34s %9.4f %9.2f %5d %5d %5d %5d %6d %6d"
              % (n, tr, loss_rate(s), s["taken"], s["lost"], s["abstained"],
                 s["false"], s["own_probes"], s["other_probes"]))

    # Is a loss addressable by rewriting a PAIR? Only if it has one
    # consistent taker. Per victim: losses, how many abstained, and the
    # share of its DISPLACED losses that went to its single top taker.
    print("\nper victim: is there a pair to rewrite?")
    print("%-34s %5s %5s %6s  %s" % ("victim", "lost", "abst", "top%", "top taker"))
    tot_lost = tot_abst = 0
    concentrations = []
    for n, s in sorted(stats.items(), key=lambda kv: -kv[1]["lost"]):
        if not s["lost"]:
            continue
        takers = {t: c for (v, t), c in matrix.items() if v == n}
        disp = sum(takers.values())
        top, topn = (max(takers.items(), key=lambda kv: kv[1]) if takers
                     else ("-", 0))
        share = topn / float(s["lost"])
        tot_lost += s["lost"]
        tot_abst += s["abstained"]
        concentrations.append(share)
        print("%-34s %5d %5d %5.0f%%  %s"
              % (n, s["lost"], s["abstained"], 100 * share, top))
    if tot_lost:
        print("\n%d loss(es) total; %d (%.0f%%) had NO catalog skill fire at "
              "all; median top-taker share of a victim's losses %.0f%%"
              % (tot_lost, tot_abst, 100.0 * tot_abst / tot_lost,
                 100 * sorted(concentrations)[len(concentrations) // 2]))

    print("\ntop displacements (victim -> taker, n):")
    for (v, t), n in sorted(matrix.items(), key=lambda kv: -kv[1])[:25]:
        print("  %-32s -> %-32s %d" % (v, t, n))

    if a.mode == "claims":
        print()
        render_claims(catalog, matrix, stats)
        return 0
    if a.mode == "check":
        over = [(n, s) for tr, n, s in rows
                if s["other_probes"] >= a.min_other and tr > a.max_take_rate]
        for n, s in over:
            print("IMPORTER %s: won %d of %d probes of other skills' cases "
                  "(%.1f%%), lost %d of its own %d"
                  % (n, s["taken"], s["other_probes"],
                     100.0 * take_rate(s), s["lost"], s["own_probes"]))
        print("displacement: %d skill(s) over take_rate=%.3f (min_other=%d)"
              % (len(over), a.max_take_rate, a.min_other))
        return 1 if over else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
