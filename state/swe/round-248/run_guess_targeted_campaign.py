"""Guest-differential campaign SPECIFICALLY targeting Guess-carrying
programs (calls to guess/is_guess/confidence/sure), closing round 234's
own flagged-but-never-run backlog item: "run a decent-sized (1000+)
guest-fuzz campaign specifically targeting Guess-carrying programs before
trusting the probe to police this ongoing, now that the known gaps are
closed."

Unlike harness/swe/guest.py's own fuzz_guest() (which samples the FULL
BUILTIN_ARITY table uniformly, so Guess-family calls are sparse — 4 of 30
builtins), this script generates candidate programs the same way
(generate_guest_program) but FILTERS for ones whose source text actually
invokes one of the four Guess builtins, and only spends oracle time on
those, so "1000+" means 1000+ real Guess-carrying programs tested, not
1000+ programs of which only a fraction touch Guess.

Rewritten by round 251 after rounds 248/249/250 each launched this
campaign in the background, then ended their own turn "waiting for the
notification" — the one-shot-agent-no-background-wait trap named by
skills(B)'s own dedicated skill, which recurred THREE rounds running
despite the skill existing. Round 249 additionally restarted from seed 0,
discarding round 248's ~200 already-oracled programs, because the
original script had no checkpoint: it only wrote its JSON report once, at
the very end, after `accepted == TARGET`. On this host (contended: a
single accepted-Guess-program batch of 100 costs 400-1400s+ depending on
load), reaching TARGET=1000 synchronously within one round's real budget
is not reliable, so this version is checkpointed and resumable — an
interrupted or killed run leaves real, usable partial data and can be
CONTINUED (not restarted) by re-running the same command, the same
`.partial.jsonl` discipline `swe/campaign.py` already established for
mutation/live_kill/repair stages. Callers are expected to run this in the
FOREGROUND with a `--max-seconds` budget comfortably under the calling
tool's own timeout (see round 243/251's "block synchronously in the same
tool call" discipline) rather than backgrounding it and waiting on a
notification that a one-shot round will never receive.

Every accepted program also gets the why-shape probe (oracle_self_eval's
default why_probe=True) — WHY_VOCAB has contained every free-delegation op
token in the grammar's own reach since round 246 (matches/shapeof/typed),
so a mismatch here is a genuinely new finding, not a known, already-fixed
vocabulary gap.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, "/home/pgain/agi-research-nuc-llm")

from harness.swe.guest import generate_guest_program, GUEST_ORACLE
from harness.swe.killers import load_whence
from harness.swe.fuzz import WHENCE_ROOT, shrink
from harness.swe import oracles as O

GUESS_MARKERS = ("guess(", "is_guess(", "confidence(", "sure(")

DEFAULT_TARGET = 1000
TIMEOUT_S = 8.0
MAX_DEPTH = 2000
CHECKPOINT_EVERY = 20

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(OUT_DIR, "guess-targeted-state.json")
PARTIAL_PATH = os.path.join(OUT_DIR, "guess-targeted.partial.jsonl")
FINDINGS_PATH = os.path.join(OUT_DIR, "guess-targeted-findings.jsonl")
REPORT_PATH = os.path.join(OUT_DIR, "guess-targeted-campaign.json")


def has_guess_call(src):
    return any(m in src for m in GUESS_MARKERS)


def _dump_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _append_jsonl(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=DEFAULT_TARGET)
    ap.add_argument("--max-seconds", type=float, default=None,
                     help="stop and checkpoint gracefully after this many "
                          "wall-clock seconds even if --target is unmet")
    args = ap.parse_args()

    pkg = load_whence(WHENCE_ROOT, "guesstargeted")
    pkg["root"] = WHENCE_ROOT

    state = _load_json(STATE_PATH, default=None)
    if state is not None:
        seed = state["next_seed"]
        scanned = state["scanned"]
        accepted = state["accepted"]
        counts = state["counts"]
        marker_counts = state["marker_counts"]
        resumed = True
    else:
        seed = 0
        scanned = 0
        accepted = 0
        counts = {}
        marker_counts = {m: 0 for m in GUESS_MARKERS}
        resumed = False

    known_sigs = set(tuple(r["sig"]) for r in _read_jsonl(FINDINGS_PATH))

    t0 = time.time()
    print("resumed=%s starting seed=%d accepted=%d/%d scanned=%d" %
          (resumed, seed, accepted, args.target, scanned), file=sys.stderr)

    stop_reason = "target_reached"
    while accepted < args.target:
        if args.max_seconds is not None and time.time() - t0 > args.max_seconds:
            stop_reason = "max_seconds"
            break
        src = generate_guest_program(seed, stress_rate=0.7)
        scanned += 1
        seed += 1
        if not has_guess_call(src):
            continue
        accepted += 1
        for m in GUESS_MARKERS:
            if m in src:
                marker_counts[m] += 1
        o = O.run_oracle(GUEST_ORACLE, pkg, src, timeout_s=TIMEOUT_S,
                          max_depth=MAX_DEPTH, root=WHENCE_ROOT)
        counts[o.kind] = counts.get(o.kind, 0) + 1
        _append_jsonl(PARTIAL_PATH, {"seed": seed - 1, "kind": o.kind})
        if o.kind in ("crash", "mismatch"):
            sig = O.signature(o)
            if sig not in known_sigs:
                known_sigs.add(sig)

                def keep(cand, sig=sig):
                    return O.signature(O.run_oracle(
                        GUEST_ORACLE, pkg, cand, timeout_s=TIMEOUT_S,
                        max_depth=MAX_DEPTH, root=WHENCE_ROOT)) == sig

                minimized = shrink(src, keep)
                _append_jsonl(FINDINGS_PATH, {
                    "sig": list(sig), "seed": seed - 1, "src": src,
                    "detail": o.detail, "minimized": minimized,
                })

        if accepted % CHECKPOINT_EVERY == 0:
            _dump_json_atomic(STATE_PATH, {
                "next_seed": seed, "scanned": scanned, "accepted": accepted,
                "counts": counts, "marker_counts": marker_counts,
                "target": args.target, "elapsed_this_run_s": time.time() - t0,
            })
            print("accepted=%d scanned=%d elapsed_this_run=%.1fs" %
                  (accepted, scanned, time.time() - t0), file=sys.stderr)

    _dump_json_atomic(STATE_PATH, {
        "next_seed": seed, "scanned": scanned, "accepted": accepted,
        "counts": counts, "marker_counts": marker_counts,
        "target": args.target, "elapsed_this_run_s": time.time() - t0,
    })

    findings = {tuple(r["sig"]): r for r in _read_jsonl(FINDINGS_PATH)}
    report = {
        "target": args.target,
        "accepted": accepted,
        "scanned": scanned,
        "acceptance_rate": accepted / scanned if scanned else 0.0,
        "seconds_this_run": time.time() - t0,
        "stop_reason": stop_reason,
        "complete": accepted >= args.target,
        "counts": counts,
        "marker_counts": marker_counts,
        "findings": {"|".join(map(str, k)): v for k, v in findings.items()},
    }
    print(json.dumps(report, indent=2))
    _dump_json_atomic(REPORT_PATH, report)


if __name__ == "__main__":
    main()
