"""Round 457 (harness A). Why the slow tier's recall is a sawtooth.

The finding these tests hold open
--------------------------------
`run_slowtier_slice.sh` has run one bounded slice per round since round 439,
and `logs/driver.log` records what it bought — rounds 440 to 456, in order:

    19, 22, 25, 12, 3, 6, 3, 6, 9, 3, 3, 6, 3, 6, 9, 12, 3   (% recall)

It has never exceeded 25%, and never exceeded 12% in the regime the driver
itself created. That is not bad luck. Measured, and every drop to 3%
accounted for:

  * `checkout_digest` digests every `.py` and `.lang` file under
    `languages/whence/`, and it reads the WORKING TREE, not git. So a round
    invalidates the entire tier the moment it EDITS a whence source —
    committed or not. (Rounds 452 and 456 reset the digest with no whence
    source committed inside their own session; their edits were on disk.)
  * Of the 16 digest transitions in that window, 5 are resets. All 5 are
    language(C) rounds. All 5 language(C) rounds in the window reset it.
    Zero of the 11 non-language rounds did.
  * The rotation puts language(C) at rounds ≡ 2 and ≡ 0 (mod 6), so the
    longest run of consecutive non-language rounds is THREE.

One slice per round means at most `1 + 3 = 4` units can be conclusive at
once, against 33 units: a ceiling of 12%. The observed maximum in the
driver era is exactly 12%, reached twice (rounds 443 and 455).

Nothing here is a bug in `slowtier.py`. The state machine is fail-closed and
right: a pass measured against a checkout that has moved is not evidence
about this checkout. The gap is between what the mechanism can deliver under
this rotation and this budget, and what the line in `driver.log` is read as
meaning. These tests exist so the arithmetic is re-derived by a machine on
every fast-tier run instead of being carried as prose — round 456's own
lesson about a number that stops moving.

If one of these fails, the constraint changed; read the failure, do not
retune the assertion. See `knowledge/round-457-*.md` §3.
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "harness"))

from swe import slowtier  # noqa: E402

SLICE_SRC = os.path.join(REPO_ROOT, "harness", "run_slowtier_slice.sh")
CLAUDE_MD = os.path.join(REPO_ROOT, "CLAUDE.md")
LEDGER = os.path.join(REPO_ROOT, "state", "slow-tier-ledger.jsonl")

#: `plan()`'s own fallback for a unit with no measured cost.
DEFAULT_S = 300.0


def _default_budget_s():
    """The budget the driver actually uses, read from the script, not typed
    here — a constant copied into a test is a second source of truth."""
    body = open(SLICE_SRC).read()
    m = re.search(r'BUDGET="\$\{DRIVER_SLOWTIER_BUDGET_S:-(\d+)\}"', body)
    assert m, "the slice script's default budget is no longer parseable"
    return float(m.group(1))


def _rotation():
    """`{round mod 6: track}` parsed from CLAUDE.md's ground rule 6.

    Parsed rather than hard-coded on purpose: the ceiling below is a
    function of the rotation, so if the rotation ever changes these tests
    must recompute rather than keep asserting yesterday's number.
    """
    body = open(CLAUDE_MD).read()
    m = re.search(r"Track rotation \(round number mod 6\):(.*?)\n\s*Track D",
                  body, re.S)
    assert m, "CLAUDE.md ground rule 6's rotation line is no longer parseable"
    pairs = re.findall(r"(\d)\s*(?:->|→)\s*([A-Za-z\-]+\([A-E]\))", m.group(1))
    rot = {int(k): v for k, v in pairs}
    assert len(rot) == 6, rot
    return rot


def _longest_non_language_run(rot):
    """Longest run of consecutive rounds whose track is not language(C)."""
    resets = sorted(k for k, v in rot.items() if v.startswith("language"))
    best = 0
    for r in resets:
        run = 0
        n = (r + 1) % 6
        while n not in resets:
            run += 1
            n = (n + 1) % 6
        best = max(best, run)
    return best


def _tier_cost_s():
    """The planner's OWN estimate of covering every unit once."""
    rows = slowtier.status(ledger_path=LEDGER)["rows"]
    total = 0.0
    for r in rows:
        est = slowtier._est(r)
        total += DEFAULT_S if est is None else est
    return total, len(rows)


# ------------------------------------------------------------ the rotation --

def test_the_rotation_puts_a_tier_reset_every_second_or_fourth_round():
    """The window is three, and it comes from CLAUDE.md, not from me."""
    rot = _rotation()
    assert sorted(k for k, v in rot.items() if v.startswith("language")) == [0, 2]
    assert _longest_non_language_run(rot) == 3


def test_a_whence_source_edit_is_what_resets_the_tier():
    """The mechanism behind the correlation, asserted at the source rather
    than inferred from the log: `checkout_digest` walks the whence checkout
    for `.py`/`.lang` files. A language(C) round cannot avoid moving it."""
    assert slowtier._SOURCE_EXTS == (".py", ".lang")
    src = open(os.path.join(REPO_ROOT, "harness", "swe", "slowtier.py")).read()
    i = src.index("def checkout_digest(")
    body = src[i:src.index("\ndef ", i + 10)]
    # It walks a directory on disk. Not `git show`, not a commit.
    assert "os.walk(root)" in body, body
    assert "git" not in body, body


# ------------------------------------------------------------- the ceiling --

def test_one_slice_per_round_cannot_cover_the_tier_before_the_next_reset():
    """The arithmetic, re-derived from live data every run.

    If this fails, either the tier got much cheaper or the budget got much
    bigger, and the sawtooth is over — which is a result worth reading, not
    an assertion worth relaxing.
    """
    total, n_units = _tier_cost_s()
    budget = _default_budget_s()
    rounds_needed = total / budget
    window = 1 + _longest_non_language_run(_rotation())
    assert rounds_needed > window, (
        "the tier now fits inside the rotation's window: %.0f s / %.0f s = "
        "%.1f rounds needed vs a %d-round window — re-read "
        "knowledge/round-457-*.md §3 before deleting this test"
        % (total, budget, rounds_needed, window))
    # And the ceiling that follows from it is well under 100%.
    assert window / float(n_units) < 0.5


def test_the_recall_ceiling_is_reported_by_nothing_that_prints_recall():
    """The gap this round names and does not close.

    `slowtier status`'s summary prints `n_conclusive / n_units` and calls it
    recall; `run_slowtier_slice.sh` puts that line in `driver.log` every
    round. Neither says that the denominator is unreachable under the
    current rotation, so 3% reads as "almost nothing is covered" when the
    truthful reading is "the maximum is 12% and we are at a quarter of it".
    Pinned as an ABSENCE so that closing it breaks this test on purpose.
    """
    src = open(os.path.join(REPO_ROOT, "harness", "swe", "slowtier.py")).read()
    report = src[src.index("def report_text("):]
    report = report[:report.index("\ndef ", 10)]
    assert "ceiling" not in report.lower(), (
        "report_text now mentions a ceiling — if the ceiling is reported, "
        "delete this test and close round 457's next-step 2")


# --------------------------------------------------- the unreachable unit --

def _ledger_rows_for(unit):
    """Every ledger row whose unit id is `unit`, oldest first."""
    out = []
    with open(LEDGER) as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                if (row.get("unit") or row.get("file")) == unit:
                    out.append(row)
    return out


#: A ledger outcome that is EVIDENCE about the run. `classify` reaches
#: `fresh_pass`/`fresh_fail` from these two and from nothing else; `timeout`
#: falls through to `unknown` however fresh the digests are.
EVIDENCE_OUTCOMES = ("passed", "failed")


def test_one_unit_has_never_been_evidence_and_the_registry_says_why():
    """`test_swe_campaign.py[heavy]` has never produced EVIDENCE. The heavy
    registry's own prose says its single test "does not finish inside any
    budget this program grants a round", so 33/33 is not reachable even with
    unlimited rounds — the true ceiling is 32/33 before the rotation is
    considered at all.

    Round 461 repaired the predicate, not the claim. Round 457 wrote this as
    `"test_swe_campaign.py[heavy]" not in seen` — an ABSENCE OF ANY ROW —
    and round 459's post-round slice appended one: outcome `timeout`,
    returncode -9, 3000.12 s. The assertion went red at round 460 while
    everything it was written to protect was still true, because "never
    produced a ledger row" was a proxy for "never been evidence" and the two
    came apart the first time the unit was actually attempted. A timed-out
    row is not a pass; it is not a fail either. Assert the thing the
    docstring claims.

    The row is pinned POSITIVELY as well: if `[heavy]` ever finishes, the
    `timeout` assertion breaks on purpose and 33/33 becomes reachable.
    """
    reg = json.load(open(os.path.join(REPO_ROOT, "harness", "tier-units.json")))
    assert "test_swe_campaign.py" in reg["heavy"]
    assert "does not finish inside any budget" in reg["_comment"]
    rows = _ledger_rows_for("test_swe_campaign.py[heavy]")
    assert [r for r in rows if r.get("outcome") not in EVIDENCE_OUTCOMES] == rows, (
        "a [heavy] row now carries an evidence outcome %r — the unit finished, "
        "so 33/33 is reachable and this test and round 457's ceiling both "
        "need rewriting, not retuning"
        % [r.get("outcome") for r in rows if r.get("outcome") in EVIDENCE_OUTCOMES])
    assert all(r.get("outcome") == "timeout" for r in rows), (
        "every [heavy] row so far is a timeout; a new non-timeout, "
        "non-evidence outcome is a state nothing here has reasoned about: %r"
        % sorted({r.get("outcome") for r in rows}))
    units = {u["id"] for u in slowtier.slow_tier_units()}
    assert "test_swe_campaign.py[heavy]" in units, (
        "the unit is declared, so it counts in the denominator")
    st = slowtier.status()
    state = {r["unit"]: r["state"] for r in st["rows"]}
    assert state["test_swe_campaign.py[heavy]"] not in slowtier.CONCLUSIVE
    assert state["test_swe_campaign.py[heavy]"] not in slowtier.SCOPED_CONCLUSIVE


def test_the_light_half_of_the_split_has_a_row_and_it_is_still_not_evidence():
    """Round 455's next-steps item 4, re-derived and CORRECTED at round 461.

    It read: "`test_swe_campaign.py[light]` is still `unknown` to the
    slow-tier instrument. Recall is 9% (3 conclusive of 33)". Both halves
    have moved. `[light]` is no longer `unknown` — round 457's slice ran it
    (2026-09-02 17:03:10, outcome `timeout`, 3000.23 s) against checkout
    `88cba3aa3d246012`, which has since moved, so it classifies as
    `stale_checkout`. And recall is no longer 9%.

    What has NOT moved is the substance: the row is a timeout, so `[light]`
    has never been evidence either, and both halves of the split remain
    outside `n_conclusive`. This test pins the substance and deliberately
    does not pin the recall number, which is a sawtooth by design.
    """
    rows = _ledger_rows_for("test_swe_campaign.py[light]")
    assert rows, "round 457's slice ran it; the row is the evidence for this test"
    assert all(r.get("outcome") not in EVIDENCE_OUTCOMES for r in rows)
    st = slowtier.status()
    state = {r["unit"]: r["state"] for r in st["rows"]}
    assert state["test_swe_campaign.py[light]"] not in slowtier.CONCLUSIVE
    assert state["test_swe_campaign.py[light]"] not in slowtier.SCOPED_CONCLUSIVE
    # Neither half of the split can ever be conclusive while both time out,
    # so the ceiling round 457 derived is 31/33, not 32/33, for as long as
    # that holds. Stated here rather than in prose because prose is what
    # round 455's item 4 was.
    never = {r["unit"] for r in st["rows"]
             if r["state"] not in slowtier.CONCLUSIVE + slowtier.SCOPED_CONCLUSIVE}
    assert {"test_swe_campaign.py[light]", "test_swe_campaign.py[heavy]"} <= never
