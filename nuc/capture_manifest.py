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
import math
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
    # Round 424. What the ABSENCE is evidence of. Round 406 had only one
    # answer -- "the capture dropped it" -- and so reported a box on which
    # nothing failed as a capture defect, forever. "box-state" says the
    # capture is fine and the world is quiet; "window" says every required
    # KIND is present and the problem is which DAYS they cover.
    absence_means: str = "filtered"

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

    # Round 424. Any terminal kind at all proves the capture was not passed
    # through round 400's `Starting|Started` grep. Once that is established,
    # a missing `Failed` line stops being a fact about the capture.
    witnessed = [k for k in UNFILTERED_WITNESS_KINDS if jrn["kinds"].get(k)]
    for kind, why in sorted(required_journal.items()):
        if jrn["kinds"].get(kind):
            continue
        box_state = bool(witnessed) and kind in BOX_STATE_KINDS
        gaps.append(Gap(
            source="journal", missing=f"`{kind} <unit>.service` lines",
            why_it_matters=(
                why + (" -- but %s line(s) survived, so this capture was not "
                       "filtered and the absence is a fact about the BOX: "
                       "nothing failed in the window."
                       % "/".join(witnessed)) if box_state else why),
            recoverable="in-capture" if box_state else "only-on-box",
            blocking=not box_state,
            absence_means="box-state" if box_state else "filtered"))

    # Round 424. The axis this module was blind on. Two captures taken minutes
    # apart -- one `journalctl -b`, one unrestricted -- returned identical
    # verdicts here while covering 81 and 1652 unit fires respectively.
    span = journal_span_coverage(journal_text, sar["day_files_on_box"])
    for day in span["uncovered"]:
        gaps.append(Gap(
            source="journal",
            missing=f"any systemd[1] line dated day {day} (pairs with sa{day})",
            why_it_matters=("attribution needs a fire and a bucket in the SAME "
                            "window; this day file has buckets and no fires"),
            recoverable="only-on-box", blocking=True, absence_means="window"))

    blocking = [g for g in gaps if g.blocking]
    kinds_ok = not [g for g in blocking if g.absence_means == "filtered"]
    if not blocking:
        verdict = "complete"
    elif kinds_ok:
        verdict = "narrow"          # right lines, wrong days
    else:
        verdict = "filtered"
    return {
        "sar": sar,
        "journal": jrn,
        "span": span,
        "unfiltered_witnesses": witnessed,
        "n_gaps": len(gaps),
        "n_blocking_gaps": len(blocking),
        "verdict": verdict,
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
        "#    Round 424: DO NOT trust a hardcoded expiry here. `sa2` runs",
        "#    `find $SA_DIR -mtime +$HISTORY | xargs rm -f` and HISTORY is 7",
        "#    on this box, so day files are DELETED at 7 days, not overwritten",
        "#    at 31. Run `capture_manifest.py retention` for the real dates.",
        "#    `sar[0-9][0-9]` joins the glob: those are sysstat's own",
        "#    pre-rendered daily reports, they expire on the same sweep, and",
        "#    no round before 424 captured them.",
        "ssh -i \"$KEY\" \"$NUC\" 'tar -C /var/log/sysstat -cf - $(cd /var/log/sysstat && ls sa[0-9][0-9] sar[0-9][0-9] 2>/dev/null)' \\",
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
        '#    Round 424: `-b` is GONE from this line and must not come back.',
        '#    This plan only runs when the box is reachable, and on 2026-09-01',
        '#    the box became reachable by REBOOTING -- so `-b` would have',
        '#    captured 2h40m and 81 fires in place of 8d18h and 1652.',
        'ssh -i "$KEY" "$NUC" \'journalctl -o short-iso --no-pager _PID=1\' \\',
        '  > "$OUT/journal-pid1-full.txt"',
        '',
        '# 3b. The boot table. `_PID=1` is the SYSTEM manager only, so the boot',
        '#     table is what tells a reboot from a resume -- and, round 448, what',
        '#     turns a MISSING scheduled fire into "the box was down at it".',
        'ssh -i "$KEY" "$NUC" \'journalctl --list-boots --no-pager\' > "$OUT/journal-boots.txt"',
        '',
        '# 3c. The USER manager unit journals, one file per unit, self-labelling.',
        '#     Round 436 opened `journal-user-full.txt` expecting the user',
        '#     MANAGER and found 329 `coli[...]` engine lines, half of them a',
        '#     duplicate of that same file unlabelled lead section under a',
        '#     hand-written `### USER_MANAGER` header. Two causes, both fixed',
        '#     here: the comment above the command named the manager while the',
        '#     command named the engine UNIT (they are not the same journal), and',
        '#     the command emitted NO `### ` marker, so a second view appended to',
        '#     the same file was indistinguishable from the first. Every stream',
        '#     below announces itself, exactly like step 2 and step 3d.',
        '#     `qwen36-toolproxy` joins `qwen36-colibri`: round 436 found it has',
        '#     its own `Consumed` records and 9 `Started` fires that appear in no',
        '#     capture this program has ever taken.',
        'ssh -i "$KEY" "$NUC" \'journalctl _SYSTEMD_USER_UNIT=qwen36-colibri.service -o short-iso --no-pager\' \\',
        '  | { echo "### USER_UNIT_qwen36-colibri"; cat; } > "$OUT/journal-user-qwen36-colibri.txt"',
        'ssh -i "$KEY" "$NUC" \'journalctl _SYSTEMD_USER_UNIT=qwen36-toolproxy.service -o short-iso --no-pager\' \\',
        '  | { echo "### USER_UNIT_qwen36-toolproxy"; cat; } > "$OUT/journal-user-qwen36-toolproxy.txt"',
        '# The user MANAGER itself (`systemd[<uid>]`), which is a DIFFERENT',
        '# journal from any unit it owns and is where a user-unit start/stop is',
        '# actually announced. Its own file, never concatenated with a unit one.',
        'ssh -i "$KEY" "$NUC" \'journalctl --user -o short-iso --no-pager\' \\',
        '  | { echo "### USER_MANAGER"; cat; } > "$OUT/journal-user-manager.txt"',
        '',
        '# 3d. What the COLLECTOR does to the numbers, banked as evidence rather',
        '#     than re-derived each round. `sadc` matches `pgsteal_` as a bare',
        '#     prefix but `pgscan_kswapd`/`pgscan_direct` as full names, so on a',
        '#     kernel exporting both an actor split and an anon/file split,',
        '#     pgsteal is summed twice and pgscan is not.',
        'ssh -i "$KEY" "$NUC" \'bash -s\' > "$OUT/collector-evidence.txt" <<\'EV\'',
        'strings /usr/lib/sysstat/sadc | grep -E "^pg[a-z_]*$" | sort -u',
        'grep -E "^(pgscan|pgsteal)" /proc/vmstat; sar -V | head -2',
        'grep -vE "^[[:space:]]*#|^[[:space:]]*$" /etc/sysstat/sysstat',
        'ls -l /var/log/sysstat/; systemctl list-timers sysstat-summary.timer --no-pager',
        'EV',
        "",
        '# 3e. `Persistent=` on the sweep timer -- round 448. This one setting',
        '#     decides whether an outage SAVES a day file or merely delays its',
        '#     death by a few hours, and it is the whole basis of',
        '#     `capture_manifest.py retention --down-since`. Round 448 derived',
        '#     the answer (not persistent) from the fires the box itself',
        '#     missed and never re-ran',
        '#     because no capture had ever taken the unit text. Capturing it',
        '#     turns a two-trial inference into a read.',
        'ssh -i "$KEY" "$NUC" \'bash -s\' > "$OUT/timer-units.txt" <<\'TMR\'',
        'for t in sysstat-summary sysstat-collect; do',
        '  echo "### TIMER_UNIT_$t"; systemctl cat "$t.timer" 2>&1 || true',
        '  echo "### TIMER_SHOW_$t"',
        '  systemctl show "$t.timer" -p Persistent -p OnCalendar -p RandomizedDelaySec \\',
        '    -p AccuracySec -p NextElapseUSecRealtime -p LastTriggerUSec 2>&1 || true',
        'done',
        'TMR',
        '',
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
# Round 448. The boot table is what turns "no `Starting` line" into "the box
# was down", and it is the only file in the capture that carries it.
BOOTS_CANDIDATES = ("journal-boots.txt",)
# Round 424. `ls -l /var/log/sysstat` is the only record of a day file's
# mtime, and mtime is the whole input to the retention sweep. Both the
# dedicated evidence file and the head of `sar-all.txt` carry it.
RETENTION_CANDIDATES = ("collector-evidence.txt", "sar-all.txt")


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
    rp = sub.add_parser(
        "retention",
        help="which day files the NEXT sysstat sweep deletes (round 424)")
    rp.add_argument("--capture", required=True)
    rp.add_argument("--next-run", required=True,
                    help="UTC of the next sysstat-summary fire, e.g. "
                         "2026-09-02T00:07:00Z (`systemctl list-timers`)")
    rp.add_argument("--now", required=True,
                    help="UTC the `ls -l` was taken; `ls` omits the year")
    rp.add_argument("--history", type=int, default=7,
                    help="HISTORY from /etc/sysstat/sysstat")
    rp.add_argument("--strict", action="store_true",
                    help="exit 1 if the next sweep deletes anything")
    # Round 448. A fire the box sleeps through deletes nothing and is not
    # deferred, so a forecast that ignores the outage record over-reports
    # loss -- in the direction that makes a later round give up on a file
    # still sitting on disk.
    rp.add_argument("--skipped-fire", action="append", default=[],
                    metavar="UTC",
                    help="a scheduled fire that provably did not run "
                         "(repeatable); the forecast walks past it")
    rp.add_argument("--down-since", metavar="UTC",
                    help="box last seen alive at this instant; with "
                         "--down-until, every fire in the window is skipped")
    rp.add_argument("--down-until", metavar="UTC",
                    help="latest instant the box is known to be STILL down "
                         "(normally now)")
    rp.add_argument("--period-days", type=int, default=1,
                    help="sweep timer period (OnCalendar daily = 1)")

    sw = sub.add_parser(
        "sweeps",
        help="did the sweep actually fire, and is a missed fire caught up? "
             "(round 448)")
    sw.add_argument("--capture", required=True)
    sw.add_argument("--anchor", required=True,
                    help="UTC of ONE fire, observed or announced, to fix the "
                         "lattice; do not hardcode 00:07")
    sw.add_argument("--unit", default=DEFAULT_SWEEP_UNIT)
    sw.add_argument("--period-days", type=int, default=1)
    sw.add_argument("--strict", action="store_true",
                    help="exit 1 if the persistence verdict is unknown -- i.e. "
                         "the box never ran the experiment and the deadline "
                         "cannot be called conditional on evidence")

    args = p.parse_args(argv)
    if args.mode == "sweeps":
        try:
            jrn = _read(_pick(args.capture, JOURNAL_CANDIDATES))
            boots = _read(_pick(args.capture, BOOTS_CANDIDATES))
            hist = sweep_history(jrn, boots, args.anchor, args.unit,
                                 args.period_days)
        except CaptureManifestError as exc:
            print(f"capture-manifest ERROR: {exc}", file=sys.stderr)
            return 2
        out = dict(hist)
        out["persistence"] = persistence_verdict(hist)
        out["capture_dir"] = args.capture
        print(json.dumps(out, indent=2))
        return 1 if (args.strict
                     and out["persistence"]["persistent"] == "unknown") else 0
    if args.mode == "retention":
        try:
            text = _read(_pick(args.capture, RETENTION_CANDIDATES))
        except CaptureManifestError as exc:
            print(f"capture-manifest ERROR: {exc}", file=sys.stderr)
            return 2
        files = parse_sysstat_ls(text, args.now)
        if not files:
            print("capture-manifest ERROR: no `ls -l` lines found; retention "
                  "cannot be derived and must NOT be assumed", file=sys.stderr)
            return 2
        skipped = list(args.skipped_fire)
        if bool(args.down_since) != bool(args.down_until):
            print("capture-manifest ERROR: --down-since and --down-until must "
                  "be given together; one alone names no window",
                  file=sys.stderr)
            return 2
        if args.down_since:
            skipped += fires_lost_to_outage(args.next_run, args.down_since,
                                            args.down_until, args.period_days)
        out = retention_forecast(files, args.next_run, history_days=args.history,
                                 skipped_fires=sorted(set(skipped)),
                                 period_days=args.period_days)
        print(json.dumps(out, indent=2))
        return 1 if (args.strict and out["n_deleted_at_next_run"]) else 0
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



# =====================================================================
# Round 424 (NUC-integration E). Three defects this module had, all found
# by RUNNING the plan it emits against a live box for the first time.
#
# 1. THE PLAN WAS BOOT-SCOPED. Step 3 was `journalctl -b`. The plan can only
#    run when the box is reachable, and on 2026-09-01 the box became
#    reachable by REBOOTING -- so `-b` covered 2 h 40 m and 81 unit fires,
#    against the 8 d 18 h and 1652 fires the same command yields without it.
#    A remediation plan that is gated on a condition clearing is exposed to
#    whatever cleared it. Here the gate and the invalidator were the same
#    event.
#
# 2. THE AUDIT COULD NOT SEE THAT. Run on the boot-scoped capture and on the
#    full one, `audit` returned the SAME verdict, the same `n_gaps`, the same
#    `n_blocking_gaps`, and `durations_derivable_fraction` 1.0 for both. It
#    graded which KINDS of line survived and never asked what WINDOW they
#    covered, which is the only axis the two captures differ on.
#    `journal_span_coverage` is that axis.
#
# 3. `--strict` COULD NEVER PASS. `Failed <unit>.service` was required, so a
#    box on which nothing failed audited as `filtered` forever. Absence of
#    `Finished` is evidence about the CAPTURE (round 400's grep dropped it);
#    absence of `Failed` on a capture that has 1580 `Finished` lines is
#    evidence about the BOX. A gate that is red on a healthy box is a gate
#    nobody reads.
#
# And the hardcoded line "sa23 is overwritten on 2026-09-23", carried in the
# emitted plan by rounds 406/412/418, was wrong by 21 days. `/usr/lib/
# sysstat/sa2` ends with `find $SA_DIR -mtime +$HISTORY | xargs rm -f` and
# `/etc/sysstat/sysstat` sets `HISTORY=7`: day files are DELETED at 7 days,
# they do not survive to be overwritten by the next month's same-numbered
# file. `retention_forecast` derives the real date instead.
# =====================================================================

import calendar
import datetime as _dt

# systemd emits these when a unit terminates. Any ONE of them proves the
# capture was not passed through a `Starting|Started` grep, which is the
# filter round 400 applied and the one this module exists to detect.
UNFILTERED_WITNESS_KINDS = ("Finished", "Stopped", "Stopping")

# `Failed` is the kind whose absence is ambiguous, and the ambiguity resolves
# in opposite directions depending on the witnesses. Kept OUT of the blocking
# set when a witness is present, rather than dropped: a capture that really
# was filtered still needs to be told so.
BOX_STATE_KINDS = ("Failed",)


def _day_of_month_set(text: str) -> set:
    """Days-of-month for which the journal actually holds a `systemd[1]` line.

    Day-of-month rather than a full date on purpose: sysstat names its files
    `sa<DD>` and carries no month, so DD is the only key the two sides share.
    Comparing on DD is not a shortcut around a harder join -- it IS the join,
    and it is exact as long as the capture is under a month wide, which the
    7-day retention guarantees.
    """
    days = set()
    for line in text.splitlines():
        m = _JOURNAL_KIND.match(line.strip())
        if m:
            days.add(m.group(1)[8:10])
    return days


def journal_span_coverage(journal_text: str, day_files) -> dict:
    """Which `sa<DD>` day files the journal can actually attribute fires for.

    This is the axis `audit` was blind on. A capture can hold every required
    line KIND and still be useless for attribution, because attribution needs
    a fire and a bucket in the same window, and the two sources are captured
    by different commands with independent scopes.
    """
    have = _day_of_month_set(journal_text)
    days = sorted(set(day_files))
    covered = sorted(d for d in days if d in have)
    return {
        "journal_days": sorted(have),
        "day_files": days,
        "covered": covered,
        "uncovered": sorted(d for d in days if d not in have),
        "n_covered": len(covered),
        "n_day_files": len(days),
        "coverage_fraction": (len(covered) / len(days)) if days else None,
    }


# ------------------------------------------------------------------ retention

_LS_LINE = re.compile(
    r"^\S+\s+\d+\s+\S+\s+\S+\s+(\d+)\s+"
    r"([A-Z][a-z]{2})\s+(\d{1,2})\s+(?:(\d{2}):(\d{2})|(\d{4}))\s+(\S+)\s*$")

_MONTHS = {m: i for i, m in enumerate(calendar.month_abbr) if m}


def parse_sysstat_ls(text: str, now_utc: str) -> list:
    """`ls -l /var/log/sysstat` -> [{name, size, mtime_utc}], newest first.

    `ls -l` prints `Mon DD HH:MM` for recent files and `Mon DD  YYYY` for old
    ones, and NEITHER form carries both. The year is reconstructed from
    `now_utc` by the same rule `ls` used to drop it: a timestamped entry is
    within the last six months, so if the resulting date is in the future it
    belonged to the previous year. Getting this wrong silently moves a file
    across a retention boundary, which is the exact quantity being computed.
    """
    now = _dt.datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
    out = []
    for line in text.splitlines():
        m = _LS_LINE.match(line.rstrip())
        if not m:
            continue
        size, mon, day, hh, mm, year, name = m.groups()
        if year:
            stamp = _dt.datetime(int(year), _MONTHS[mon], int(day),
                                 tzinfo=_dt.timezone.utc)
        else:
            stamp = _dt.datetime(now.year, _MONTHS[mon], int(day),
                                 int(hh), int(mm), tzinfo=_dt.timezone.utc)
            if stamp > now + _dt.timedelta(days=1):
                stamp = stamp.replace(year=now.year - 1)
        out.append({"name": name, "size": int(size),
                    "mtime_utc": stamp.strftime("%Y-%m-%dT%H:%M:%SZ")})
    return sorted(out, key=lambda e: e["mtime_utc"], reverse=True)


# `sa2`'s own regex, verbatim from /usr/lib/sysstat/sa2 on the box. It matches
# `sa23`, `sar23` and their compressed forms -- and NOT `sa1`, so a stray file
# is left alone rather than swept.
SA2_SWEEP_RE = re.compile(r"^sar?[0-9]{2,8}(\.(Z|gz|bz2|xz|lz|lzo))?$")


def find_mtime_matches(age_s: float, days: int) -> bool:
    """`find -mtime +N`, exactly: age in WHOLE 24 h units, truncated, then > N.

    The truncation is the whole subtlety and it buys a file up to 24 extra
    hours. At 2026-08-31T00:07Z `sa23` was 7.01 days old; `floor(7.01) == 7`
    is not `> 7`, so the sweep that ran that night spared it. One day later
    `floor(8.01) == 8` and it does not survive. A model that used the raw
    float would have declared `sa23` already gone and this round would not
    have bothered to capture it.
    """
    return int(age_s // 86400) > days


def _next_sweep_at_or_after(stamp_utc: str, first_run: _dt.datetime,
                            period_days: int = 1, skipped=()) -> _dt.datetime:
    """The first `sysstat-summary` fire at or after `stamp_utc` that RUNS.

    The timer is `OnCalendar=*-*-* 00:07:00`, i.e. daily, so the fires are
    `first_run + k*period` for k >= 0. Derived from the one fire the caller
    passed rather than from a hardcoded 00:07, so a box whose timer moves does
    not silently keep the old answer.

    Round 448 adds `skipped`: a set of fire instants that provably do NOT run
    because the box is down at them. A missed fire is not a delayed one on
    this box -- see `persistence_verdict`, which derives that from the box's
    own fire history rather than assuming it -- so a skipped fire deletes
    nothing and the deadline moves a whole period to the right. `skipped` is
    a set of aware datetimes; a lattice point in it is passed over.
    """
    t = _dt.datetime.fromisoformat(stamp_utc.replace("Z", "+00:00"))
    if t <= first_run:
        cand = first_run
    else:
        k = math.ceil((t - first_run).total_seconds() / (period_days * 86400))
        cand = first_run + _dt.timedelta(days=period_days * k)
    # A bounded walk: `skipped` is finite, so at most len(skipped)+1 steps can
    # be needed. Bounded explicitly rather than by `while True` so a caller
    # that passes a generated infinite set gets an error, not a hang.
    for _ in range(len(skipped) + 1):
        if cand not in skipped:
            return cand
        cand = cand + _dt.timedelta(days=period_days)
    return cand


def retention_forecast(files, next_run_utc: str,
                       history_days: int = 7,
                       compress_after_days: int = 10,
                       sweep_re=SA2_SWEEP_RE,
                       skipped_fires=(),
                       period_days: int = 1) -> dict:
    """What `sysstat-summary.service` deletes the next time it fires.

    Replaces the constant "sa23 is overwritten on 2026-09-23" that rounds
    406-418 carried in the emitted plan. That constant modelled sysstat as a
    31-slot ring buffer keyed on day-of-month, which is the mechanism when
    `HISTORY > 28`; below that, `sa2` deletes by mtime and the ring never gets
    a chance to wrap. Both mechanisms are real and the EARLIER one binds.

    The forecast is deliberately per-file rather than a single date: the
    files do not expire together, and the next sweep takes the two oldest
    while sparing the third by seventy minutes.
    """
    requested = _dt.datetime.fromisoformat(next_run_utc.replace("Z", "+00:00"))
    skipped = {_dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
               for s in skipped_fires}
    # ROUND 448. `next_run_utc` was the deadline for four rounds and it was
    # never a date -- it is a date CONDITIONAL on the box being up at it. The
    # box's own journal proves the condition binds: of 9 scheduled fires in
    # the round-424 capture's window, 2 (2026-08-30 and 2026-09-01) have no
    # `Starting sysstat-summary.service` line at all, both fall inside a
    # boot-table gap, and neither was caught up after the following boot. So
    # a fire the box sleeps through deletes NOTHING and every doomed file
    # lives another whole period. That is how `sa23` survived to be captured
    # in the first place, which round 424 noticed and attributed to luck.
    run = _next_sweep_at_or_after(next_run_utc, requested, period_days, skipped)
    passed_over = sorted(f for f in skipped if requested <= f < run)
    doomed, spared, ignored = [], [], []
    for f in files:
        if not sweep_re.match(f["name"]):
            ignored.append(f["name"])
            continue
        mt = _dt.datetime.fromisoformat(f["mtime_utc"].replace("Z", "+00:00"))
        age_s = (run - mt).total_seconds()
        row = {"name": f["name"],
               "mtime_utc": f["mtime_utc"],
               "age_days_at_run": round(age_s / 86400, 3),
               "find_age_units": int(age_s // 86400)}
        if find_mtime_matches(age_s, history_days):
            doomed.append(row)
        else:
            row["compressed_at_run"] = find_mtime_matches(
                age_s, compress_after_days)
            # The instant the file becomes SWEEPABLE -- not the instant it is
            # swept. `sa2` runs only when `sysstat-summary.timer` fires, so a
            # file eligible at 23:50 survives until the next 00:07, and a file
            # eligible at 08:10 survives sixteen hours. Round 430 split the two
            # because the field was named `survives_until` and read as a
            # deletion time: it is off by up to a day, always in the direction
            # that makes a capture look more urgent than it is. And a box that
            # is DOWN at 00:07 does not sweep at all, which is how `sa23`
            # survived to be captured in the first place (round 424) -- so
            # `deleted_at_utc` is the earliest possible deletion, never a
            # promise.
            row["sweepable_at_utc"] = (
                mt + _dt.timedelta(days=history_days + 1)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            row["survives_until_utc"] = row["sweepable_at_utc"]
            row["deleted_at_utc"] = _next_sweep_at_or_after(
                row["sweepable_at_utc"], run
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            spared.append(row)
    return {
        "next_run_utc": _fmt_utc(run),
        "requested_next_run_utc": next_run_utc,
        # Non-empty means the answer above is NOT the fire the caller asked
        # about: these fires are scheduled, are known not to run, and were
        # walked past. Empty is the ordinary case and reads identically to
        # every forecast this module produced before round 448.
        "skipped_fires": [_fmt_utc(f) for f in sorted(skipped)],
        "fires_passed_over": [_fmt_utc(f) for f in passed_over],
        "history_days": history_days,
        "compress_after_days": compress_after_days,
        "n_deleted_at_next_run": len(doomed),
        "deleted_at_next_run": doomed,
        "spared": spared,
        "not_swept": sorted(ignored),
        "earliest_sweepable_utc": min((r["sweepable_at_utc"] for r in spared),
                                      default=None),
        # The number a capture deadline should actually be set from -- and
        # round 448's correction to what that number MEANS. It is the first
        # fire at which loss becomes possible, not a wall clock. Every fire
        # in `skipped_fires` has already been walked past; a fire AFTER the
        # last known-down instant is still conditional on the box being up,
        # and this module cannot know that. `earliest_loss_conditional` says
        # so in the artefact instead of in a comment nobody reads.
        "earliest_loss_utc": min((r["deleted_at_utc"] for r in spared),
                                 default=None),
        "earliest_loss_conditional": True,
        "earliest_loss_condition": (
            "the box is UP at that fire; a fire slept through deletes nothing "
            "and is not deferred (see persistence_verdict)"),
        # A tie is the normal case -- `saNN` and `sarNN` are seventeen minutes
        # apart in mtime and land on the same 00:07 fire -- so this is a list.
        "next_files_lost": sorted(
            r["name"] for r in spared
            if r["deleted_at_utc"] == min((x["deleted_at_utc"]
                                           for x in spared), default=None)),
    }


# ------------------------------------------------- sweep history (round 448)
#
# WHY THIS EXISTS. `retention_forecast` answers "when does the box delete
# this file", and rounds 430-447 quoted its answer -- `2026-09-03T00:07:00Z`
# next loss, `2026-09-10T00:07:00Z` deadline -- as a calendar date in
# `state/research-state.md`'s standing next-steps item. It is not a calendar
# date. `sysstat-summary.timer` deletes only when it FIRES, it fires only
# when the box is up, and this box is up perhaps half the time: rounds 436,
# 442 and 448 all opened to an unreachable box.
#
# The question that decides whether an outage SAVES a file or merely DELAYS
# its death is one systemd setting, `Persistent=`. With it, a fire missed
# while the box was off runs at the next boot and the file dies anyway, a few
# hours late. Without it, the fire is simply lost and the file lives a whole
# extra period. The capture plan has never captured that setting -- round 448
# adds it -- but the answer was already in the banked journal, because the
# box ran the experiment twice by itself:
#
#   9 fires scheduled at 00:07 in the round-424 capture's journal window
#     (2026-08-23T14:02:08Z .. 2026-09-01T08:16:20Z)
#   7 `Starting sysstat-summary.service` lines present
#   2 MISSING: 2026-08-30T00:07 and 2026-09-01T00:07
#
# Both missing fires fall inside a gap in `journal --list-boots` (boot -2 ends
# 2026-08-29T02:10:07Z, boot -1 starts 2026-08-30T00:32:32Z; boot -1 ends
# 2026-08-31T16:28:00Z, boot 0 starts 2026-09-01T05:33:31Z), so the box was
# down at both. And neither was caught up: boot -1 came up 25 minutes after
# the fire it missed and logged no `sysstat-summary` run until the NEXT day's
# scheduled 00:07. Two independent trials, both saying `Persistent=` is not in
# effect. A slept-through sweep is LOST, not deferred.
#
# The absence argument is sound only because round 424 removed `-b` from the
# capture's journalctl: an unfiltered `_PID=1` journal covering the window is
# what makes "no line" mean "did not run" rather than "not captured". A
# boot-scoped capture could not support any of this.

_FIRE_LINE = re.compile(
    r"^(\S+) \S+ systemd\[1\]: Starting (?P<unit>\S+?)(?: - |\.\.\.|\s*$)", re.M)

_BOOT_ROW = re.compile(
    r"^\s*(-?\d+)\s+([0-9a-f]{32})\s+"
    r"\w{3}\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+UTC\s+"
    r"\w{3}\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+UTC\s*$", re.M)

DEFAULT_SWEEP_UNIT = "sysstat-summary.service"


def _fmt_utc(t: _dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(s: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def parse_service_fires(journal_text: str,
                        unit: str = DEFAULT_SWEEP_UNIT) -> list:
    """Every instant `unit` actually STARTED, from an unfiltered `_PID=1` journal.

    Matches on `Starting <unit>`, which systemd emits for a oneshot; the
    completion is `Finished`, never `Started`, and round 400 lost 92% of its
    durations to exactly that distinction. Only the start is needed here --
    the question is whether the sweep ran at all.
    """
    out = []
    for m in _FIRE_LINE.finditer(journal_text):
        if m.group("unit") != unit:
            continue
        try:
            out.append(_fmt_utc(_parse_utc(m.group(1))))
        except ValueError:
            continue
    return sorted(set(out))


def parse_boot_table(text: str) -> list:
    """`journalctl --list-boots --no-pager` -> [{index, boot_id, first, last}].

    Only rows whose BOTH timestamps parse are returned; the capture file also
    holds `### DISK` and `### CONF` sections appended after the table, and a
    loose parser would happily read those as boots.
    """
    out = []
    for m in _BOOT_ROW.finditer(text):
        idx, boot_id, first, last = m.groups()
        out.append({
            "index": int(idx),
            "boot_id": boot_id,
            "first_entry_utc": _fmt_utc(_parse_utc(first.replace(" ", "T", 1) + "Z")),
            "last_entry_utc": _fmt_utc(_parse_utc(last.replace(" ", "T", 1) + "Z")),
        })
    return sorted(out, key=lambda b: b["first_entry_utc"])


def scheduled_fires(anchor_utc: str, lo_utc: str, hi_utc: str,
                    period_days: int = 1) -> list:
    """Every lattice point `anchor + k*period` inside [lo, hi], k any integer.

    `anchor` is ONE observed or announced fire, not a hardcoded 00:07, for the
    same reason `_next_sweep_at_or_after` takes one: a box whose timer moves
    must not silently keep the old answer.
    """
    anchor, lo, hi = _parse_utc(anchor_utc), _parse_utc(lo_utc), _parse_utc(hi_utc)
    step = _dt.timedelta(days=period_days)
    k0 = math.ceil((lo - anchor) / step)
    out, t = [], anchor + k0 * step
    while t <= hi:
        out.append(_fmt_utc(t))
        t += step
    return out


def _covering_boot_gap(fire_utc: str, boots: list):
    """The [last_entry, first_entry] window between two boots containing `fire`.

    A fire inside such a gap happened while the box was, at best, not logging
    -- and this box logs continuously while awake. Returns None when the fire
    falls inside a boot rather than between two.
    """
    f = _parse_utc(fire_utc)
    for earlier, later in zip(boots, boots[1:]):
        if _parse_utc(earlier["last_entry_utc"]) < f < _parse_utc(later["first_entry_utc"]):
            return {"after_boot": earlier["index"], "before_boot": later["index"],
                    "down_from_utc": earlier["last_entry_utc"],
                    "down_to_utc": later["first_entry_utc"]}
    return None


def sweep_history(journal_text: str, boots_text: str, anchor_utc: str,
                  unit: str = DEFAULT_SWEEP_UNIT, period_days: int = 1,
                  tolerance_s: int = 600) -> dict:
    """Scheduled vs observed fires of `unit`, over the journal's own window.

    The window is the journal's first and last timestamp, so the answer is
    scoped to what the capture can actually witness. A scheduled fire is
    matched to an observed one within `tolerance_s` -- systemd's own start
    latency on this box ran 1-21 s over the seven observed fires, and
    `RandomizedDelaySec` would widen it -- and an unmatched scheduled fire is
    a fire that did not run.
    """
    fires = parse_service_fires(journal_text, unit)
    boots = parse_boot_table(boots_text)
    stamps = [m.group(1) for m in _FIRE_LINE.finditer(journal_text)]
    all_ts = sorted(_fmt_utc(_parse_utc(s)) for s in _journal_timestamps(journal_text))
    if not all_ts:
        raise CaptureManifestError(
            "no parseable timestamps in the journal; the sweep history cannot "
            "be derived and must NOT be assumed")
    lo, hi = all_ts[0], all_ts[-1]
    sched = scheduled_fires(anchor_utc, lo, hi, period_days)
    obs = [_parse_utc(f) for f in fires]
    ran, missed = [], []
    for s in sched:
        sd = _parse_utc(s)
        hit = [o for o in obs if abs((o - sd).total_seconds()) <= tolerance_s]
        if hit:
            ran.append({"scheduled_utc": s, "observed_utc": _fmt_utc(hit[0]),
                        "latency_s": round((hit[0] - sd).total_seconds(), 1)})
        else:
            missed.append({"scheduled_utc": s,
                           "boot_gap": _covering_boot_gap(s, boots)})
    return {
        "unit": unit,
        "window_utc": [lo, hi],
        "anchor_utc": anchor_utc,
        "period_days": period_days,
        "n_scheduled": len(sched),
        "n_ran": len(ran),
        "n_missed": len(missed),
        "ran": ran,
        "missed": missed,
        "observed_unmatched": [f for f in fires
                               if not any(r["observed_utc"] == f for r in ran)],
        "boots": boots,
    }


def _journal_timestamps(journal_text: str, limit_probe: int = 4000) -> list:
    """First and last parseable `-o short-iso` stamps, without parsing 1 MB.

    Reads inward from both ends. `journal-pid1-full.txt` is a megabyte and the
    only thing needed from it here is its span; parsing every line to learn two
    values is the sort of cost that quietly makes a health check unaffordable.
    """
    lines = journal_text.splitlines()
    out = []
    for seq in (lines[:limit_probe], lines[-limit_probe:] if lines else []):
        for line in seq:
            head = line.split(" ", 1)[0]
            try:
                out.append(_parse_utc(head))
            except ValueError:
                continue
    return out


def persistence_verdict(history: dict, catchup_window_s: int = 3600) -> dict:
    """Does a fire missed during an outage get caught up at the next boot?

    That is `Persistent=` in `sysstat-summary.timer`, and it is the single bit
    that decides whether an outage SAVES a day file or merely delays its
    death. Derived from the box's own behaviour rather than read from a unit
    file the capture never took.

    Fails closed in the honest direction: `"unknown"` unless at least one
    scheduled fire was missed inside a boot gap AND the box came back up
    inside the journal window, because with no missed fire there is no
    experiment and asserting either answer would be inventing one.
    """
    trials, caught = [], 0
    # Round 448, found by its own negative control. This read `history["ran"]`
    # first, which is the fires MATCHED to a scheduled slot -- and a catch-up
    # run is by construction NOT at its scheduled slot, so the one event the
    # verdict exists to detect was the one event excluded from its evidence.
    # The verdict could only ever come back `False`. Every observed fire
    # counts here, matched or not.
    observed = sorted(
        [_parse_utc(r["observed_utc"]) for r in history["ran"]]
        + [_parse_utc(f) for f in history["observed_unmatched"]])
    for m in history["missed"]:
        gap = m.get("boot_gap")
        if not gap:
            continue
        back = _parse_utc(gap["down_to_utc"])
        window_end = back + _dt.timedelta(seconds=catchup_window_s)
        hits = [o for o in observed if back <= o <= window_end]
        if hits:
            caught += 1
        trials.append({
            "missed_utc": m["scheduled_utc"],
            "box_back_utc": gap["down_to_utc"],
            "catchup_deadline_utc": _fmt_utc(window_end),
            "caught_up": bool(hits),
            "caught_up_at_utc": _fmt_utc(hits[0]) if hits else None,
        })
    if not trials:
        return {"persistent": "unknown", "n_trials": 0, "n_caught_up": 0,
                "trials": [],
                "why": ("no scheduled fire was missed inside a boot gap in this "
                        "window, so the box never ran the experiment")}
    return {
        "persistent": caught > 0,
        "n_trials": len(trials),
        "n_caught_up": caught,
        "trials": trials,
        "why": ("%d of %d fires missed during an outage were re-run within %d s "
                "of the box coming back" % (caught, len(trials), catchup_window_s)),
    }


def fires_lost_to_outage(anchor_utc: str, down_from_utc: str, down_to_utc: str,
                         period_days: int = 1) -> list:
    """Scheduled fires inside a known outage -- the input to `skipped_fires`.

    Half-open on the left and closed on the right is deliberate: a fire at the
    exact instant the box was last seen alive is not evidence of a miss, and a
    fire at the instant it came back is (the box was still down a moment
    before, and systemd's own start latency is a second or more).
    """
    out = []
    for f in scheduled_fires(anchor_utc, down_from_utc, down_to_utc, period_days):
        if _parse_utc(down_from_utc) < _parse_utc(f) <= _parse_utc(down_to_utc):
            out.append(f)
    return out


# The entry-point guard lives at the very END of the file, not after `main()`.
# Round 424 appended its helpers below `main()` and the CLI raised
# `NameError: parse_sysstat_ls` on the first run: module-level statements
# execute in file order, so a guard placed mid-file runs `main()` before the
# rest of the module exists. It is a one-line fix and a five-minute bug, and
# it only appears once somebody adds code after the guard.
if __name__ == "__main__":
    raise SystemExit(main())
