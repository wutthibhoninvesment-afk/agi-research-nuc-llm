#!/usr/bin/env python3
"""What a NUC capture actually banked, and what only ever existed on the box.

Round 406 (NUC-integration E). The box went down at 2026-08-31T16:30:00.1Z and
this round could not reach it. Everything round 406 was able to answer, it
answered out of `state/nuc-capture-r400/` -- 14 files a previous round happened
to commit. Everything it could NOT answer, it could not answer for one reason:
the capture had been filtered, and nothing recorded what the filter removed.

The concrete case. Round 400 handed forward "prove or drop the fwupd
attribution". The decisive test is to attribute a bucket's cost to the units
that were RUNNING during it rather than the one that happened to START in it --
`cost_ledger` places a fire at an instant, but cost accrues over a runtime. That
test needs one field: when each unit finished. The capture holds 358
`Starting <unit>.service` lines and **zero** `Finished` lines, because it was
grepped for `Starting|Started` and a systemd oneshot logs `Finished`, never
`Started`. So 330 of the 358 fires -- 92.2%, and every single housekeeping unit
the ledger blames -- have no derivable duration, and the test cannot be run at
all from banked data.

That is not a small omission, and the thing that makes it expensive is not the
omission itself but that it was INVISIBLE. `unit-starts.txt` is 112 kB of real
journal; it looks complete. Nothing in the tree said "this is `Starting|Started`
only", so round 406 spent its first hour designing an analysis against a field
that was never there.

WHAT THIS MODULE IS
-------------------
A manifest: it reads a capture directory and states, per source, what is
present and what is absent, against a declared list of what this program's
analyses need. Its point is that "we have the sysstat archive" becomes a
CHECKED claim with a date on it, rather than an assumption carried between
rounds. `plan` then emits the exact shell to close the gaps on the next
up-round, so the fix is one command and not a paragraph of good intentions.

It cannot tell you what is in the binary `saNN` files -- only the box can, and
`sar` renders only the activity you ask for. That asymmetry is the whole risk:
`sa23` is overwritten on 2026-09-23 and the rendered captures are all that will
survive it.

Pure text-in / dict-out like `nuc/perturbation.py`: it opens no socket and runs
no command, so it is safe to import from any track and cannot contact port 8001.

CLI
    python3 nuc/capture_manifest.py audit --capture state/nuc-capture-r400
    python3 nuc/capture_manifest.py plan  --capture state/nuc-capture-r400
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass

# --------------------------------------------------------------- requirements

# `sar` activity flags are CASE-SENSITIVE and the cases mean different things:
# `-B` is paging, `-b` is block-I/O rates; `-S` is swap SPACE, `-s` is a start
# time. Round 400's capture labelled its sections `### SAR_<FLAG>_SA<NN>` with
# the flag upper-cased, which silently merges those pairs -- `SAR_B_SA30` could
# be either activity, and only its column header (`pgpgin/s`) says which. The
# first draft of this module inherited that and printed the required paging
# activity as `-b`, i.e. named the wrong flag in the remediation it emits.
#
# So activities carry an unambiguous marker KEY and the literal flag separately.
# The generated plan writes the key; the legacy single-letter markers are still
# read, because `state/nuc-capture-r400/` is the only capture that exists.


@dataclass(frozen=True)
class Activity:
    key: str                  # marker token, unambiguous across flag case
    flag: str                 # the literal `sar` argument, case as sar wants it
    why: str                  # the nuc/ analysis that reads it, or why we keep it
    required: bool            # required == some nuc/ module parses it today


ACTIVITIES = (
    Activity("R", "-r", "memory / Committed_AS steps (perturbation.commit_steps)", True),
    Activity("W", "-W", "swap-out buckets (perturbation.swap_excursions, cost_ledger)", True),
    Activity("B", "-B", "paging, the page-cache channel (round 388's apt finding)", True),
    Activity("U", "-u", "CPU utilisation", False),
    Activity("Q", "-q", "run-queue and load average", False),
    Activity("SWAPSPACE", "-S", "swap SPACE used (vs -W's swap TRAFFIC)", False),
    Activity("IO", "-b", "block I/O rates -- NOT -B; see the note above", False),
    Activity("DEV", "-d", "per-device block I/O", False),
    Activity("NET", "-n DEV", "network", False),
    Activity("CSW", "-w", "context switches and forks", False),
)

REQUIRED_SAR_ACTIVITIES = {a.key: a for a in ACTIVITIES if a.required}
OPTIONAL_SAR_ACTIVITIES = {a.key: a for a in ACTIVITIES if not a.required}

# journald line kinds, and what each one is load-bearing for.
REQUIRED_JOURNAL_KINDS = {
    "Starting": "the fire instant -- perturbation.parse_unit_starts",
    "Finished": "oneshot COMPLETION; the only source of a run duration, and "
                "absent from every capture this program has taken",
    "Started": "long-running-service readiness",
    "Failed": "distinguishes a unit that ran from one that died retrying",
}

# `+`, not a single letter: `capture_plan` emits multi-character keys
# (`SWAPSPACE`, `NET`, `CSW`) precisely to break the `-B`/`-b` collision, and
# the first draft of this regex could not read back the markers its own plan
# writes -- a capture would have audited as missing every optional activity it
# had just successfully captured.
_SECTION = re.compile(r"^###\s+SAR_([A-Za-z]+)_SA(\d{2})\s*$")
_SYSSTAT_FILE = re.compile(r"\bsa(\d{2})\b")
_JOURNAL_KIND = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\S*\s+\S+\s+"
    r"systemd\[1\]:\s+(\w+)\s+(\S+?)\.service")


class CaptureManifestError(ValueError):
    pass


# --------------------------------------------------------------- sar coverage


def sar_coverage(text: str) -> dict:
    """`### SAR_<FLAG>_SA<NN>` section markers -> {flag: [day, ...]}.

    Round 400's capture writes one marker per (activity, day-file) pair, which
    is the only place the pairing is recorded -- the rendered table itself does
    not say which `sar` flag produced it, and `-r` and `-B` tables are
    distinguishable only by their column headers.
    """
    by_flag: dict = {}
    for line in text.splitlines():
        m = _SECTION.match(line.strip())
        if m:
            by_flag.setdefault(m.group(1).upper(), set()).add(m.group(2))
    day_files = sorted(set(_SYSSTAT_FILE.findall(text)))
    return {
        "day_files_on_box": day_files,
        "by_activity": {k: sorted(v) for k, v in sorted(by_flag.items())},
        "n_activities": len(by_flag),
    }


# ------------------------------------------------------------ journal coverage


def journal_coverage(text: str) -> dict:
    """Which systemd line kinds survived the capture's grep, and what that costs.

    `durations_derivable` is the number of `Starting` events for which some
    terminal line for the SAME unit also exists. It is the number that decides
    whether interval-attribution can be run offline, and on every capture this
    program has taken so far it is a small fraction of the fires.
    """
    kinds: dict = {}
    per_unit: dict = {}
    stamps = []
    for line in text.splitlines():
        m = _JOURNAL_KIND.match(line.strip())
        if not m:
            continue
        stamp, kind, unit = m.groups()
        kinds[kind] = kinds.get(kind, 0) + 1
        per_unit.setdefault(unit, set()).add(kind)
        stamps.append(stamp)

    starting_units = {u for u, ks in per_unit.items() if "Starting" in ks}
    terminal = {"Started", "Finished", "Failed"}
    closed = {u for u in starting_units if per_unit[u] & terminal}
    n_starting = kinds.get("Starting", 0)
    n_closed = sum(1 for line in text.splitlines()
                   if (m := _JOURNAL_KIND.match(line.strip()))
                   and m.group(2) == "Starting" and m.group(3) in closed)
    return {
        "kinds": dict(sorted(kinds.items())),
        "first_utc": min(stamps) if stamps else None,
        "last_utc": max(stamps) if stamps else None,
        "n_units_with_a_start": len(starting_units),
        "n_units_never_closed": len(starting_units - closed),
        "units_never_closed": sorted(starting_units - closed),
        "n_starting_events": n_starting,
        "durations_derivable": n_closed,
        "durations_missing": n_starting - n_closed,
        "durations_derivable_fraction":
            (n_closed / n_starting) if n_starting else None,
    }


# ------------------------------------------------------------------- the audit


@dataclass(frozen=True)
class Gap:
    """One thing the capture does not contain, and what it costs."""
    source: str
    missing: str
    why_it_matters: str
    recoverable: str          # "only-on-box" | "never" | "in-capture"
    blocking: bool            # True == some nuc/ module needs it today

    def as_dict(self) -> dict:
        return asdict(self)


def audit(sar_text: str, journal_text: str,
          activities=ACTIVITIES,
          required_journal: dict | None = None) -> dict:
    """Grade one capture against what `nuc/` actually needs.

    The verdict is `complete` only if every REQUIRED activity covers every day
    file on the box AND every required journal kind is present. Optional
    activities are reported as gaps too, because their recoverability expires
    with the day file rather than with the round -- `sa23` is overwritten on
    2026-09-23 and nothing renders an activity that was never captured.
    """
    required_journal = (REQUIRED_JOURNAL_KINDS if required_journal is None
                        else required_journal)
    sar = sar_coverage(sar_text)
    jrn = journal_coverage(journal_text)
    days = set(sar["day_files_on_box"])
    gaps: list = []

    for a in activities:
        # Legacy captures label sections by upper-cased FLAG, not by key, so a
        # single-letter key is also looked up under its flag letter.
        have = set(sar["by_activity"].get(a.key, []))
        have |= set(sar["by_activity"].get(a.flag.lstrip("-")[0].upper(), [])) \
            if len(a.key) == 1 else set()
        missing_days = sorted(days - have) if days else []
        if not days and not have:
            missing_days = ["(no day files listed)"]
        if missing_days:
            gaps.append(Gap(
                source="sar",
                missing=f"`sar {a.flag}` for " + (
                    "every day file" if len(missing_days) == len(days) or not days
                    else "sa" + ",sa".join(missing_days)),
                why_it_matters=a.why + ("" if a.required
                                        else " (no nuc/ module reads it yet)"),
                recoverable="only-on-box", blocking=a.required))

    for kind, why in sorted(required_journal.items()):
        if not jrn["kinds"].get(kind):
            gaps.append(Gap(
                source="journal", missing=f"`{kind} <unit>.service` lines",
                why_it_matters=why, recoverable="only-on-box", blocking=True))

    blocking = [g for g in gaps if g.blocking]
    return {
        "sar": sar,
        "journal": jrn,
        "n_gaps": len(gaps),
        "n_blocking_gaps": len(blocking),
        "verdict": "complete" if not blocking else "filtered",
        "gaps": [g.as_dict() for g in gaps],
    }


# -------------------------------------------------------------------- the plan


def capture_plan(audit_result: dict, capture_dir: str = "state/nuc-capture-rNNN",
                 activities=ACTIVITIES) -> str:
    """The shell to run on the next up-round, derived from the gaps found.

    Emitted as a script rather than prose for one reason: round 400 wrote its
    equivalent as a numbered handoff item marked TIME-CRITICAL, and the next
    E round -- this one -- opened to a box that was already unreachable. A
    command can be run in the first thirty seconds of a round. A paragraph has
    to be read, understood and retyped first.

    Section markers use the unambiguous KEY, not the upper-cased flag, so
    `sar -B` and `sar -b` do not collide the way they do in round 400's file.

    Read-only on the box bar the tarball, which goes to `~/nuc-research/`, an
    allowed write path. Touches no unit and no engine port.
    """
    days = audit_result.get("sar", {}).get("day_files_on_box") or []
    pairs = " ".join(f"{a.key}:{a.flag.replace(' ', '=')}" for a in activities)
    lines = [
        "#!/usr/bin/env bash",
        "# Full-fidelity NUC capture. Generated by nuc/capture_manifest.py plan.",
        "# READ-ONLY on the box except ~/nuc-research/ (an allowed write path).",
        "# No unit is restarted; port 8001 is never contacted; no engine request.",
        "set -euo pipefail",
        'NUC="${NUC:-jab@100.78.44.111}"',
        'KEY="${KEY:-$HOME/.ssh/id_ed25519}"',
        f'OUT="${{OUT:-{capture_dir}}}"',
        'mkdir -p "$OUT"',
        "",
        "# 1. The binary day files themselves -- ~2 MB, and the ONLY artifact",
        "#    from which an un-captured `sar` activity can still be rendered.",
        "#    sa23 is overwritten on 2026-09-23; everything older is already gone.",
        "ssh -i \"$KEY\" \"$NUC\" 'tar -C /var/log/sysstat -cf - $(cd /var/log/sysstat && ls sa[0-9][0-9])' \\",
        '  > "$OUT/sysstat-binary.tar"',
        "",
        "# 2. Every activity we read, plus every activity we do not read yet but",
        "#    which expires with the day file. One ssh, one file, self-labelling.",
        "#    Markers carry an unambiguous KEY because `-B` and `-b` are different",
        "#    activities that upper-case to the same letter.",
        'ssh -i "$KEY" "$NUC" \'bash -s\' > "$OUT/sar-all.txt" <<\'REMOTE\'',
        "echo '### SYSSTAT_FILES'; ls -l /var/log/sysstat/",
        f"for pair in {pairs}; do",
        '  key=${pair%%:*}; flag=${pair#*:}; flag=${flag//=/ }',
        "  for f in /var/log/sysstat/sa[0-9][0-9]; do",
        '    echo "### SAR_${key}_SA${f##*/sa}"',
        '    LC_ALL=C sar $flag -f "$f" 2>&1 || true',
        "  done",
        "done",
        "REMOTE",
        "",
        "# 3. The journal WITHOUT a grep that drops completions. Round 400's",
        "#    capture kept `Starting|Started` only, so 330 of its 358 fires -- and",
        "#    every housekeeping unit in the cost ledger -- have no duration, and",
        "#    round 406's interval-attribution test could not be run at all.",
        'ssh -i "$KEY" "$NUC" \'journalctl -b -o short-iso --no-pager _PID=1\' \\',
        '  > "$OUT/journal-pid1-full.txt"',
        "",
        "# 4. Manifest the result before trusting it. Non-zero exit = still filtered.",
        'python3 nuc/capture_manifest.py audit --capture "$OUT" --strict',
    ]
    if days:
        lines.insert(9, f"# Day files present at last audit: sa{', sa'.join(days)}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------- io/cli


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError as exc:
        raise CaptureManifestError(f"cannot read {path}: {exc}") from exc


# The two filenames round 400 used. Named here rather than globbed so a capture
# that is missing one FAILS instead of silently auditing half of itself.
SAR_CANDIDATES = ("sar-all.txt", "sar.txt")
JOURNAL_CANDIDATES = ("journal-pid1-full.txt", "unit-starts.txt", "journal.txt")


def _pick(capture_dir: str, candidates) -> str:
    for name in candidates:
        p = os.path.join(capture_dir, name)
        if os.path.exists(p):
            return p
    raise CaptureManifestError(
        f"{capture_dir}: none of {', '.join(candidates)} present")


def audit_dir(capture_dir: str) -> dict:
    sar_p = _pick(capture_dir, SAR_CANDIDATES)
    jrn_p = _pick(capture_dir, JOURNAL_CANDIDATES)
    out = audit(_read(sar_p), _read(jrn_p))
    out["capture_dir"] = capture_dir
    out["sources"] = {"sar": sar_p, "journal": jrn_p}
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="mode", required=True)
    ap = sub.add_parser("audit", help="what this capture banked, and what it did not")
    ap.add_argument("--capture", required=True)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any BLOCKING gap remains")
    pp = sub.add_parser("plan", help="shell to close the gaps on the next up-round")
    pp.add_argument("--capture", required=True)
    pp.add_argument("--out-dir", default="state/nuc-capture-rNNN")

    args = p.parse_args(argv)
    try:
        result = audit_dir(args.capture)
    except CaptureManifestError as exc:
        print(f"capture-manifest ERROR: {exc}", file=sys.stderr)
        return 2
    if args.mode == "audit":
        print(json.dumps(result, indent=2))
        return 1 if (args.strict and result["n_blocking_gaps"]) else 0
    print(capture_plan(result, args.out_dir), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
