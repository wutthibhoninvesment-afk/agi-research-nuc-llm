"""Round 521 (SWE-loop D) — a copy of a live tree survives a vanished file,
and the scanner that finds who makes files vanish.

The episode, in four steps, all of it in `logs/health_round_517.log`:

  1. `languages/whence/tests/test_polarity.py` wrote `_r438_suffix.lang` into
     the LIVE `languages/whence/` directory and removed it one subprocess
     later.
  2. `harness/tests/test_swe_oraclekill.py:37` copies that directory with
     `shutil.copytree` at MODULE SCOPE. The driver runs the whence and the
     harness health checks concurrently, so `os.scandir` listed the name and
     `copy2` got ENOENT.
  3. Because the copy is at module scope the raise was a COLLECTION error:
     `Interrupted: 1 error during collection`, 0 of 557 node ids collected,
     and `test_tiering.py::test_the_slow_tier_is_exactly_the_unpromoted_swe_files`
     -- which shells out to collect that directory -- went red.
  4. It had never been red before, so `harness/crosstrack-registry.json` had
     no entry, `redattrib.py audit` raised R001, and
     `test_redattrib.py::TestThisTree` x2 was red for rounds 518-521.

Every injection below is DETERMINISTIC: no sleeps, no threads, no second
process. `shutil.copytree` calls `ignore(dirpath, names)` after `os.scandir`
and before the first `copy2`, and `link_tree` calls `os.link` per file, so
both give an exact seam at which "another process deleted it" can be staged.

Note for whoever edits `_copytree_tolerating_vanished`: patching
`shutil.copy2` does NOT work, because `copytree`'s `copy_function=copy2`
default is bound when `shutil` is defined. That cost this round one refuted
prediction (P1's stated mechanism) and is recorded so it costs the next
reader nothing.
"""
import ast
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe import linkcopy as LC                                   # noqa: E402
from swe import livewrite as LW                                  # noqa: E402
from swe import mutation as M                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# staging a vanish
# ---------------------------------------------------------------------------

@pytest.fixture
def tree(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for n in ("a.txt", "b.txt", "c.txt"):
        (src / n).write_text(n)
    return str(src), str(tmp_path / "out" / "proj")


class _VanishOnIgnore(object):
    """Unlink `names` at the moment `copytree` has scanned and not copied."""

    def __init__(self, names):
        self.names = names
        self.real = shutil.ignore_patterns

    def __enter__(self):
        real = self.real
        names = self.names

        def hooked(*pats):
            match = real(*pats)

            def ignore(dirpath, entries):
                for n in names:
                    p = os.path.join(dirpath, n)
                    if os.path.exists(p):
                        os.unlink(p)
                return match(dirpath, entries)
            return ignore
        shutil.ignore_patterns = hooked
        return self

    def __exit__(self, *exc):
        shutil.ignore_patterns = self.real
        return False


def test_copytree_still_raises_without_the_guard(tree):
    """The defect itself, reproduced against the stdlib. If this ever stops
    raising, the guard below is dead code and should go."""
    src, dst = tree
    with _VanishOnIgnore(("b.txt", "c.txt")):
        with pytest.raises(shutil.Error) as ei:
            shutil.copytree(src, dst,
                            ignore=shutil.ignore_patterns(*M.COPY_IGNORE))
    errs = ei.value.args[0]
    assert len(errs) == 2 and all(len(t) == 3 for t in errs)
    assert all("No such file or directory" in t[2] for t in errs)


def test_copy_project_survives_a_file_deleted_mid_copy(tree):
    src, dst = tree
    before = len(M.VANISHED)
    with _VanishOnIgnore(("b.txt", "c.txt")):
        res = M._copy_project(src, dst)
    assert sorted(os.path.basename(p) for p in res["vanished"]) == \
        ["b.txt", "c.txt"]
    assert os.listdir(dst) == ["a.txt"], "the rest of the tree is still copied"
    assert len(M.VANISHED) == before + 2, "recorded, not swallowed"


def test_a_clean_copy_reports_no_vanish(tree):
    """The negative control: the guard must not manufacture a finding."""
    src, dst = tree
    assert M._copy_project(src, dst) == {"vanished": []}
    assert sorted(os.listdir(dst)) == ["a.txt", "b.txt", "c.txt"]


def test_a_dangling_symlink_is_not_a_vanish_and_still_raises(tmp_path):
    """ENOENT is not enough. A dangling symlink reports the same errno and
    the source path DOES still exist (`lexists`), so it is a real error and
    must keep raising -- otherwise the guard would swallow a broken tree."""
    src = tmp_path / "src"
    src.mkdir()
    os.symlink(str(src / "nothing-here"), str(src / "link"))
    with pytest.raises(shutil.Error):
        M._copy_project(str(src), str(tmp_path / "out" / "proj"))


def test_a_non_vanish_error_is_re_raised_with_the_vanishes_removed(tmp_path):
    """A mixed batch: one vanish, one genuine error. The genuine one must
    survive the filtering, and it must be the only thing left."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "gone.txt").write_text("x")
    os.symlink(str(src / "nothing-here"), str(src / "link"))
    with _VanishOnIgnore(("gone.txt",)):
        with pytest.raises(shutil.Error) as ei:
            M._copy_project(str(src), str(tmp_path / "out" / "proj"))
    remaining = ei.value.args[0]
    assert len(remaining) == 1
    assert remaining[0][0].endswith("link")


def test_link_tree_counts_the_vanish_it_already_survived(tmp_path):
    """`link_tree` never aborted -- ENOENT fell through the `copy2` fallback
    into a bare `pass`. What it did not do was SAY so, and the two copiers
    have to make the same sandbox."""
    src = tmp_path / "src"
    src.mkdir()
    for n in ("a.txt", "b.txt", "c.txt"):
        (src / n).write_text(n)
    real = os.link

    def hooked(s, d, *a, **k):
        if os.path.basename(s) != "b.txt":
            p = os.path.join(os.path.dirname(s), "b.txt")
            if os.path.exists(p):
                os.unlink(p)
        return real(s, d, *a, **k)

    os.link = hooked
    try:
        st = LC.link_tree(str(src), str(tmp_path / "out"))
    finally:
        os.link = real
    assert st["n_vanished"] == 1
    assert [os.path.basename(p) for p in st["vanished"]] == ["b.txt"]
    assert st["n_files"] == 2 and st["n_fallback"] == 0
    assert st["fallback_reasons"] == {}, (
        "a vanish is not a link FALLBACK; before round 521 it was counted as "
        "ENOENT there while n_files and n_fallback never matched")


def test_the_two_copiers_now_agree_on_a_vanished_file(tmp_path):
    """The property the whole fix is for. `swe/copyparity.py` exists because
    a byte sandbox and a linked sandbox must be the same sandbox; on this one
    input they were 'complete tree' and 'dead process'."""
    def stage(where):
        s = tmp_path / where
        s.mkdir()
        for n in ("a.txt", "b.txt"):
            (s / n).write_text(n)
        return str(s)

    byte_src = stage("bsrc")
    with _VanishOnIgnore(("b.txt",)):
        M._copy_project(byte_src, str(tmp_path / "bout" / "proj"))

    link_src = stage("lsrc")
    real = os.link

    def hooked(s, d, *a, **k):
        if os.path.basename(s) != "b.txt":
            p = os.path.join(os.path.dirname(s), "b.txt")
            if os.path.exists(p):
                os.unlink(p)
        return real(s, d, *a, **k)
    os.link = hooked
    try:
        LC.link_tree(link_src, str(tmp_path / "lout"))
    finally:
        os.link = real

    assert os.listdir(str(tmp_path / "bout" / "proj")) == ["a.txt"]
    assert os.listdir(str(tmp_path / "lout")) == ["a.txt"]


# ---------------------------------------------------------------------------
# the scanner
# ---------------------------------------------------------------------------

_PRE_FIX_POLARITY = '''
import os, subprocess, sys
def test_it():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prog = os.path.join(here, "_r438_%s.lang" % stem)
    with open(prog, "w", encoding="utf-8") as f:
        f.write(mutant)
'''

_POST_FIX_POLARITY = '''
import os, tempfile
def test_it():
    tmp = tempfile.mkdtemp(prefix="r438-")
    prog = os.path.join(tmp, "_r438_%s.lang" % stem)
    with open(prog, "w", encoding="utf-8") as f:
        f.write(mutant)
'''


def test_the_scanner_flags_the_shape_that_caused_round_517():
    f = LW.scan_source(_PRE_FIX_POLARITY, "t.py")
    assert len(f) == 1, f
    assert f[0]["scope"] == "test_it" and f[0]["call"] == "open(..., 'w')"
    assert "__file__" in f[0]["dest"], "the root is expanded, not just named"
    assert f[0]["ignored_by_copiers"] is False


def test_the_scanner_clears_the_repair():
    assert LW.scan_source(_POST_FIX_POLARITY, "t.py") == []


def test_a_grep_for_the_name_could_not_have_found_it():
    """Round 343's sentence, re-measured. The root in the real instance is a
    FUNCTION-LOCAL name derived from `__file__`; it shares no token with
    `WHENCE_ROOT`, with `AGI_ROOT`, or with the filename being written."""
    assert "WHENCE_ROOT" not in _PRE_FIX_POLARITY
    assert "ROOT" not in _PRE_FIX_POLARITY
    assert LW.scan_source(_PRE_FIX_POLARITY, "t.py")


def test_a_root_that_arrives_as_a_parameter_is_not_a_finding():
    """The scanner's first run reported three findings in
    `test_swe_mutation.py::_tiny_checkout`, whose root is a PARAMETER: a
    `root = WHENCE_ROOT` binding in an unrelated function in the same file
    had leaked into the module environment. A scanner reporting its own
    scope bug as somebody else's defect is the failure this module is about.
    """
    src = ('import os\n'
           'def other():\n'
           '    root = WHENCE_ROOT\n'
           'def helper(root):\n'
           '    with open(os.path.join(root, "x.lang"), "w") as f:\n'
           '        f.write("y")\n')
    assert LW.scan_source(src, "t.py") == []


def test_a_read_only_open_of_a_live_path_is_not_a_finding():
    src = ('import os\n'
           'def t():\n'
           '    with open(os.path.join(WHENCE_ROOT, "run.py")) as f:\n'
           '        f.read()\n')
    assert LW.scan_source(src, "t.py") == []


def test_a_write_under_a_copy_ignore_dir_is_L002_not_L001():
    """`languages/whence/tests/test_v27.py` writes its scratch program into
    `tests/__pycache__/`, which every copier in this repo skips by name. It
    is a live-tree write and it CANNOT cause the round-517 abort, and the
    report has to be able to say both."""
    src = ('import os\n'
           'def t():\n'
           '    p = os.path.join(WHENCE_ROOT, "tests", "__pycache__", "x.lang")\n'
           '    with open(p, "w") as f:\n'
           '        f.write("y")\n')
    f = LW.scan_source(src, "t.py")
    assert len(f) == 1 and f[0]["ignored_by_copiers"] is True
    assert "__pycache__" in M.COPY_IGNORE, "the ignore list is the authority"


def test_check_hides_L002_by_default_and_shows_it_on_request(tmp_path):
    src = ('import os\n'
           'def t():\n'
           '    with open(os.path.join(WHENCE_ROOT, ".git", "x"), "w") as f:\n'
           '        f.write("y")\n')
    f = LW.scan_source(src, "t.py")
    assert [x["ignored_by_copiers"] for x in f] == [True]


def test_tmp_and_unknown_roots_are_never_findings():
    src = ('import os, tempfile\n'
           'def t():\n'
           '    d = tempfile.mkdtemp()\n'
           '    with open(os.path.join(d, "x"), "w") as f:\n'
           '        f.write("y")\n'
           '    with open(os.path.join(somewhere_else, "y"), "w") as g:\n'
           '        g.write("z")\n')
    assert LW.scan_source(src, "t.py") == []


def test_the_write_call_table_covers_more_than_open():
    src = ('import os, shutil\n'
           'def t():\n'
           '    shutil.copy("a", os.path.join(WHENCE_ROOT, "b"))\n'
           '    os.rename("a", os.path.join(WHENCE_ROOT, "c"))\n'
           '    os.makedirs(os.path.join(WHENCE_ROOT, "d"))\n')
    calls = sorted(x["call"] for x in LW.scan_source(src, "t.py"))
    assert calls == ["copy()", "makedirs()", "rename()"]


# ---------------------------------------------------------------------------
# this tree
# ---------------------------------------------------------------------------

def _module_scope_copiers():
    """Files under `harness/tests/` that copy a tree during COLLECTION."""
    out = {}
    for fn in sorted(os.listdir(os.path.join(ROOT, "harness", "tests"))):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(ROOT, "harness", "tests", fn)
        with open(path, encoding="utf-8") as fh:
            try:
                tree = ast.parse(fh.read())
            except SyntaxError:
                continue
        for st in tree.body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
                continue
            for sub in ast.walk(st):
                if isinstance(sub, ast.Call):
                    f = sub.func
                    nm = f.attr if isinstance(f, ast.Attribute) else getattr(
                        f, "id", None)
                    if nm in ("_copy_project", "copytree", "MasterTree"):
                        out.setdefault(fn, []).append(sub.lineno)
    return out


def test_the_module_scope_copiers_are_the_three_round_521_measured():
    """The amplifier, pinned. A copy at module scope turns any copy failure
    into a pytest COLLECTION error, which costs the WHOLE directory rather
    than one node -- that is the difference between round 517's one red and
    a red nobody would have noticed. `own-suite` scope: only a change under
    `harness/tests/` can move this, so it cannot be opened by another track.
    A fourth entrant should read the module docstring before adding itself.
    """
    assert sorted(_module_scope_copiers()) == [
        "test_swe_oraclekill.py", "test_swe_repair.py", "test_swe_review.py"]


def test_the_scan_of_this_tree_is_well_formed_and_is_not_a_gate():
    """A MEASUREMENT, deliberately not a count. `livewrite.check()` ranges
    over `languages/whence/tests` and `skills/`, which this track does not
    own; pinning its cardinality here would manufacture exactly the
    cross-track red this round exists to explain (round 511). What is pinned
    is that every finding carries the fields a reader needs to act.
    """
    for f in LW.check(ROOT):
        assert set(f) == {"path", "lineno", "scope", "call", "dest",
                          "ignored_by_copiers"}
        assert f["lineno"] > 0 and f["path"].endswith(".py")
        assert f["ignored_by_copiers"] is False


def test_the_reviewed_set_is_exactly_what_round_521_read():
    """`REVIEWED` is a record of a human decision, so it may not grow by
    accident. Round 521 read all 15 findings of its first scan and accepted
    none into this dict: 12 are real and belong to `language(C)` and
    `harness(A)`, one was repaired (`test_polarity.py`), and two are L002,
    which `check` already filters by mechanism rather than by permission."""
    assert LW.REVIEWED == {}


def test_the_staged_mode_is_silent_on_a_commit_with_no_test_file():
    """The pre-commit shape (round 515's step 4 reasoning): green and silent
    when it has nothing to say, so it never becomes noise the author skips."""
    assert isinstance(LW.staged(ROOT), list)
