"""Round 161: deterministically recover round 137/149's repair verdicts.

No new LLM calls. Reconstructs each mutant from round-137's frozen
`orig-proj` snapshot (the WHENCE_ROOT as it stood before any repair attempt),
applies the already-recorded diff (round-137's own repair.json "diff" field,
or round-149's repair-recheck .diff files) onto the injected copy, and runs
score_repair with the CURRENT harness code — which now includes round 149's
own AGI_RESEARCH_ROOT fix (harness/swe/proc.py) that round 137's live run
predates. See knowledge/round-155-...md Sec 1 (the same env bug, discovered
via the mutation-recheck path) and this round's Sec 3.
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO, "harness"))

from swe.mutation import generate
from swe.repair import InjectedWorkspace, score_repair, _unparsed_original

ORIG_PROJ = os.path.join(REPO, "state/swe/round-137/orig-proj")
SNAPSHOT_SRC = os.path.join(REPO, "state/swe/round-137/snapshot/whence/interp.py")


def mutants_by_id():
    src = open(SNAPSHOT_SRC, encoding="utf-8").read()
    return {m.id: m for m in generate(src, "whence/interp.py")}


def diff_line_swap(diff_text):
    """Extract the single (removed, added) line-content pair from a tiny
    one-line unified diff. `patch -p1` cannot replay these diffs directly —
    `ws.diff()`'s CONTEXT lines were rendered by whatever Python's
    `ast.unparse` ran the live round (round 137/149 predate this NUC host's
    3.12); this interpreter's ast.unparse renders unrelated statements
    (tuple-unpacking assignment targets) with different but AST-equivalent
    parenthesization, so patch's context match fails even though the
    mutated line itself is unaffected and renders identically either way
    (confirmed: 4/5 of the real diffs replayed here touch only boolean/
    subscript expressions, never a bare tuple-assignment target). Returns
    None if the diff isn't exactly one add/remove pair (so the caller can
    fall back to "no change" rather than guess)."""
    removed = [l[1:] for l in diff_text.splitlines() if l.startswith("-") and not l.startswith("---")]
    added = [l[1:] for l in diff_text.splitlines() if l.startswith("+") and not l.startswith("+++")]
    if len(removed) != 1 or len(added) != 1:
        return None
    return removed[0], added[0]


def replay(mid, diff_text, label):
    """Reconstruct the injected workspace, apply the already-recorded live
    diff by literal single-line content swap (see diff_line_swap), and
    score with the CURRENT harness code (post round-149's AGI_RESEARCH_ROOT
    fix in harness/swe/proc.py, which round 137's live run predates)."""
    m = mutants_by_id()[mid]
    ws = InjectedWorkspace(ORIG_PROJ, m)
    try:
        swap = diff_line_swap(diff_text)
        if swap:
            removed, added = swap
            path = os.path.join(ws.dst, m.path)
            text = open(path, encoding="utf-8").read()
            if text.count(removed) != 1:
                raise RuntimeError("%s: removed line not unique/found (%d occurrences)" %
                                    (mid, text.count(removed)))
            with open(path, "w", encoding="utf-8") as f:
                f.write(text.replace(removed, added, 1))
        rec = score_repair(ws, run_tests=True, test_args="-q tests", test_timeout_s=900)
        rec["mutant"] = mid
        rec["source"] = label
        rec["diff_applied"] = bool(swap)
        return rec
    finally:
        ws.cleanup()


def main():
    out = {}

    # Round 137's own 6 attempts: replay from repair.json's saved diffs.
    r137 = json.load(open(os.path.join(REPO, "state/swe/round-137/repair.json")))
    for r in r137["results"]:
        mid = r["mutant"]
        rec = replay(mid, r["diff"], "round-137-original")
        out.setdefault(mid, {})["round-137-original"] = rec
        print("round-137", mid, "exact=%s(was %s) green=%s(was %s) outcome=%s(was %s)" %
              (rec["exact"], r["exact"], rec["green"], r["green"], rec["outcome"], r["outcome"]))

    # Round 149's re-attempts: replay from the .diff files left on disk
    # (mutants with no .diff file made no change — an empty diff).
    r149_dir = os.path.join(REPO, "state/swe/round-149/repair-recheck.json")
    seen = set()
    for fn in sorted(os.listdir(r149_dir)):
        if fn.endswith(".trace.jsonl"):
            mid_us = fn[len("repair-"):-len(".trace.jsonl")]
        else:
            continue
        # mid encoded with underscores in place of : and # — recover via the
        # known id list rather than guessing the escaping.
        seen.add(mid_us)

    id_by_us = {}
    src = open(SNAPSHOT_SRC, encoding="utf-8").read()
    import re
    for m in generate(src, "whence/interp.py"):
        us = re.sub(r"\W", "_", m.id)
        id_by_us[us] = m.id

    for us in sorted(seen):
        mid = id_by_us.get(us)
        if mid is None:
            print("SKIP (no id match):", us)
            continue
        diff_path = os.path.join(r149_dir, "repair-%s.diff" % us)
        diff_text = open(diff_path, encoding="utf-8").read() if os.path.exists(diff_path) else ""
        rec = replay(mid, diff_text, "round-149-recheck")
        out.setdefault(mid, {})["round-149-recheck"] = rec
        print("round-149", mid, "exact=%s green=%s outcome=%s" %
              (rec["exact"], rec["green"], rec["outcome"]))

    with open(os.path.join(REPO, "state/swe/round-161/repair-replay.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
