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
import hashlib
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import curecheck as C                                        # noqa: E402

CENSUS_NAMES = C.field_census_names()


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


# --------------------------------------------------------------------------
# Round 410 (language C) — one helper, two predicates, one home.
#
# Round 409 left this behind as its next-steps item 1: the corpus had THREE
# guards in three files. `curecheck.field_corpus_absent` asked "is this the
# tree the gateway writes into?"; `_corpus_unchanged()`, duplicated verbatim
# in `test_v33.py` and `test_v34.py`, asked "has the gateway rewritten
# anything?". Two genuinely different questions, both worth asking — and the
# second one answered ABSENT and CHANGED with the same skip and the same
# sentence, so in a worktree it said `field corpus moved: missing: X`, which
# is true and misleading.
#
# The copies are gone. What is pinned below is not that they are gone (a
# diff shows that) but the two facts that made removing them worth a round:
# the three states now get three answers, and the state the old helper got
# WRONG is re-falsified here on every fast tier rather than in a scratch
# directory that got thrown away.
# --------------------------------------------------------------------------

def _old_corpus_unchanged(root, census_path):
    """`test_v33.py`'s round-395 helper, VERBATIM apart from taking its two
    paths as arguments instead of reading module globals.

    Round 409's next-steps item 4 named the gap this closes: that round
    proved its pins red against the old code by reconstructing it in `/tmp`
    and throwing it away, so "nothing re-runs the falsification". A copy of
    the defective code, kept next to the test that shows what it got wrong,
    costs nine lines and re-executes the proof forever.
    """
    census = json.load(open(census_path, encoding="utf-8"))
    for name, want in census["file_md5"].items():
        path = os.path.join(root, "examples", os.path.basename(name))
        if not os.path.exists(path):
            return "missing: %s" % name
        got = hashlib.md5(open(path, "rb").read()).hexdigest()
        if got != want:
            return "changed: %s" % name
    return None


def _census_root(tmp_path, name):
    """A tree whose `examples/` holds the census's files with the census's
    OWN bytes, plus a census file that describes them.

    `_fake_root` above writes `let x = 1` into every file and is compared
    against the real census, so every file there reads as `changed`. The md5
    guard needs a tree where nothing has changed, so this one writes a census
    of what it wrote.
    """
    root = str(tmp_path / name)
    ex = os.path.join(root, "examples")
    os.makedirs(ex)
    md5 = {}
    for i, n in enumerate(CENSUS_NAMES):
        body = ("let x = %d\n" % i).encode()
        with open(os.path.join(ex, n), "wb") as f:
            f.write(body)
        md5["examples/" + n] = hashlib.md5(body).hexdigest()
    census = os.path.join(root, "field-names.json")
    with open(census, "w", encoding="utf-8") as f:
        json.dump({"round": 384, "n_files": len(md5), "file_md5": md5}, f)
    return root, census


def _skip_reason_against(root, census_path, monkeypatch):
    """`field_corpus_skip_reason` with the census file redirected."""
    monkeypatch.setattr(C, "FIELD_CENSUS", census_path)
    return C.field_corpus_skip_reason(root)


def test_the_corpus_states_get_different_answers(
        tmp_path, monkeypatch):
    root, census = _census_root(tmp_path, "three")

    # 1. all present, all as frozen -> run.
    assert _skip_reason_against(root, census, monkeypatch) is None

    # 2. one rewritten -> skip, and the reason says REWRITTEN and names it.
    victim = os.path.join(root, "examples", CENSUS_NAMES[0])
    open(victim, "wb").write(b"let x = 999\n")
    reason = _skip_reason_against(root, census, monkeypatch)
    assert reason is not None and "REWRITTEN" in reason
    assert CENSUS_NAMES[0] in reason
    assert C.field_corpus_changed(root) == CENSUS_NAMES[0]

    # 3. none present at all -> skip, and the reason is the OTHER one.
    for n in CENSUS_NAMES:
        os.remove(os.path.join(root, "examples", n))
    reason = _skip_reason_against(root, census, monkeypatch)
    assert reason == C.FIELD_CORPUS_ABSENT_REASON
    assert "REWRITTEN" not in reason


def test_the_old_helper_skipped_the_one_state_that_must_stay_red(
        tmp_path, monkeypatch):
    """THE falsification, re-run rather than described.

    Thirteen of fourteen present: the gateway deleted a program. That is the
    single loudest thing a corpus measurement can discover, and the old
    helper answered it with a SKIP whose sentence said the corpus had moved.
    The new one returns None — the seven tests behind it RUN, and go red.
    """
    root, census = _census_root(tmp_path, "drift")
    gone = CENSUS_NAMES[0]
    os.remove(os.path.join(root, "examples", gone))

    old = _old_corpus_unchanged(root, census)
    assert old == "missing: examples/%s" % gone       # old: skip
    assert "moved" not in old                          # ... under this reason:
    assert ("field corpus moved: %s" % old).startswith("field corpus moved")

    assert _skip_reason_against(root, census, monkeypatch) is None, (
        "13 of 14 is drift and drift must stay RED")
    assert C.field_corpus_absent(root) is False
    assert C.field_corpus_changed(root) is None, (
        "an absent file is not a rewritten one")
    assert C.field_corpus_drift(root)[1] == [gone]


def test_the_old_helper_also_misdescribed_a_fresh_checkout(
        tmp_path, monkeypatch):
    """The loud half of the same conflation, and the one every `git worktree`
    hit: nothing had moved, nothing had been rewritten, and seven tests said
    `field corpus moved`."""
    root, census = _census_root(tmp_path, "fresh")
    for n in CENSUS_NAMES:
        os.remove(os.path.join(root, "examples", n))

    old = _old_corpus_unchanged(root, census)
    assert old is not None and old.startswith("missing: ")

    new = _skip_reason_against(root, census, monkeypatch)
    assert new == C.FIELD_CORPUS_ABSENT_REASON
    assert ".gitignore" in new and "not a regression" in new


def test_a_rewritten_corpus_does_not_hide_a_missing_one(tmp_path, monkeypatch):
    """THE FOURTH STATE, and this test is why there is one.

    `field_corpus_skip_reason` was written with three states — absent,
    rewritten, drift — as if they partitioned. They do not: a gateway that
    reorganises its programs deletes one and rewrites another in the same
    breath, and the first draft answered that with the REWRITE's skip. Seven
    tests would have gone quiet about a deletion, under a sentence that said
    a file had been rewritten. The deletion is the louder event because it is
    the one that can be a mistake, so drift is checked FIRST and this asserts
    the order rather than the outcome of one arm.
    """
    root, census = _census_root(tmp_path, "both")
    monkeypatch.setattr(C, "FIELD_CENSUS", census)
    os.remove(os.path.join(root, "examples", CENSUS_NAMES[0]))
    open(os.path.join(root, "examples", CENSUS_NAMES[1]), "wb").write(b"x\n")

    # both facts are true at once, and each predicate reports its own
    assert C.field_corpus_missing(root) == [CENSUS_NAMES[0]]
    assert C.field_corpus_changed(root) == CENSUS_NAMES[1]
    # ... and the decision is the drift one.
    assert C.field_corpus_skip_reason(root) is None, (
        "a rewrite must not buy a deletion a skip")


# --- the "one home" pin ----------------------------------------------------

#: Every file allowed to read round 384's census, and why. The shape is
#: `harness/tests/test_pristine_check.py::test_the_curated_corpus_rule_is_
#: duplicated_only_where_declared`'s: a copy is not forbidden, it is
#: DECLARED, so making a fourth one costs a red test that names the rule.
CENSUS_READERS = {
    "tests/test_field_corpus_selector.py":
        "the QUARANTINE. `_old_corpus_unchanged` below is round 395's helper "
        "kept verbatim so the falsification re-runs every fast tier; it "
        "parses a census because the code being falsified parsed one. It is "
        "never called on the live tree — every caller passes a tmp_path.",
    "curecheck.py":
        "the reader. `_census_md5()` is the one place the file is parsed, "
        "and `FIELD_CENSUS` the one place its path is spelled.",
    "tests/test_v32.py":
        "the census's OWN integrity test — it asserts what the file says "
        "about itself (round, n_files, the builtin set at capture), which "
        "is the one claim that cannot be routed through a helper that "
        "trusts the file.",
}


def _py_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in ("__pycache__", "research-env",
                                    ".git", "whence_lang.egg-info")]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.relpath(os.path.join(dirpath, fn), ROOT)


def test_the_census_is_parsed_in_exactly_one_place():
    """`["file_md5"]` is the subscript that reads the census's payload. Round
    410 removed three copies of the six lines around it; this is what stops a
    fourth appearing without an argument for it."""
    hits = set()
    for rel in _py_files():
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        if '["file_md5"]' in src:
            hits.add(rel)
    assert hits == set(CENSUS_READERS), (
        sorted(hits), sorted(CENSUS_READERS))


def test_no_test_file_defines_its_own_corpus_guard_any_more():
    """The name is pinned, not just the behaviour: a future round that wants
    a corpus guard should find `field_corpus_skip_reason` rather than
    re-derive one, and re-deriving one under the old name is the specific
    thing that produced three copies."""
    pat = re.compile(r"^def _corpus_unchanged\(", re.M)
    offenders = [rel for rel in _py_files()
                 if rel.startswith("tests" + os.sep)
                 and pat.search(open(os.path.join(ROOT, rel),
                                     encoding="utf-8").read())]
    # An anchored `^def` and not a substring: the first draft of this test
    # searched for the bare text and MATCHED ITSELF, so it would have passed
    # with the quarantine copy deleted. A pin whose subject is a string is a
    # pin the pin can satisfy.
    assert offenders == [], offenders
    assert _old_corpus_unchanged.__doc__ and "VERBATIM" in \
        _old_corpus_unchanged.__doc__, "the quarantine copy is what makes " \
        "this rule checkable; it must still be here"


def test_the_two_reasons_cannot_be_mistaken_for_each_other():
    """Both are shown to a human reading a skip line, and the whole defect
    was that one sentence served for two facts. They are required to share
    no distinguishing claim."""
    absent, changed = C.FIELD_CORPUS_ABSENT_REASON, C.FIELD_CORPUS_CHANGED_REASON
    assert "%s" in changed and "%s" not in absent
    assert "REWRITTEN" in changed and "REWRITTEN" not in absent
    assert ".gitignore" in absent and ".gitignore" not in changed
    assert "no subject" in absent or "has no subject" in absent


def test_the_two_pinned_test_modules_use_the_shared_guard():
    """`test_v33.py` and `test_v34.py` are the two files the copies lived in.
    Their `corpus_pin` must come from `curecheck`, and — the part a grep for
    the call would miss — it must be the SAME object in both, so a future
    change to the guard cannot reach one file and not the other."""
    import tests.test_v33 as t33
    import tests.test_v34 as t34
    assert t33._CORPUS_SKIP == t34._CORPUS_SKIP
    for mod in (t33, t34):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "C.field_corpus_skip_reason()" in src, mod.__file__
        assert "hashlib.md5" not in src, mod.__file__
