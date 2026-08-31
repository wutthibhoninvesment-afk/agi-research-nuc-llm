"""Round 395 (SWE-loop D) — what identifies the field corpus.

`examples/` holds two populations: the eighteen examples this project wrote,
and fourteen programs the Hermes gateway (a separate autonomous system that
shares this repo) leaves behind. Round 386 selected the second population by
UNTRACKED STATUS — `git ls-files --others` — with a good argument: a derived
set beats a hand-written one, and a program the gateway adds tomorrow is
picked up for free.

Round 393's `git add -A` sweep (commit `49969fb`) tracked all fourteen. The
selector then returned the EMPTY LIST, and four tests in `test_v33.py` and
`test_v34.py` reported `assert 0 == 10` and `KeyError: 'nano_reasoner.lang'`
— failures that name a count and a filename, and never the cause. Nobody saw
them for two rounds because a stale pin in `test_v24.py` was aborting
collection of the whole suite at the same time.

The lesson the tests below pin: **a derived subject set is only as stable as
the meaning of the artefact it is derived from.** Untracked-ness was a proxy
for "written by someone else", and the proxy changed without the fact
changing — the files are byte-identical, and `_corpus_unchanged()`'s md5
census correctly says so, which is why that guard could not catch this.

The authority is now the census itself, and round 386's live property is kept
as a REPORT (`field_corpus_drift`) rather than as the selector.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import curecheck as C                                        # noqa: E402

CENSUS_NAMES = sorted(
    os.path.basename(k) for k in
    json.load(open(C.FIELD_CENSUS, encoding="utf-8"))["file_md5"])


def _git(repo, *args):
    return subprocess.check_output(["git", "-C", repo] + list(args),
                                   stderr=subprocess.STDOUT).decode()


def _fake_root(tmp_path, extra=None, commit_all=True):
    """A git repo whose `examples/` holds the census's files, plus `extra`."""
    root = str(tmp_path)
    ex = os.path.join(root, "examples")
    os.makedirs(ex, exist_ok=True)
    for n in CENSUS_NAMES:
        with open(os.path.join(ex, n), "w") as f:
            f.write("let x = 1\n")
    _git(root, "init", "-q")
    if commit_all:
        _git(root, "add", "-A")
        _git(root, "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "-m", "the add -A sweep")
    if extra:
        with open(os.path.join(ex, extra), "w") as f:
            f.write("let y = 2\n")
    return root


#: Round 409. Three tests below read `examples/` OFF DISK, and the corpus is
#: `.gitignore`d by name — so they failed in every `git worktree` at every
#: commit, which made `harness/pristine_check.py`'s `whence-fast` verdict a
#: permanent false `git_incomplete`. `field_corpus_absent` is all-or-nothing:
#: a PARTIALLY missing corpus is drift and stays red. See its docstring.
needs_field_corpus = pytest.mark.skipif(
    C.field_corpus_absent(), reason=C.FIELD_CORPUS_ABSENT_REASON)


def test_the_census_declares_fourteen_names():
    """Checkout-independent: the census is a TRACKED json file. Kept out of
    the skipif below so that a corrupted census is still a red test in a
    fresh checkout, where the directory half has nothing to say."""
    assert len(CENSUS_NAMES) == 14


@needs_field_corpus
def test_the_census_and_the_directory_still_agree():
    got = {os.path.basename(p) for p in C.field_programs()}
    assert got == set(CENSUS_NAMES)


def test_the_selector_is_indifferent_to_git_tracking_status(tmp_path):
    """The regression. Under round 386's selector the committed arm returned
    zero; under the census both arms return fourteen."""
    committed = _fake_root(tmp_path / "committed", commit_all=True)
    untracked = _fake_root(tmp_path / "untracked", commit_all=False)

    def old_selector(root):
        proc = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "examples"],
            cwd=root, capture_output=True, text=True)
        return [n for n in proc.stdout.split("\n") if n.endswith(".lang")]

    assert old_selector(committed) == []          # what round 393 produced
    assert len(old_selector(untracked)) == 14     # what round 386 measured

    assert len(C.field_programs(committed)) == 14
    assert len(C.field_programs(untracked)) == 14


def test_absence_is_all_or_nothing_so_real_drift_still_fails(tmp_path):
    """The SAFETY property of round 409's skip, and the reason it is not a
    plain `os.path.exists` guard.

    A skip that fires whenever "some file is missing" would swallow exactly
    the event `field_corpus_drift` exists to report: the gateway deleting or
    renaming a program. So the predicate answers a different question —
    "was this checkout ever the tree the gateway writes into?" — for which
    the only honest evidence is NONE of the fourteen being present. Thirteen
    of fourteen is drift, and drift is red.
    """
    root = _fake_root(tmp_path / "full", commit_all=False)
    assert C.field_corpus_absent(root) is False

    os.remove(os.path.join(root, "examples", CENSUS_NAMES[0]))
    assert C.field_corpus_absent(root) is False, "13 of 14 must NOT skip"
    undeclared, missing = C.field_corpus_drift(root)
    assert missing == [CENSUS_NAMES[0]] and undeclared == []

    for n in CENSUS_NAMES[1:]:
        os.remove(os.path.join(root, "examples", n))
    assert C.field_corpus_absent(root) is True, "0 of 14 is a fresh checkout"


def test_the_skip_reason_names_the_cause_and_not_just_the_symptom():
    """Round 408 read these four reds as a finding and spent a paragraph
    proving they were false. The reason string is what stops the next
    reader doing that again, so it is pinned."""
    r = C.FIELD_CORPUS_ABSENT_REASON
    assert ".gitignore" in r and "round 402" in r
    assert "not a regression" in r


def test_drift_reports_a_gateway_program_the_census_does_not_name(tmp_path):
    """Round 386's live property, kept as a report. A new program from the
    gateway is named, not silently absorbed and not silently dropped."""
    root = _fake_root(tmp_path / "withnew", extra="brand_new_demo.lang")
    undeclared, missing = C.field_corpus_drift(root)
    assert undeclared == ["brand_new_demo.lang"]
    assert missing == []


def test_drift_reports_a_declared_program_that_is_gone(tmp_path):
    root = _fake_root(tmp_path / "withgap")
    os.remove(os.path.join(root, "examples", "nano_reasoner.lang"))
    undeclared, missing = C.field_corpus_drift(root)
    assert missing == ["nano_reasoner.lang"]
    assert undeclared == []


@needs_field_corpus
def test_the_live_tree_has_no_drift():
    """If this goes red the gateway has moved and the census is a decision to
    re-make; it is NOT a regression in anything this project wrote."""
    undeclared, missing = C.field_corpus_drift()
    assert (undeclared, missing) == ([], []), (undeclared, missing)


@needs_field_corpus
def test_ten_of_the_fourteen_still_fail_to_parse():
    """The number `test_v33.py` and `test_v34.py` publish, asserted here
    against the selector directly so a selector fault reads as a selector
    fault rather than as `assert 0 == 10`."""
    rows = C.survey(C.field_programs())
    assert len(rows) == 14
    assert len([r for r in rows if not r["parses"]]) == 10
