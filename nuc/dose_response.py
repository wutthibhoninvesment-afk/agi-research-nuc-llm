#!/usr/bin/env python3
"""Round 472 — the observer effect as a DOSE-RESPONSE, not a coincidence.

Round 466 found that this program's own ssh logins are the strongest single
"explanation" of costly swap on the NUC over ten days: session scopes name
29 of 52 costly buckets against a circular-shift null of 6.70, and 13 of the
14 scope-named buckets the reachability log can test sit inside an E-round
window (Fisher p = 2.5e-4). It then said, in its own next-steps, exactly why
that is not yet a causal claim:

    "If the logins cost the memory, the cost should scale with what the round
    DID, not with the login count -- an E round that only probes should be
    cheap and one that scps a 1.0 MB journal + 1.3 MB sar + a tar should not."

That is a dose-response prediction and this module is the experiment. Three
things make it a real one rather than a re-run of round 466's coincidence
count:

  1. **The dose comes from a different file than the response.** The dose is
     read out of `logs/round-<N>.json`, the driver's own transcripts, which
     record every shell command a round issued with millisecond timestamps.
     The response is read out of `state/nuc-capture-r424/sar-all.txt`, taken
     off the box. Neither file knows about the other.
  2. **The window is FIXED-LENGTH.** A heavy round works longer, so its
     contact window is longer, so it covers more buckets -- window length is
     itself a dose and would manufacture the correlation. Every round is
     therefore scored over the same span anchored at its first contact.
  3. **There are negative controls.** A round's LOCAL work (shell calls that
     never touch the box, transcript bytes) cannot cost the NUC any memory. If
     it predicts the response as well as the NUC work does, the association is
     about when rounds run, not about what they do to the box.

Nothing here contacts the box. Every input is already on this host.
"""
from __future__ import annotations

import bisect
import json
import math
import random
import re
from pathlib import Path
from typing import Iterable

# `nuc/` has no `__init__.py`, and this module is used both ways: the tests
# import it as `from nuc import dose_response` from the repo root, and the CLI
# runs it as `python3 nuc/dose_response.py`, which puts `nuc/` itself on the
# path and makes `nuc.perturbation` unimportable. Both spellings, in the order
# that keeps a single installed copy authoritative.
try:                                                    # pragma: no cover
    from nuc.perturbation import (
        BucketMap, PerturbationError, parse_unit_starts_any_kind,
        shift_null_covered, Event, _iso_seconds,
    )
except ImportError:                                     # pragma: no cover
    from perturbation import (
        BucketMap, PerturbationError, parse_unit_starts_any_kind,
        shift_null_covered, Event, _iso_seconds,
    )

# The two documented ssh paths, plus the pre-round-154 LAN address the older
# transcripts still carry. `pgain-nuc` is deliberately NOT here: it is the
# tailnet NAME and appears in prose constantly, so it would match text that
# never opened a connection.
NUC_TARGETS = ("100.78.44.111", "192.168.1.37", "192.168.1.42")

# One of these tokens plus a target is a login. `sftp` has never been used in
# this program; it is here so that starting to use it does not silently drop
# out of the dose.
TRANSFER_VERBS = ("ssh", "scp", "rsync", "sftp")
_VERB_RE = re.compile(r"(?<![\w./-])(%s)(?![\w./-])" % "|".join(TRANSFER_VERBS))

_HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_ASSIGN_RE = re.compile(r"(?:^|[\s;&|(])([A-Za-z_][A-Za-z0-9_]*)=(\S+)")

# The fixed scoring window. 3600 s, anchored 300 s before first contact, is
# round 466's own [-300, +3300] observer window -- reused on purpose so that
# this round's windows and round 466's confounding table are the same object.
WINDOW_BEFORE_S = 300
WINDOW_AFTER_S = 3300

PERM_TRIALS = 20000
SHIFT_TRIALS = 2000


# --------------------------------------------------------------- the dose

def strip_heredocs(cmd: str) -> str:
    """The command with every heredoc BODY removed, opener lines kept.

    Without this the dose is nonsense. Round 424's transcript contains
    `cat > nuc/predictions-e-round424.md <<'EOF'` whose body quotes an ssh
    command line for the tailnet address -- a substring test scores that as a
    login to the box, and it is a local file write. The opener line is kept
    because a real invocation looks like
    `ssh ... jab@100.78.44.111 'bash -s' <<'REMOTE'`, which opens a heredoc on
    the very line that makes the connection.
    """
    out, lines, i = [], cmd.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        tags = [m.group(2) for m in _HEREDOC_RE.finditer(line)]
        i += 1
        for tag in tags:
            while i < len(lines) and lines[i].strip() != tag:
                i += 1
            i += 1 if i < len(lines) else 0
    return "\n".join(out)


def nuc_variables(text: str) -> set:
    """Shell variables assigned a NUC target in this same command.

    Round 424's capture step is `NUC=jab@100.78.44.111; ...; scp ... $NUC:...`
    -- the verb and the address never share a line. Resolving one level of
    assignment is enough for every command in this corpus and is reported, so
    a future two-level indirection shows up as a miss rather than as a zero.
    """
    return {m.group(1) for m in _ASSIGN_RE.finditer(text)
            if any(t in m.group(2) for t in NUC_TARGETS)}


# A redirect target, or an scp/rsync local destination. Deliberately NOT
# `2>&1`, `>&2`, or a process substitution: those are not files that landed.
_REDIR_RE = re.compile(r"""(?<![0-9&])>>?\s*(?![&(])(['"]?)([^\s;&|<>'"]+)\1""")
_VAR_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")


def shell_vars(text: str) -> dict:
    """Every simple `NAME=value` in one command, last write wins.

    One level, no arithmetic, no command substitution. That is enough for
    every capture command in this corpus and the shortfall is REPORTED
    (`n_paths_unresolved`) rather than absorbed, so a two-level indirection
    arrives as a visible miss.
    """
    return {m.group(1): m.group(2) for m in _ASSIGN_RE.finditer(text)}


def expand_vars(word: str, variables: dict) -> str:
    return _VAR_RE.sub(lambda m: variables.get(m.group(1), m.group(0)), word)


def landed_paths(cmd: str) -> list:
    """Local files this command wrote FROM the box.

    THE REASON THIS EXISTS. `bytes_returned` is the `tool_result` text, and
    round 424's capture is `ssh ... 'cat /work/...' > state/nuc-capture-r424/
    journal-pid1-full.txt`. Three megabytes crossed the wire and 489 bytes
    reached the transcript. Scoring that round on stdout alone would have made
    the single heaviest round in the corpus look like one of the lightest --
    the exact direction that manufactures a null. It is also not an scp
    problem: round 424 used no scp at all.

    Only paths from commands that CONTACTED the box are counted; the caller
    enforces that, so a purely local `cat > file` never lands here.
    """
    text = strip_heredocs(cmd)
    variables = shell_vars(text)
    out = []
    for m in _REDIR_RE.finditer(text):
        out.append(expand_vars(m.group(2), variables))
    for line in text.splitlines():
        if not re.search(r"(?<![\w./-])(scp|rsync)(?![\w./-])", line):
            continue
        toks = [t for t in line.split() if not t.startswith("-")]
        if len(toks) >= 3 and ":" not in toks[-1]:
            out.append(expand_vars(toks[-1], variables))
    return [x for x in out if x and not x.startswith("/dev/")]


def landed_bytes(cmd: str, root: str = ".") -> dict:
    """`landed_paths` resolved against the tree as it stands TODAY.

    A path that no longer exists is `unresolved`, never zero. The capture dirs
    this reads are checked in, so for the rounds that matter the resolution is
    exact; for the rest the shortfall is a number in the report.
    """
    base = Path(root)
    total, resolved, missing = 0, [], []
    for rel in landed_paths(cmd):
        f = base / rel
        if f.is_dir():
            n = sum(x.stat().st_size for x in f.rglob("*") if x.is_file())
            total += n
            resolved.append({"path": rel, "bytes": n, "kind": "dir"})
        elif f.is_file():
            n = f.stat().st_size
            total += n
            resolved.append({"path": rel, "bytes": n, "kind": "file"})
        else:
            missing.append(rel)
    return {"bytes": total, "resolved": resolved, "unresolved": missing}


def command_contact(cmd: str) -> dict:
    """Did this shell command open connections to the NUC, and how many?

    Returns `{"n_logins": 0, ...}` for a command that did not. `n_logins`
    counts transfer VERBS in the surviving text, because one Bash call may
    open several sessions (round 424's capture ran three `scp`s in one call)
    and the journal records one session scope per session, not per call.
    """
    text = strip_heredocs(cmd)
    variables = nuc_variables(text)
    literal = [t for t in NUC_TARGETS if t in text]
    var_refs = [v for v in variables
                if ("$" + v) in text or ("${" + v + "}") in text]
    verbs = [m.group(1) for m in _VERB_RE.finditer(text)]
    # `literal` ALONE, and `var_refs` deliberately does not join it. Round
    # 472's mutation pass proved that disjunct dead: a variable can only be
    # resolved to a NUC target by an assignment in this same command text, and
    # that assignment puts the literal address in the text too, so `var_refs`
    # never decides anything `literal` had not already decided. It is kept as
    # a REPORTED field because `landed_paths` genuinely needs the expansion --
    # round 424 writes to `$OUT/...` -- and because a command that reached the
    # box through a variable inherited from the ENVIRONMENT would be invisible
    # to this classifier, which is a limitation worth being able to see.
    addressed = bool(literal)
    return {
        "n_logins": len(verbs) if addressed else 0,
        "verbs": verbs if addressed else [],
        "targets": literal,
        "via_variable": sorted(var_refs),
        "addressed": addressed,
        "had_verb": bool(verbs),
        # An addressed command with no verb is a mention, not a contact; a
        # verb with no address is an ssh to some other host. Both are reported
        # so the classifier's two failure modes are visible rather than
        # collapsed into the same zero.
        "why_zero": (None if addressed and verbs else
                     "addressed but no transfer verb" if addressed else
                     "transfer verb but no NUC address" if verbs else
                     "neither"),
    }


def _blocks(rec: dict):
    msg = rec.get("message") or {}
    content = msg.get("content")
    return content if isinstance(content, list) else []


def _result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, list):
        return "".join(x.get("text", "") for x in content
                       if isinstance(x, dict))
    return "" if content is None else str(content)


def _to_z(ts):
    if not ts:
        return None
    s = str(ts).replace("Z", "+00:00")
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(s).astimezone(timezone.utc)
    except ValueError:
        return None
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch_ms(ts):
    if not ts:
        return None
    s = str(ts).replace("Z", "+00:00")
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(s).astimezone(timezone.utc)
    except ValueError:
        return None
    return dt.timestamp()


def transcript_dose(text: str, round_: int = None,
                    root: str = ".") -> dict:
    """One round's dose, from its own transcript. Pure: text in, dict out.

    Four doses, and two of them are negative controls:

      `n_calls`, `n_logins`   -- how many times the box was contacted
      `box_seconds`           -- wall time the box spent answering
      `bytes_returned`        -- payload pulled back through stdout
      `local_calls`, `local_bytes` -- the SAME quantities for shell commands
                                 that never touched the box (the controls)

    `bytes_returned` is stdout only. An `scp` writes to a file, so its payload
    is invisible here; `n_scp` is reported separately and the round file says
    so out loud rather than letting a 3.2 MB transfer be scored as 700 bytes.
    """
    pending, nuc, local = {}, [], []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = rec.get("timestamp")
        for b in _blocks(rec):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                pending[b.get("id")] = ((b.get("input") or {}).get("command")
                                        or "", ts, b.get("name"))
            elif b.get("type") == "tool_result":
                got = pending.pop(b.get("tool_use_id"), None)
                if got is None:
                    continue
                cmd, use_ts, tool = got
                if tool not in (None, "Bash"):
                    continue
                out = _result_text(b)
                dur = None
                a, z = _epoch_ms(use_ts), _epoch_ms(ts)
                if a is not None and z is not None:
                    dur = max(0.0, z - a)
                hit = command_contact(cmd)
                land = (landed_bytes(cmd, root) if hit["n_logins"]
                        else {"bytes": 0, "resolved": [], "unresolved": []})
                row = {"issued_utc": _to_z(use_ts), "returned_utc": _to_z(ts),
                       "duration_s": dur, "bytes": len(out),
                       "landed_bytes": land["bytes"],
                       "landed_paths": [x["path"] for x in land["resolved"]],
                       "unresolved_paths": land["unresolved"],
                       "n_logins": hit["n_logins"], "verbs": hit["verbs"],
                       "head": cmd.strip().splitlines()[0][:160] if cmd.strip()
                               else ""}
                (nuc if hit["n_logins"] else local).append(row)

    def _sum(rows, key):
        return sum(r[key] or 0 for r in rows)

    stamps = [r["issued_utc"] for r in nuc if r["issued_utc"]]
    return {
        "round": round_,
        "n_calls": len(nuc),
        "n_logins": _sum(nuc, "n_logins"),
        "n_scp": sum(1 for r in nuc for v in r["verbs"] if v == "scp"),
        "box_seconds": round(_sum(nuc, "duration_s"), 3),
        "bytes_returned": _sum(nuc, "bytes"),
        "bytes_landed": _sum(nuc, "landed_bytes"),
        "bytes_moved": _sum(nuc, "bytes") + _sum(nuc, "landed_bytes"),
        "n_paths_unresolved": sum(len(r["unresolved_paths"]) for r in nuc),
        "local_calls": len(local),
        "local_bytes": _sum(local, "bytes"),
        "first_contact_utc": min(stamps) if stamps else None,
        "last_contact_utc": (max(r["returned_utc"] for r in nuc
                                 if r["returned_utc"]) if stamps else None),
        "calls": nuc,
    }


def round_doses(rounds: Iterable, transcript_dir: str = "logs",
                root: str = ".") -> list:
    """`transcript_dose` over many rounds; rounds with no transcript are
    reported with `missing: true` rather than dropped."""
    out = []
    for n in rounds:
        p = Path(transcript_dir) / ("round-%d.json" % n)
        if not p.exists():
            out.append({"round": n, "missing": True, "n_calls": 0,
                        "n_logins": 0, "first_contact_utc": None})
            continue
        d = transcript_dose(p.read_text(errors="replace"), n, root)
        d["missing"] = False
        d["transcript_bytes"] = p.stat().st_size
        out.append(d)
    return out


# ----------------------------------------------------------- the response

def score_windows(doses: Iterable, bmap: BucketMap,
                  before_s: int = WINDOW_BEFORE_S,
                  after_s: int = WINDOW_AFTER_S,
                  interval_s: int = 600) -> dict:
    """Attach each round's fixed-length window response to its dose.

    A round whose first contact is on a date the pooled sar window does not
    cover is UNTESTABLE, and is returned in its own list. Scoring it as a zero
    response would invent an observation from a file that does not reach that
    day -- round 466's mistake-not-made, kept.
    """
    scored, untestable = [], []
    for d in doses:
        at = d.get("first_contact_utc")
        if d.get("missing") or not at or not d.get("n_logins"):
            untestable.append({"round": d.get("round"),
                               "why": ("no transcript" if d.get("missing")
                                       else "no NUC contact in the transcript"),
                               **{k: d.get(k) for k in ("n_calls", "n_logins")}})
            continue
        a = bmap.abs_second(at)
        if a is None:
            untestable.append({"round": d.get("round"),
                               "why": "first contact %s is outside the pooled "
                                      "sar window %s..%s"
                                      % (at, bmap.days[0], bmap.days[-1]),
                               "n_logins": d.get("n_logins")})
            continue
        lo, hi = a - before_s, a + after_s
        if lo < 0 or hi >= bmap.span_s:
            untestable.append({"round": d.get("round"),
                               "why": "window runs off the end of the pooled "
                                      "span (edge round)",
                               "n_logins": d.get("n_logins")})
            continue
        buckets = bmap.span_buckets(lo, hi)
        # THE CONFOUND THIS ROUND ALMOST PUBLISHED. A window on a stretch the
        # sar record does not cover has zero buckets and therefore a zero
        # response BY CONSTRUCTION -- and every such window belongs to a round
        # that found the box DOWN, which is also a round that made two or
        # three probe calls instead of fifteen. Pooled, that pairs "few calls"
        # with "zero swap" for a reason that has nothing to do with cost, and
        # manufactures a dose-response out of the box's power state. A window
        # is only comparable when the record covers all of it.
        expected = (before_s + after_s) // interval_s + 1
        scored.append({
            "round": d["round"],
            "first_contact_utc": at,
            "window_utc": [_abs_to_iso(bmap, lo), _abs_to_iso(bmap, hi)],
            "abs_lo": lo, "abs_hi": hi,
            "n_calls": d["n_calls"], "n_logins": d["n_logins"],
            "n_scp": d["n_scp"], "box_seconds": d["box_seconds"],
            "bytes_returned": d["bytes_returned"],
            "bytes_landed": d["bytes_landed"],
            "bytes_moved": d["bytes_moved"],
            "local_calls": d["local_calls"], "local_bytes": d["local_bytes"],
            "transcript_bytes": d.get("transcript_bytes"),
            "n_buckets": len(buckets),
            "n_buckets_expected": expected,
            "fully_covered": len(buckets) >= expected,
            "record_coverage": ("full" if len(buckets) >= expected
                                else "partial" if buckets else "none"),
            "n_costly_buckets": len(buckets & bmap.costly),
            "swap_bytes": sum(bmap.all_bucket_bytes[k] for k in buckets),
        })
    scored.sort(key=lambda r: r["abs_lo"])
    return {"scored": scored, "untestable": untestable,
            "n_full": sum(1 for r in scored if r["record_coverage"] == "full"),
            "n_partial": sum(1 for r in scored
                             if r["record_coverage"] == "partial"),
            "n_no_record": sum(1 for r in scored
                               if r["record_coverage"] == "none"),
            "window_s": before_s + after_s + 1,
            "pooled_days": list(bmap.days),
            "min_bytes": bmap.min_bytes}


def _abs_to_iso(bmap: BucketMap, s: int) -> str:
    d, sod = divmod(s % bmap.span_s, 86400)
    return "%sT%02d:%02d:%02dZ" % (bmap.days[d], sod // 3600,
                                   sod % 3600 // 60, sod % 60)


# ------------------------------------------------------------ statistics

def _ranks(xs) -> list:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = r
        i = j + 1
    return out


def spearman(xs, ys) -> float:
    """Pearson on mid-ranks. Returns 0.0 when either side is constant --
    a dose that never varies cannot predict anything and that is not an
    error."""
    if len(xs) != len(ys):
        raise PerturbationError("spearman: length mismatch")
    if len(xs) < 3:
        raise PerturbationError("spearman: need at least 3 pairs")
    rx, ry = _ranks(list(xs)), _ranks(list(ys))
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def permutation_test(xs, ys, trials: int = PERM_TRIALS,
                     seed: int = 20260903) -> dict:
    """Is this rho more than the pairing buys?

    The null shuffles which dose belongs to which window. It holds BOTH
    marginal distributions exactly fixed -- the same skewed doses, the same
    heavy-tailed responses, the same n -- and destroys only the pairing, which
    is the thing the hypothesis is about. No normality is assumed anywhere,
    which matters here because a single 2.34 GiB bucket dominates the response.
    """
    if trials <= 0:
        raise PerturbationError("trials must be > 0")
    obs = spearman(xs, ys)
    rng = random.Random(seed)
    ys = list(ys)
    ge = 0
    for _ in range(trials):
        rng.shuffle(ys)
        if abs(spearman(xs, ys)) >= abs(obs) - 1e-12:
            ge += 1
    return {"rho": round(obs, 4), "n": len(xs), "trials": trials,
            "n_ge_observed": ge, "p_two_sided": ge / trials,
            "p_floor": 1.0 / trials,
            "null": "shuffle which dose belongs to which window; both "
                    "marginals held exactly fixed"}


def window_shift_null(bmap: BucketMap, scored: Iterable,
                      trials: int = SHIFT_TRIALS,
                      seed: int = 20260903,
                      whole_day: bool = False,
                      restrict_to_round_days: bool = False) -> dict:
    """Are the round windows, as a SET, more expensive than their shape buys?

    The companion question to the dose-response, and a different one: this
    asks whether E rounds happen at expensive moments at all, before asking
    whether expensive rounds are the expensive ones. Same circular-shift null
    as round 466 -- the whole train of windows is translated rigidly, so
    count, length and spacing survive and only alignment dies.
    """
    rows = list(scored)
    if not rows:
        raise PerturbationError("no scored windows")
    spans = [(r["abs_lo"], r["abs_hi"]) for r in rows]

    # THE SUPPORT PROBLEM. A shift over the whole pooled span moves the round
    # train onto 2026-08-23 and -24, and no E round can occur there: the
    # driver log's first line is round 152 on 08-26. Those two days carry the
    # record's largest bucket (2.34 GiB), so a null free to land on them is
    # compared against an observation that never could -- which inflates the
    # null's BYTES and makes the observed total look small for a reason that
    # is calendar, not cost. Restricting the shift group to the days the
    # windows actually occupy removes that.
    day_lo = min(lo for lo, _ in spans) // 86400
    day_hi = max(hi for _, hi in spans) // 86400
    if restrict_to_round_days:
        base, span = day_lo * 86400, (day_hi - day_lo + 1) * 86400
    else:
        base, span = 0, bmap.span_s

    def total(shift):
        hit = set()
        for lo, hi in spans:
            slo = base + (lo - base + shift) % span
            hit |= bmap.span_buckets(slo, slo + (hi - lo))
        return (sum(bmap.all_bucket_bytes[k] for k in hit),
                len(hit & bmap.costly))

    obs_bytes, obs_costly = total(0)
    rng = random.Random(seed)
    if whole_day:
        offsets = [86400 * k for k in range(1, span // 86400)]
    else:
        offsets = [rng.randrange(span) for _ in range(trials)]
    b_draws, c_draws = [], []
    for off in offsets:
        b, c = total(off)
        b_draws.append(b)
        c_draws.append(c)
    b_draws.sort()
    c_draws.sort()
    n = len(offsets)
    return {
        "n_windows": len(rows),
        "whole_day_shifts": whole_day,
        "restricted_to_round_days": restrict_to_round_days,
        "shift_group_days": [bmap.days[day_lo], bmap.days[day_hi]]
                            if restrict_to_round_days
                            else [bmap.days[0], bmap.days[-1]],
        "trials": n,
        "observed_bytes": obs_bytes,
        "null_mean_bytes": round(sum(b_draws) / n, 1),
        "null_median_bytes": b_draws[n // 2],
        "null_p95_bytes": b_draws[min(n - 1, int(0.95 * n))],
        "p_bytes": sum(1 for x in b_draws if x >= obs_bytes) / n,
        "observed_costly_buckets": obs_costly,
        "null_mean_costly": round(sum(c_draws) / n, 3),
        "null_median_costly": c_draws[n // 2],
        "null_p95_costly": c_draws[min(n - 1, int(0.95 * n))],
        "p_costly": sum(1 for x in c_draws if x >= obs_costly) / n,
        "p_floor": 1.0 / n,
    }


def covered_rate_null(bmap: BucketMap, scored: Iterable,
                      trials: int = SHIFT_TRIALS, seed: int = 20260903,
                      interval_s: int = 600,
                      restrict_to_round_days: bool = True) -> dict:
    """The shift null with the record's own gaps taken out of it.

    THE MIRROR OF THE SUPPORT PROBLEM, and the reason the two nulls above are
    not enough. Restricting the shift group to the days E rounds occupy stops
    the null reaching 2026-08-23/24 -- but inside those days the box was DOWN
    for hours (rounds 184/190/196, and the whole 298-346 outage), and a window
    shifted onto downtime has NO buckets and therefore hits no costly one. A
    null free to land on the record's holes is being asked "are your windows
    on live stretches?", to which the answer is trivially yes, and it returns
    that as an effect.

    So the statistic is a RATE over COVERED windows only: of the windows a
    draw places on fully-recorded ground, what fraction contain at least one
    costly bucket? Observed and null are then the same quantity, and the
    record's holes cancel instead of counting.

    A draw that covers nothing is not scored; `n_draws_scored` says how many
    survived, because a rate over two windows is not the same evidence as a
    rate over twenty-eight.
    """
    rows = list(scored)
    if not rows:
        raise PerturbationError("no scored windows")
    spans = [(r["abs_lo"], r["abs_hi"]) for r in rows]
    expected = (spans[0][1] - spans[0][0]) // interval_s + 1
    day_lo = min(lo for lo, _ in spans) // 86400
    day_hi = max(hi for _, hi in spans) // 86400
    if restrict_to_round_days:
        base, span = day_lo * 86400, (day_hi - day_lo + 1) * 86400
    else:
        base, span = 0, bmap.span_s

    def rate(shift):
        cov = hot = 0
        for lo, hi in spans:
            slo = base + (lo - base + shift) % span
            b = bmap.span_buckets(slo, slo + (hi - lo))
            if len(b) < expected:
                continue
            cov += 1
            if b & bmap.costly:
                hot += 1
        return cov, hot

    obs_cov, obs_hot = rate(0)
    if obs_cov != len(rows):
        raise PerturbationError(
            "the observed windows are not all fully covered (%d of %d); pass "
            "the full-record stratum" % (obs_cov, len(rows)))
    obs = obs_hot / obs_cov
    rng = random.Random(seed)
    draws, ge, skipped = [], 0, 0
    for _ in range(trials):
        cov, hot = rate(rng.randrange(span))
        if cov == 0:
            skipped += 1
            continue
        r = hot / cov
        draws.append(r)
        if r >= obs - 1e-12:
            ge += 1
    if not draws:
        raise PerturbationError("no draw placed a single window on covered "
                                "ground; the record has too few holes-free "
                                "stretches for this null")
    draws.sort()
    n = len(draws)
    return {
        "n_windows": len(rows),
        "expected_buckets_per_window": expected,
        "shift_group_days": [bmap.days[day_lo], bmap.days[day_hi]]
                            if restrict_to_round_days
                            else [bmap.days[0], bmap.days[-1]],
        "observed_windows_with_a_costly_bucket": obs_hot,
        "observed_rate": round(obs, 4),
        "trials": trials,
        "n_draws_scored": n,
        "n_draws_skipped_no_coverage": skipped,
        "mean_covered_windows_per_draw": None,
        "null_mean_rate": round(sum(draws) / n, 4),
        "null_median_rate": draws[n // 2],
        "null_p95_rate": draws[min(n - 1, int(0.95 * n))],
        "n_draws_ge_observed": ge,
        "p_value": ge / n,
        "p_floor": 1.0 / n,
        "null": "circular shift of the whole window train within the days E "
                "rounds occupy, scored as a rate over the windows each draw "
                "places on fully-recorded ground",
    }


DOSES = ("n_logins", "n_calls", "box_seconds", "bytes_returned",
         "bytes_landed", "bytes_moved")
CONTROLS = ("local_calls", "local_bytes", "transcript_bytes")


def dose_response(scored: Iterable, trials: int = PERM_TRIALS,
                  seed: int = 20260903,
                  response: str = "swap_bytes") -> dict:
    """Every dose and every control against the response, one table.

    The controls are in the SAME table on purpose. A dose-response result that
    is only reported for the doses cannot be read: `bytes_returned` at
    rho = 0.4 means one thing if `local_bytes` is at 0.0 and the opposite if
    it is at 0.45.
    """
    rows = [r for r in scored if r.get(response) is not None]
    if len(rows) < 3:
        raise PerturbationError("need at least 3 scored windows, have %d"
                                % len(rows))
    ys = [r[response] for r in rows]
    out = {}
    for name in DOSES + CONTROLS:
        xs = [r.get(name) or 0 for r in rows]
        res = permutation_test(xs, ys, trials, seed)
        res["is_control"] = name in CONTROLS
        res["dose_min"], res["dose_max"] = min(xs), max(xs)
        out[name] = res
    best = max((k for k in DOSES), key=lambda k: abs(out[k]["rho"]))
    best_ctl = max((k for k in CONTROLS), key=lambda k: abs(out[k]["rho"]))
    return {
        "response": response,
        "n": len(rows),
        "response_total": sum(ys),
        "response_median": sorted(ys)[len(ys) // 2],
        "table": out,
        "strongest_dose": best,
        "strongest_control": best_ctl,
        "dose_beats_every_control": abs(out[best]["rho"]) >
                                    abs(out[best_ctl]["rho"]),
        "verdict": _verdict(out, best, best_ctl),
    }


def _verdict(table: dict, best: str, best_ctl: str) -> str:
    d, c = table[best], table[best_ctl]
    if d["p_two_sided"] > 0.05:
        return ("NULL: no dose reaches p<=0.05. The cost of an E-round window "
                "does not scale with what the round did to the box, so round "
                "466's coincidence is not shown to be causal by this test.")
    if abs(c["rho"]) >= abs(d["rho"]) or c["p_two_sided"] <= 0.05:
        return ("CONFOUNDED: the strongest dose (%s) is matched or beaten by a "
                "control (%s) that cannot touch the box. Whatever this "
                "measures is about when rounds run, not what they do."
                % (best, best_ctl))
    return ("DOSE-RESPONSE: %s predicts window cost (rho %.3f, p %.4f) and "
            "every control fails to. Consistent with the logins costing the "
            "memory." % (best, d["rho"], d["p_two_sided"]))


# ------------------------------------- the dose's own cross-check: scopes

def dose_vs_scopes(scored: Iterable, journal_text: str,
                   slack_s: int = 0) -> dict:
    """Does the transcript's login count match the journal's session count?

    Two files, two hosts, two programs. The transcript says how many times
    this program opened a connection; the journal says how many session scopes
    systemd created. If they agree per window the login dose is validated as a
    measurement rather than a guess -- and if they do not, the disagreement is
    the finding, because one of the two files is then wrong about what
    happened.
    """
    scopes = parse_unit_starts_any_kind(journal_text, ("scope",))
    secs = sorted(_iso_seconds(e.at_utc) for e in scopes
                  if e.at_utc.endswith("Z"))
    rows = []
    for r in scored:
        lo = _iso_seconds(r["window_utc"][0]) - slack_s
        hi = _iso_seconds(r["window_utc"][1]) + slack_s
        n = sum(1 for s in secs if lo <= s <= hi)
        rows.append({"round": r["round"], "n_logins_transcript": r["n_logins"],
                     "n_session_scopes_journal": n,
                     "delta": n - r["n_logins"]})
    exact = sum(1 for x in rows if x["delta"] == 0)
    within2 = sum(1 for x in rows if abs(x["delta"]) <= 2)
    tot_t = sum(x["n_logins_transcript"] for x in rows)
    tot_j = sum(x["n_session_scopes_journal"] for x in rows)
    return {
        "n_windows": len(rows),
        "n_exact": exact, "n_within_2": within2,
        "frac_within_2": (within2 / len(rows) if rows else None),
        "total_logins_transcript": tot_t,
        "total_scopes_journal": tot_j,
        "ratio_journal_over_transcript": (tot_j / tot_t if tot_t else None),
        "rho": (spearman([x["n_logins_transcript"] for x in rows],
                         [x["n_session_scopes_journal"] for x in rows])
                if len(rows) >= 3 else None),
        "rows": rows,
        "why": ("the transcript and the journal are independent records of "
                "the same logins; agreement validates the dose, disagreement "
                "IS the finding"),
    }


def scope_provenance(journal_text: str, doses: Iterable,
                     match_s: int = 120) -> dict:
    """Of ALL session scopes in the journal, how many are this program's?

    Round 466 matched the other direction -- 33 of 35 reachability-log probes
    had a scope within 120 s -- which cannot say what FRACTION of the box's
    logins are ours, because the log holds one row per round and a round makes
    many. The transcripts hold every call, so this direction is answerable.

    Scopes on dates before the transcript corpus begins are UNTESTABLE, not
    unmatched: absence of a transcript for 2026-08-23 is the driver log not
    existing yet.
    """
    scopes = [e.at_utc for e in parse_unit_starts_any_kind(journal_text,
                                                           ("scope",))]
    calls = sorted(_iso_seconds(c["issued_utc"])
                   for d in doses if not d.get("missing")
                   for c in d.get("calls", []) if c.get("issued_utc"))
    if not calls:
        raise PerturbationError("no NUC calls in any transcript")
    first_date = min(d["first_contact_utc"][:10] for d in doses
                     if d.get("first_contact_utc"))
    matched, unmatched, untestable = 0, [], 0
    for at in scopes:
        if at[:10] < first_date:
            untestable += 1
            continue
        t = _iso_seconds(at)
        near = min(calls, key=lambda c: abs(c - t))
        if abs(near - t) <= match_s:
            matched += 1
        else:
            unmatched.append({"at_utc": at, "nearest_call_delta_s": near - t})
    testable = matched + len(unmatched)
    return {
        "n_scopes": len(scopes),
        "first_transcript_date": first_date,
        "n_untestable_before_transcripts": untestable,
        "n_testable": testable,
        "n_matched": matched,
        "frac_matched": (matched / testable if testable else None),
        "match_s": match_s,
        "n_calls": len(calls),
        "unmatched_sample": unmatched[:20],
        "why": ("this is the fraction of the box's logins that are this "
                "program -- the number round 466 could not compute because "
                "the reachability log holds one row per round"),
    }


def split_scopes_by_provenance(journal_text: str, doses: Iterable,
                               match_s: int = 120) -> dict:
    """Session scopes split into THIS PROGRAM's logins and everybody else's.

    Round 466 concluded "the scopes are this program's own footprints" from a
    PROBE-side rate: 33 of 35 reachability-log probes had a scope within 120 s.
    That direction cannot bound the fraction of the box's logins that are ours,
    because the log holds one row per round and a round makes many logins. The
    transcripts hold every call, so the scope-side rate is answerable -- and it
    is the rate the sentence "the scopes are ours" is actually about.
    """
    scopes = parse_unit_starts_any_kind(journal_text, ("scope",))
    calls = sorted(_iso_seconds(c["issued_utc"])
                   for d in doses if not d.get("missing")
                   for c in d.get("calls", []) if c.get("issued_utc"))
    if not calls:
        raise PerturbationError("no NUC calls in any transcript")
    first = min(d["first_contact_utc"][:10] for d in doses
                if d.get("first_contact_utc"))
    ours, theirs, before = [], [], []
    for e in scopes:
        if e.at_utc[:10] < first:
            before.append(e)
            continue
        t = _iso_seconds(e.at_utc)
        near = min(calls, key=lambda c: abs(c - t))
        (ours if abs(near - t) <= match_s else theirs).append(e)
    # What fraction of the testable span is within match_s of SOME call? That
    # is the rate a scope unrelated to this program would match at by chance,
    # and without it "41 % matched" cannot be read either way.
    lo, hi = min(calls), max(calls)
    union, last = 0, None
    for c in calls:
        a, b = c - match_s, c + match_s
        if last is not None and a <= last:
            a = last
        if b > a:
            union += b - a
            last = b
    return {
        "match_s": match_s,
        "n_scopes": len(scopes),
        "n_before_the_transcript_corpus": len(before),
        "n_ours": len(ours), "n_theirs": len(theirs),
        "frac_ours": (len(ours) / (len(ours) + len(theirs))
                      if (ours or theirs) else None),
        "chance_match_rate": round(union / (hi - lo), 4) if hi > lo else None,
        "n_calls": len(calls),
        "ours": ours, "theirs": theirs,
        "why": ("the sentence `the scopes are this program`s footprints` is a "
                "claim about THIS fraction, not about the probe-side one"),
    }


def split_scopes_by_round(journal_text: str, doses: Iterable,
                          match_s: int = 120) -> dict:
    """`split_scopes_by_provenance`, but keeping WHICH round each scope is.

    Round 490. `split_scopes_by_provenance` answers "is this login ours?" and
    throws away the only thing that makes the lead-lag confound checkable: a
    login belongs to a ROUND, a round makes about a dozen of them in ten to
    twenty-five minutes, and it is that train -- not the population -- that
    can manufacture a right shoulder out of nothing.

    A scope is attributed to the round whose NEAREST call matched it, which is
    the same decision `split_scopes_by_provenance` makes; this only records the
    answer instead of discarding it. Scopes matching no call are returned under
    the key `None`, because "the box's own logins" is a real block too and
    dropping it would hide the negative control.
    """
    calls = []
    for d in doses:
        if d.get("missing"):
            continue
        for c in d.get("calls", []):
            if c.get("issued_utc"):
                calls.append((_iso_seconds(c["issued_utc"]), d["round"]))
    if not calls:
        raise PerturbationError("no NUC calls in any transcript")
    calls.sort()
    secs = [c for c, _ in calls]
    first = min(d["first_contact_utc"][:10] for d in doses
                if d.get("first_contact_utc"))

    blocks: dict = {}
    before = 0
    for e in parse_unit_starts_any_kind(journal_text, ("scope",)):
        if e.at_utc[:10] < first:
            before += 1
            continue
        t = _iso_seconds(e.at_utc)
        i = bisect.bisect_left(secs, t)
        best, bestd = None, None
        for j in (i - 1, i):
            if 0 <= j < len(calls):
                d = abs(calls[j][0] - t)
                if bestd is None or d < bestd:
                    best, bestd = calls[j][1], d
        blocks.setdefault(best if bestd is not None and bestd <= match_s
                          else None, []).append(e)
    return {"blocks": blocks, "match_s": match_s,
            "n_before_the_transcript_corpus": before,
            "n_rounds_with_scopes": sum(1 for k in blocks if k is not None),
            "n_scopes_ours": sum(len(v) for k, v in blocks.items()
                                 if k is not None),
            "n_scopes_not_ours": len(blocks.get(None, [])),
            "why": ("the lead-lag confound is WITHIN a round's login train, "
                    "so the train has to survive the split that identifies "
                    "it")}


def scope_provenance_nulls(bmap: BucketMap, split: dict,
                           trials: int = 2000, seed: int = 20260903) -> dict:
    """The covered-rate null run on each half of the split.

    The decisive decomposition. If the scope population's association with
    costly buckets is this program's doing, it lives in `ours`; if it is the
    box's own login traffic, it lives in `theirs`. Round 466 could not ask
    this because it had no per-call record to split on.
    """
    out = {}
    for name in ("ours", "theirs"):
        fires = split[name]
        if not fires:
            out[name] = {"n_fires": 0, "why": "empty half"}
            continue
        try:
            out[name] = shift_null_covered(bmap, fires, trials, seed)
        except PerturbationError as e:                   # pragma: no cover
            out[name] = {"n_fires": len(fires), "error": str(e)}
    a, b = out.get("ours", {}), out.get("theirs", {})
    if "observed_rate" in a and "observed_rate" in b:
        out["verdict"] = (
            "the association is carried by THIS PROGRAM's logins"
            if a["p_value"] <= 0.05 and b["p_value"] > 0.05 else
            "the association is carried by logins that are NOT this program's"
            if b["p_value"] <= 0.05 and a["p_value"] > 0.05 else
            "both halves are associated; the split does not separate them"
            if a["p_value"] <= 0.05 and b["p_value"] <= 0.05 else
            "neither half survives on its own")
    return out


# ----------------------------------------------------------------- CLI

def _load(path: str) -> str:
    return Path(path).read_text(errors="replace")


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="mode", required=True)

    sd = sub.add_parser("dose", help="per-round dose from the transcripts")
    sd.add_argument("--rounds", required=True,
                    help="comma-separated round numbers")
    sd.add_argument("--transcripts", default="logs")
    sd.add_argument("--calls", action="store_true",
                    help="include every classified call")

    sr = sub.add_parser("run", help="the whole experiment: dose, response, "
                                    "controls, nulls, cross-checks")
    sr.add_argument("--capture", required=True)
    sr.add_argument("--rounds", required=True)
    sr.add_argument("--transcripts", default="logs")
    sr.add_argument("--journal", default=None)
    sr.add_argument("--sar", default=None)
    sr.add_argument("--trials", type=int, default=PERM_TRIALS)
    sr.add_argument("--shift-trials", type=int, default=SHIFT_TRIALS)
    sr.add_argument("--seed", type=int, default=20260903)
    sr.add_argument("--before", type=int, default=WINDOW_BEFORE_S)
    sr.add_argument("--after", type=int, default=WINDOW_AFTER_S)
    sr.add_argument("--response", default="swap_bytes",
                    choices=("swap_bytes", "n_costly_buckets", "n_buckets"))
    sr.add_argument("--strict", action="store_true",
                    help="exit 1 if the experiment finds a dose-response, "
                         "i.e. if the observer is shown to cost the box")

    args = p.parse_args(argv)

    if args.mode == "dose":
        rounds = [int(x) for x in args.rounds.split(",") if x.strip()]
        out = round_doses(rounds, args.transcripts)
        if not args.calls:
            for d in out:
                d.pop("calls", None)
        print(json.dumps(out, indent=2))
        return 0

    cap = Path(args.capture)
    sar = _load(args.sar or str(cap / "sar-all.txt"))
    journal = _load(args.journal or str(cap / "journal-pid1-full.txt"))
    rounds = [int(x) for x in args.rounds.split(",") if x.strip()]
    bmap = BucketMap(sar, journal)
    doses = round_doses(rounds, args.transcripts)
    win = score_windows(doses, bmap, args.before, args.after)
    scored = win["scored"]
    full = [r for r in scored if r["record_coverage"] == "full"]
    dr = dose_response(full, args.trials, args.seed, args.response)
    report = {
        "capture": str(cap),
        "pooled_days": win["pooled_days"],
        "min_bytes": win["min_bytes"],
        "window_s": win["window_s"],
        "n_rounds_asked": len(rounds),
        "n_scored": len(scored),
        "untestable": win["untestable"],
        "n_full_record": win["n_full"],
        "n_partial_record": win["n_partial"],
        "n_no_record": win["n_no_record"],
        "dose_response": dr,
        "dose_response_UNSTRATIFIED_do_not_quote": dict(
            dose_response(scored, args.trials, args.seed, args.response),
            warning="pooled over windows the sar record does not cover; a "
                    "down-round window has a zero response BY CONSTRUCTION "
                    "and two probe calls, so this table measures the box's "
                    "power state. Kept to show the size of the error."),
        "windows_shift_null": window_shift_null(bmap, full,
                                                args.shift_trials, args.seed),
        "windows_shift_null_whole_day": window_shift_null(bmap, full,
                                                          args.shift_trials,
                                                          args.seed,
                                                          whole_day=True),
        "windows_shift_null_round_days_only": window_shift_null(
            bmap, full, args.shift_trials, args.seed,
            restrict_to_round_days=True),
        "windows_shift_null_round_days_whole_day": window_shift_null(
            bmap, full, args.shift_trials, args.seed, whole_day=True,
            restrict_to_round_days=True),
        "covered_rate_null": covered_rate_null(bmap, full, args.shift_trials,
                                               args.seed),
        "dose_vs_scopes": dose_vs_scopes(full, journal),
        "scope_provenance": scope_provenance(journal, doses),
        "scored": scored,
    }
    split = split_scopes_by_provenance(journal, doses)
    report["scope_split"] = {k: v for k, v in split.items()
                             if k not in ("ours", "theirs")}
    report["scope_split_nulls"] = scope_provenance_nulls(
        bmap, split, args.shift_trials, args.seed)
    print(json.dumps(report, indent=2))
    if args.strict and dr["verdict"].startswith("DOSE-RESPONSE"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
