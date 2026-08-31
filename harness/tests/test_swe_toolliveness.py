"""Round 395 (SWE-loop D) — tests for `swe.toolliveness`.

The module answers "could this command run at that commit?" by REBUILDING
and IMPORTING the package the tool would have built, so its own tests are
built the same way: a real git repository is constructed with a real
breakage in it, and the sweep has to find it. Nothing here asserts against
the agi-research repo except the three tests at the bottom, which pin the
historical claim this round published and are skipped when the shas are
unreachable.
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe import toolliveness as T          # noqa: E402


# --- a constructed history with a real ModuleNotFoundError in it ------------

REF_DIFF_LITERAL = '''"""a stand-in for bench/ref_diff.py"""
MODULES = (%s)


def main():
    print("%%d differing (file, mode) pairs" %% 0)
    note = "a literal that is not printed is not a citation pattern"
    return note
'''

REF_DIFF_DERIVED = '''"""a stand-in that derives the set from the package dir"""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = tuple(sorted(f[:-3] for f in os.listdir(os.path.join(ROOT, "whence"))
                       if f.endswith(".py")))
'''


def _git(repo, *args):
    return subprocess.check_output(["git", "-C", repo] + list(args),
                                   stderr=subprocess.STDOUT).decode()


def _write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _commit(repo, subject):
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", subject)
    return _git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    """alive -> alive -> DEAD -> (unrelated commit) -> alive, with a commit
    before the tool exists at all."""
    repo = str(tmp_path_factory.mktemp("liveness_repo"))
    _git(repo, "init", "-q")
    shas = {}
    _write(repo, "README.md", "before the tool exists\n")
    shas["pre"] = _commit(repo, "Round 10 (test): nothing to do with the tool")

    _write(repo, "languages/whence/whence/__init__.py", "")
    _write(repo, "languages/whence/whence/interp.py", "VALUE = 1\n")
    _write(repo, "languages/whence/whence/values.py", "OTHER = 2\n")
    _write(repo, "languages/whence/bench/ref_diff.py",
           REF_DIFF_LITERAL % '"__init__", "interp", "values"')
    shas["born"] = _commit(repo, "Round 11 (test): the tool arrives")

    # a module nothing imports: missing from MODULES and completely free,
    # which is what `timetravel.py` was for 280 commits of the real repo
    _write(repo, "languages/whence/whence/unused.py", "NOBODY_IMPORTS_ME = 3\n")
    shas["free"] = _commit(repo, "Round 12 (test): an unimported module")

    # the real break: interp imports a module the hand-written tuple omits
    _write(repo, "languages/whence/whence/extra.py", "E = 4\n")
    _write(repo, "languages/whence/whence/interp.py",
           "from .extra import E\nVALUE = E\n")
    shas["broke"] = _commit(repo, "Round 13 (test): the module that broke it")

    _write(repo, "README.md", "an unrelated commit while the tool is dead\n")
    shas["quiet"] = _commit(repo, "Round 14 (test): unrelated")

    _write(repo, "languages/whence/bench/ref_diff.py", REF_DIFF_DERIVED)
    shas["fixed"] = _commit(repo, "Round 15 (test): derive the module set")
    return repo, shas


def _sweep(repo, tmpdir, **kw):
    probe = T.RefDiffProbe(repo=repo)
    out = os.path.join(tmpdir, "rows.jsonl")
    T.sweep(probe, out, **kw)
    return probe, out, T.load_rows(out)


# --- commits_touching ------------------------------------------------------

def test_commits_touching_lists_only_commits_that_can_move_the_verdict(
        history):
    repo, shas = history
    got = [c["sha"] for c in T.commits_touching(T.RefDiffProbe.paths,
                                                repo=repo)]
    assert shas["pre"] not in got and shas["quiet"] not in got
    assert got == [shas["born"], shas["free"], shas["broke"], shas["fixed"]]


def test_commits_touching_reads_the_round_out_of_the_subject(history):
    repo, _ = history
    cs = T.commits_touching(T.RefDiffProbe.paths, repo=repo)
    assert [c["round"] for c in cs] == [11, 12, 13, 15]


def test_all_commits_includes_the_ones_the_probe_skips(history):
    repo, shas = history
    every = [c["sha"] for c in T.all_commits(repo=repo)]
    assert shas["pre"] in every and shas["quiet"] in every
    assert len(every) == 6


# --- the sweep: the verdict is a run, not an argument ----------------------

def test_sweep_finds_the_dead_commit_and_names_the_missing_module(
        history, tmp_path):
    repo, shas = history
    _, _, rows = _sweep(repo, str(tmp_path))
    by = {r["sha"]: r for r in rows}
    assert by[shas["born"]]["verdict"] == "alive"
    assert by[shas["free"]]["verdict"] == "alive"
    assert by[shas["broke"]]["verdict"] == "dead"
    assert "No module named 'whence_ref.extra'" in by[shas["broke"]]["reason"]
    assert by[shas["fixed"]]["verdict"] == "alive"


def test_an_unimported_module_absent_from_the_list_costs_nothing(history,
                                                                 tmp_path):
    """The reason the real bug survived so long: `unused.py` is missing from
    the tuple at `free` and the tool is still alive, because nothing imports
    it. A name missing from a hand-written list is free until it is not."""
    repo, shas = history
    probe, _, rows = _sweep(repo, str(tmp_path))
    by = {r["sha"]: r for r in rows}
    assert "unused" not in by[shas["free"]]["modules"]
    assert "unused" in probe._tree_modules(shas["free"])
    assert by[shas["free"]]["verdict"] == "alive"


def test_absent_verdict_before_the_tool_exists(history, tmp_path):
    repo, shas = history
    probe = T.RefDiffProbe(repo=repo)
    out = os.path.join(str(tmp_path), "rows.jsonl")
    T.sweep(probe, out, commits=T.all_commits(repo=repo))
    by = {r["sha"]: r for r in T.load_rows(out)}
    assert by[shas["pre"]]["verdict"] == "absent"
    assert by[shas["pre"]]["reason"] == "absent"


def test_modules_at_reads_both_the_literal_and_the_derived_spelling(history):
    repo, shas = history
    probe = T.RefDiffProbe(repo=repo)
    names, how = probe.modules_at(shas["broke"])
    assert how == "literal" and "extra" not in names
    names, how = probe.modules_at(shas["fixed"])
    assert how == "derived" and "extra" in names and "unused" in names


def test_a_module_in_the_list_but_not_in_the_tree_is_dead_too(history,
                                                              tmp_path):
    """The other direction, and the failure round 392's own fix introduced in
    the real repo: the extraction asks git for a file that revision does not
    have. `extract_head`'s `check_output` raises; the sweep records it rather
    than crashing, so one bad commit cannot end a sweep."""
    repo, shas = history
    probe = T.RefDiffProbe(repo=repo)
    verdict, reason, detail = probe.check(shas["born"], str(tmp_path))
    assert verdict == "alive"
    probe2 = T.RefDiffProbe(repo=repo)
    probe2.modules_at = lambda sha: (("__init__", "interp", "values",
                                      "never_committed"), "literal")
    verdict, reason, detail = probe2.check(shas["born"],
                                           str(tmp_path / "b"))
    assert verdict == "dead"
    assert reason == "git-show-failed:never_committed"
    assert detail["missing"] == ["never_committed"]


# --- durability of the sweep file ------------------------------------------

def test_sweep_is_resumable_and_never_double_writes_a_commit(history,
                                                             tmp_path):
    repo, shas = history
    probe = T.RefDiffProbe(repo=repo)
    out = os.path.join(str(tmp_path), "rows.jsonl")
    first = T.sweep(probe, out, commits=T.commits_touching(
        probe.paths, repo=repo)[:2])
    assert len(first) == 2
    second = T.sweep(probe, out)
    assert len(second) == 2                      # only the unseen ones
    rows = T.load_rows(out)
    assert len(rows) == 4 and len({r["sha"] for r in rows}) == 4


def test_every_row_is_on_disk_before_the_next_commit_is_probed(history,
                                                              tmp_path):
    """Round 371 lost a 12-minute sweep that wrote its JSON at the end. The
    file must be complete and parseable after each row, not after the loop."""
    repo, _ = history
    probe = T.RefDiffProbe(repo=repo)
    out = os.path.join(str(tmp_path), "rows.jsonl")
    seen = []

    real = probe.check

    def spy(sha, workdir):
        seen.append(len(T.load_rows(out)) if os.path.exists(out) else 0)
        return real(sha, workdir)

    probe.check = spy
    T.sweep(probe, out)
    assert seen == [0, 1, 2, 3]


# --- intervals -------------------------------------------------------------

def test_intervals_collapse_runs_and_expand_to_the_heads_they_covered(
        history):
    repo, shas = history
    probe = T.RefDiffProbe(repo=repo)
    rows = []
    for c in T.commits_touching(probe.paths, repo=repo):
        with tempfile.TemporaryDirectory() as d:
            v, r, det = probe.check(c["sha"], d)
        rows.append(dict(c, verdict=v, reason=r, **det))
    spans = T.intervals(rows, commits=T.all_commits(repo=repo))
    assert [s["verdict"] for s in spans] == ["alive", "dead", "alive"]
    dead = spans[1]
    assert dead["from"] == shas["broke"][:7]
    # the unrelated commit was HEAD while the tool was dead and must be
    # counted: this is what turns "one bad commit" into "two rounds exposed"
    assert dead["n_heads"] == 2
    assert dead["rounds"] == [13, 14]
    assert spans[0]["n_heads"] == 2 and spans[0]["rounds"] == [11, 12]


def test_intervals_on_an_empty_sweep_is_empty():
    assert T.intervals([], commits=[]) == []


# --- citations: the subject set must be derived, not typed -----------------

def test_output_literals_come_from_print_calls_only(tmp_path):
    # NOT the fixture's checked-out file: the fixture's LAST commit replaces
    # it with the derived spelling, which prints nothing at all. Reading the
    # working copy of a file whose history is the point is how this test
    # first went green against an empty list.
    path = str(tmp_path / "stand_in.py")
    with open(path, "w") as f:
        f.write(REF_DIFF_LITERAL % '"__init__", "interp", "values"')
    lits = T.output_literals(path)
    assert "differing (file, mode) pairs" in lits
    assert not any("not a citation pattern" in l for l in lits)


def test_output_literals_split_on_format_conversions():
    src = 'print("ran %d of %d programs in %.2fs total")\n'
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
    lits = T.output_literals(f.name, min_len=4)
    os.unlink(f.name)
    assert "of" in lits or "programs in" in lits
    assert not any("%d" in l for l in lits)


def test_the_name_pattern_is_the_stem_not_the_filename(history):
    """The first version of this used `os.path.basename(source_path)` ==
    "ref_diff.py" and silently lost four rounds that write `ref_diff` bare.
    A grep needle is a hand-written subject set too."""
    repo, _ = history
    pats = T.probe_patterns(T.RefDiffProbe(repo=repo), repo=repo)
    assert pats["name"] == ["ref_diff"]


def test_find_citations_attributes_by_filename_and_by_state_heading(tmp_path):
    repo = str(tmp_path)
    os.makedirs(os.path.join(repo, "knowledge"))
    os.makedirs(os.path.join(repo, "state"))
    with open(os.path.join(repo, "knowledge", "round-042-x.md"), "w") as f:
        f.write("we ran ref_diff and it was fine\n")
    with open(os.path.join(repo, "state", "research-state.md"), "w") as f:
        f.write("### Round 007\nsomething\n### Round 008\n"
                "0 differing (file, mode) pairs\nmore\n")
    hits = T.find_citations({"name": ["ref_diff"],
                             "output": ["differing (file, mode) pairs"]},
                            repo=repo)
    assert {(h["round"], h["kind"]) for h in hits} == {(42, "name"),
                                                       (8, "output")}


def test_citations_in_span_selects_only_rounds_inside_it():
    hits = [{"round": 12, "kind": "name"}, {"round": 14, "kind": "output"},
            {"round": 99, "kind": "name"}, {"round": None, "kind": "name"}]
    inside = T.citations_in_span(hits, {"rounds": [13, 14]})
    assert inside == [{"round": 14, "kind": "output"}]


# --- the historical claim this round published -----------------------------

REAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROKE, FIXED = "4c05cf4", "1b18b2c"


def _have(sha):
    return subprocess.run(["git", "-C", REAL, "cat-file", "-e",
                           sha + "^{commit}"],
                          capture_output=True).returncode == 0


@pytest.mark.skipif(not _have(BROKE), reason="sha unreachable")
def test_the_published_dead_commit_still_reproduces(tmp_path):
    """Round 392 published "dead for six rounds (386-391)". Round 395
    re-executed it: the first dead commit is 4c05cf4, whose subject names
    round 387, and round 386 never ran under a dead HEAD. This test is the
    claim, not a copy of it — it rebuilds and imports."""
    probe = T.RefDiffProbe()
    verdict, reason, _ = probe.check(BROKE, str(tmp_path))
    assert verdict == "dead"
    assert reason.endswith("No module named 'whence_ref.foreign'")


@pytest.mark.skipif(not _have(FIXED), reason="sha unreachable")
def test_the_published_fix_commit_still_reproduces(tmp_path):
    probe = T.RefDiffProbe()
    verdict, reason, detail = probe.check(FIXED, str(tmp_path))
    assert verdict == "alive" and reason == ""
    assert "foreign" in detail["modules"] and detail["how"] == "derived"


@pytest.mark.skipif(not _have("HEAD"), reason="no checkout")
def test_ref_diff_is_alive_at_head(tmp_path):
    """The same predicate `languages/whence/tests/test_v10.py` asserts from
    the other side of the repo. Two guards, one predicate, deliberately: the
    whence suite is what a language round runs and the harness suite is what
    a harness round runs, and the tool sits between them."""
    probe = T.RefDiffProbe()
    verdict, reason, detail = probe.check("HEAD", str(tmp_path))
    assert verdict == "alive", reason
    assert detail["how"] in ("derived", "derived-from-ref")


def test_json_rows_are_sorted_and_reloadable(history, tmp_path):
    repo, _ = history
    _, out, rows = _sweep(repo, str(tmp_path))
    with open(out) as f:
        raw = [json.loads(l) for l in f if l.strip()]
    assert raw == rows
    assert all("elapsed_s" in r and "probe" in r for r in rows)
