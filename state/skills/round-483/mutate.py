#!/usr/bin/env python3
"""Mutate seedsweep.py, run its suite, record which mutants survive.

Round 483 (skills B). The subject is edited IN PLACE and restored in a
`finally` -- round 482's next-step 1, written after round 481's loop left a
mutant applied when its outer timeout fired. The restore also runs on
KeyboardInterrupt and on SystemExit, which a bare try/except does not cover.
"""
import json
import os
import subprocess
import sys

# state/skills/round-<N>/mutate.py -> four levels up is the repo root. The
# first draft used three and died on the open() BEFORE mutating anything,
# which is the ordering this script is supposed to have.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
SUBJ = os.path.join(ROOT, "skills", "seed-sweep-needs-a-same-seed-control",
                    "scripts", "seedsweep.py")
TESTS = os.path.join(ROOT, "skills", "seed-sweep-needs-a-same-seed-control",
                     "scripts", "test_seedsweep.py")

MUTANTS = [
    ("M1-no-control",
     'kind, mask = mask_from_control(ctl_payloads)',
     'kind, mask = ("none", [])',
     "delete the same-seed arm: every volatile subject becomes a "
     "hash-order finding, which is exactly the state of the two live "
     "runners in this tree"),
    ("M2-mask-everything",
     '    return sorted(k for k in keys\n'
     '                  if any(f[k] != flats[0][k] for f in flats[1:]))',
     '    return sorted(keys)',
     "a scrub set too WIDE: masks every leaf, so a real cross-seed "
     "difference is swallowed and reported green"),
    ("M3-shape-change-is-maskable",
     '    if any(len(s) != n for s in splits[1:]):\n        return None',
     '    if any(len(s) != n for s in splits[1:]):\n        n = min(len(s) for s in splits)',
     "align a shape change instead of refusing it: `unscrubbable` "
     "disappears and the instrument invents an answer"),
    ("M4-witness-always-effective",
     'return {"effective": len(set(vals)) > 1, "n_distinct": len(set(vals)),',
     'return {"effective": True, "n_distinct": len(set(vals)),',
     "the perturbation check always passes: a dead arm reports a clean "
     "bill of health"),
    ("M5-power-off-by-one",
     'return float(n) ** (-(k - 1))',
     'return float(n) ** (-k)',
     "the classic off-by-one in the power formula, understating the "
     "miss probability by a factor of n"),
    ("M6-rc-not-in-payload",
     'payload = "#rc %d\\n%s" % (proc.returncode, proc.stdout)',
     'payload = "#rc 0\\n%s" % (proc.stdout,)',
     "drop the exit code from the compared payload: a deriver that "
     "answers 0 and 1 in different processes reports stable"),
    ("M7-first-run-only",
     'ctl = [run_once(subject, CONTROL_SEED, root, timeout, python)\n'
     '           for _ in range(control_runs)]',
     'ctl = [run_once(subject, CONTROL_SEED, root, timeout, python)] * control_runs',
     "run the control ONCE and duplicate the result: the control can "
     "never disagree with itself, so it always licenses the seed claim"),
    ("M8-expectation-not-an-error",
     '    if row["expect"] != "any":\n        return row["verdict"] != row["expect"]',
     '    if row["expect"] != "any":\n        return False',
     "a registry `expect` that disagrees with the measurement stops "
     "being an error: the registry becomes a to-do list again"),
]


def run_tests():
    p = subprocess.run([sys.executable, "-m", "pytest", TESTS, "-q",
                        "-x", "--no-header"], cwd=ROOT,
                       capture_output=True, text=True)
    return p.returncode, p.stdout.strip().splitlines()[-1:]


def main():
    original = open(SUBJ, encoding="utf-8").read()
    rc, line = run_tests()
    if rc != 0:
        print("BASELINE IS RED, refusing to mutate: %s" % line)
        return 2
    print("baseline green: %s" % (line[0] if line else ""))
    results = []
    try:
        for name, old, new, why in MUTANTS:
            if old not in original:
                results.append({"mutant": name, "applied": False,
                                "killed": None, "why": why,
                                "detail": "anchor not found"})
                print("%-28s ANCHOR-MISSING" % name)
                continue
            open(SUBJ, "w", encoding="utf-8").write(
                original.replace(old, new, 1))
            rc, line = run_tests()
            killed = rc != 0
            results.append({"mutant": name, "applied": True,
                            "killed": killed, "why": why,
                            "detail": (line[0] if line else "")})
            print("%-28s %s   %s"
                  % (name, "killed" if killed else "SURVIVED",
                     line[0] if line else ""))
    finally:
        open(SUBJ, "w", encoding="utf-8").write(original)
        rc, line = run_tests()
        print("restored; suite %s: %s"
              % ("green" if rc == 0 else "RED", line[0] if line else ""))
    n_app = sum(1 for r in results if r["applied"])
    n_kill = sum(1 for r in results if r["killed"])
    out = {"n_mutants": len(MUTANTS), "n_applied": n_app, "n_killed": n_kill,
           "n_survived": n_app - n_kill, "results": results}
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "mutants.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print("%d/%d applied mutants killed" % (n_kill, n_app))
    return 0 if n_kill == n_app else 1


if __name__ == "__main__":
    sys.exit(main())
