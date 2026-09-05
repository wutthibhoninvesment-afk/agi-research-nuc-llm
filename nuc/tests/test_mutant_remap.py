"""Offline tests for nuc/mutant_remap.py (round 514, NUC-integration E).

No network, no ssh, no engine. The `TestThisTree` cases read committed
artefacts and the real subject's own history.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nuc import mutant_remap as MR  # noqa: E402

REMAP = ROOT / "state" / "nuc" / "round-514" / "mutant-remap-all87.json"
LEDGER = ROOT / "state" / "swe" / "perturbation-mutation-ledger.jsonl"

REL = "nuc/perturbation.py"

BASE = (
    "def alpha(n):\n"
    "    if n <= 0:\n"
    "        return 1\n"
    "    return n + 1\n"
)


def _ids(rep, status):
    return [r["old_id"] for r in rep["pairs"] if r["status"] == status]


# ------------------------------------------------------------------ identity

def test_an_unchanged_source_maps_every_mutant_to_itself():
    rep = MR.remap(BASE, BASE, REL)
    assert rep["by_status"] == {"matched": rep["n_requested"]}
    assert rep["n_id_changed"] == 0
    assert all(r["old_id"] == r["new_id"] for r in rep["pairs"])


def test_inserting_a_line_above_moves_every_id_without_losing_a_mutant():
    """THE CASE THIS MODULE EXISTS FOR. Round 508 added 243 lines above the
    five standing survivors of `nuc/perturbation.py`; every one of their ids
    changed, in BOTH components -- the line number and the positional `#i`."""
    moved = "import os\nx = os.getpid() + 1\n" + BASE
    rep = MR.remap(BASE, moved, REL)
    assert _ids(rep, "gone") == []
    assert rep["by_status"].get("moved", 0) == rep["n_requested"]
    for r in rep["pairs"]:
        assert r["new_line"] == r["old_line"] + 2
        assert r["new_id"] != r["old_id"]


def test_the_positional_index_moves_too_not_only_the_line():
    """A remap that only re-based line numbers would still miss: `#i` is an
    index over the WHOLE generated list, so a mutation site added anywhere
    ahead of a mutant renumbers it."""
    ahead = "y = 5 + 5\n" + BASE
    rep = MR.remap(BASE, ahead, REL)
    olds = [r["old_id"].rsplit("#", 1)[1] for r in rep["pairs"]]
    news = [r["new_id"].rsplit("#", 1)[1] for r in rep["pairs"]]
    assert olds != news


def test_a_deleted_line_reports_gone_rather_than_matching_something_else():
    """The direction that matters: a mutation whose site no longer exists must
    NOT acquire a neighbour's identity and with it a stale verdict."""
    rep = MR.remap(BASE, "def alpha(n):\n    return n + 1\n", REL)
    gone = _ids(rep, "gone")
    assert gone, rep["by_status"]
    assert any(":2:" in g or "cmp" in g for g in gone)


def test_renaming_the_enclosing_function_makes_its_mutants_gone():
    """The owner qualname is IN the key on purpose. The same arithmetic in a
    different function is a different mutation for this track's purpose: the
    verdict `moves_published_number` is about which derivation runs the line."""
    rep = MR.remap(BASE, BASE.replace("def alpha", "def beta"), REL)
    assert _ids(rep, "matched") == [] and _ids(rep, "moved") == []
    assert len(_ids(rep, "gone")) == rep["n_requested"]


# ----------------------------------------------------------------- ambiguity

DUP = (
    "def f():\n"
    "    a = 1 + 1\n"
    "    b = 1 + 1\n"
    "    return a + b\n"
)


def test_two_identical_lines_in_one_function_stay_distinguishable():
    """`a = 1 + 1` and `b = 1 + 1` produce the same content key. The ordinal
    within the key bucket keeps them apart as long as the bucket has the same
    size on both sides."""
    rep = MR.remap(DUP, DUP, REL)
    assert rep["by_status"] == {"matched": rep["n_requested"]}
    buckets = {r["n_old_with_key"] for r in rep["pairs"]}
    assert max(buckets) > 1


SAME = (
    "def g():\n"
    "    t = []\n"
    "    t.append(1 + 1)\n"
    "    t.append(1 + 1)\n"
    "    return t\n"
)


def test_a_key_bucket_that_changed_size_refuses_rather_than_guessing():
    """The honest half. `t.append(1 + 1)` twice is two mutants sharing a key
    BYTE FOR BYTE -- same op, same description, same stripped text, same
    owner. Add a third and position 1 in the old bucket is no longer position
    1 in the new one, so every pair in that bucket is AMBIGUOUS. Guessing here
    would carry a `survived` verdict onto a mutation nobody scored -- the
    direction that manufactures good news.

    Note how hard this is to trigger: the fixture needs the same statement
    repeated verbatim in the same function. That is why 0 of the 87 real
    mutants came back ambiguous, and it is a measurement, not luck."""
    grown = SAME.replace("    return t\n", "    t.append(1 + 1)\n    return t\n")
    rep = MR.remap(SAME, grown, REL)
    amb = _ids(rep, "ambiguous")
    assert amb, rep["by_status"]
    assert all(r["new_id"] is None for r in rep["pairs"]
               if r["status"] == "ambiguous")


def test_the_ambiguous_bucket_says_how_big_each_side_was():
    grown = SAME.replace("    return t\n", "    t.append(1 + 1)\n    return t\n")
    rep = MR.remap(SAME, grown, REL)
    r = next(x for x in rep["pairs"] if x["status"] == "ambiguous")
    assert r["n_new_with_key"] > r["n_old_with_key"]


def test_an_id_that_is_not_in_the_old_revision_is_named_not_dropped():
    rep = MR.remap(BASE, BASE, REL, ids=["perturbation.py:9999:cmp#0"])
    assert rep["pairs"][0]["status"] == "not_in_old_revision"
    assert rep["n_requested"] == 1


def test_only_selects_and_the_report_counts_what_was_asked():
    every = MR.remap(BASE, BASE, REL)
    one = every["pairs"][0]["old_id"]
    rep = MR.remap(BASE, BASE, REL, ids=[one])
    assert rep["n_requested"] == 1 and rep["pairs"][0]["old_id"] == one
    assert rep["n_old_mutants"] == every["n_requested"]


# -------------------------------------------------------------------- digests

def test_the_report_carries_both_digests_so_a_reader_can_check_the_ends():
    rep = MR.remap(BASE, BASE + "\n", REL)
    assert rep["old_digest"] != rep["new_digest"]
    assert len(rep["old_digest"]) == 64


def test_git_show_raises_on_a_revision_that_does_not_exist():
    with pytest.raises(MR.RemapError):
        MR.git_show(str(ROOT), "definitely-not-a-rev", REL)


# ------------------------------------------------------------------ this tree

class TestThisTree:
    """Reads committed artefacts. These go red when the tree moves."""

    def _rep(self):
        if not REMAP.exists():
            pytest.skip("round 514's remap has not been built")
        return json.loads(REMAP.read_text())

    def test_the_remap_is_from_the_ledgers_digest_to_the_subject_at_head(self):
        import hashlib
        rep = self._rep()
        head = hashlib.sha256((ROOT / REL).read_bytes()).hexdigest()
        assert rep["new_digest"] == head
        seen = {json.loads(l)["subject_digest"]
                for l in LEDGER.read_text().splitlines() if l.strip()}
        assert rep["old_digest"] in seen

    def test_every_mutant_scored_at_the_OLD_digest_was_asked_about(self):
        """SCOPED TO THE OLD DIGEST, and the scoping is the point.

        The unscoped version of this test went red the moment round 514
        re-scored the five remapped survivors: the ledger then held ids that
        exist only at HEAD, and a remap FROM the old revision cannot be asked
        about them. `subject_digest` is in the ledger's key for exactly this
        reason -- reading the file without it asks one question of two
        populations.
        """
        rep = self._rep()
        scored = {json.loads(l)["id"]
                  for l in LEDGER.read_text().splitlines() if l.strip()
                  and json.loads(l).get("subject_digest") == rep["old_digest"]}
        assert scored
        assert {r["old_id"] for r in rep["pairs"]} == scored

    def test_none_of_them_is_gone_or_ambiguous_at_head(self):
        """Round 508 moved lines and added mutation sites; it deleted none of
        the 87 scored sites. If this goes red a later round DID delete one,
        and its ledger verdict can no longer be carried at all."""
        rep = self._rep()
        assert rep["by_status"].get("gone", 0) == 0
        assert rep["by_status"].get("ambiguous", 0) == 0

    def test_almost_every_id_changed_which_is_the_whole_finding(self):
        rep = self._rep()
        assert rep["n_id_changed"] >= 80, rep["by_status"]
