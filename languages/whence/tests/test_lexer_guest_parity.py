"""Host lexer vs guest lexer, differentially — the instrument round 332's
next-steps item 1 was actually asking for (round 350, language C).

That item — "an exhaustive sweep of `whence/lexer.py`'s full history against
the guest `lex` function" — was carried unchanged for 16 rounds and round
348 said it should either be done or closed explicitly. Done, and the sweep
takes about five minutes, because `git log --follow -- whence/lexer.py` has
exactly THREE revisions:

    ee30654  Initial clean commit v3          (the whole file, never a diff)
    8d92ff9  Round 144 (language C)           `->` into TWO_CHAR_OPS/CONTINUES
    7b3afcb  Round 323 (SWE-loop D)           exponent literals

Both semantic diffs are mirrored in the guest (`two_char_ops`/`continue_ops`
carry `->`; round 332 added `exp_end`). So a history sweep covers two lines
of a two-hundred-line lexer and answers nothing about the rest, which
arrived already written in a commit that has no parent to diff against. A
diff-driven audit is structurally incapable of establishing this parity.
This file is what can: it compares what the two lexers DO.

THE CONTRACT (SPEC.md `## v0.21`)

  1. ACCEPTANCE AGREES. `tokenize(src)` raises a `LexError` if and only if
     `lex_all(src)` ends in a `bad` token. Never one without the other.
  2. ON ACCEPTANCE, THE STREAMS ARE EQUAL — kind, value and line, element
     for element, EOF included, under the normalisation in `KIND` below.
  3. ON REJECTION, THE MESSAGES ARE EQUAL, minus the position (a guest
     token has no column field). Two characters are exempt and pinned by
     `test_the_two_characters_whose_message_rendering_cannot_agree`.

Column numbers are the one thing rule 2 does not cover: guest tokens carry
`line` and no `col`, deliberately and since the guest lexer was written.

Layout:
  - table parity     — the host's eight character/keyword/operator tables
                       against the guest's own bindings, read out of a real
                       interpreter run rather than regex'd out of the file.
                       This is the check that would have caught round 144's
                       `->` if it had been added on one side only.
  - stream parity    — a hand corpus (one case per lexer branch) plus every
                       `examples/*.lang` file GIT TRACKS (round 355: not
                       every file in the directory — see `_example_files`).
  - pinned gaps      — the divergences that are real and are not bugs.

Cost control: every guest run in this file loads the ~800-line library ONCE
and lexes the whole batch in that one program, the same trick
`test_self_eval.py` uses.
"""

import glob
import os
import subprocess

import pytest

from whence.interp import Interpreter
from whence.lexer import (CONTINUE_KWS, CONTINUES, KEYWORDS, ONE_CHAR_OPS,
                          TWO_CHAR_OPS, LexError, _DIGITS, _ESCAPES,
                          _NAME_CONT, _NAME_START, tokenize)
from whence.values import Miss, Record, WList

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
MARKER = "# ==== SELF-TESTS"

# `examples/*.lang` files at or above this size go to the slow tier only.
# Measured round 350 on this host: everything below it lexes through the
# guest in under ~2.2s, `self_eval.lang` (138 KB) takes ~24s.
BIG_FILE_CHARS = 5000


def library_source():
    src = open(EXAMPLE, encoding="utf-8").read()
    assert MARKER in src
    return src.split(MARKER)[0]


def escape(s):
    """Python string -> the body of a Whence string literal.

    `\\r` is in this list because v0.21 added the `\\r` escape; before it,
    a carriage return could not be written in Whence at all, which is
    exactly why the guest lexer could not mirror the host's `\\r` skip.
    """
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))


# host `Token.type` -> guest token `.t`. Operators keep their own spelling
# as the type on the host side and are all `"op"` on the guest side, so the
# value carries the distinction for both.
KIND = {"NUMBER": "num", "STRING": "str", "NAME": "name", "KW": "kw",
        "NEWLINE": "nl", "EOF": "eof"}


class HostRejected(object):
    """A `LexError`, reduced to the part a guest token can carry."""

    __slots__ = ("message",)

    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return "HostRejected(%r)" % self.message


def host_stream(src):
    """[(kind, value, line)] on success, `HostRejected` on a lex error.

    A bare `except Exception` is deliberately NOT here. Until v0.21
    `tokenize` could raise a raw `ValueError` on `let x = ²` (see
    `whence/lexer.py`'s `_DIGITS` comment); letting that propagate as an
    error rather than catching it is the point.
    """
    try:
        toks = tokenize(src)
    except LexError as e:
        return HostRejected(str(e).split(" at line ")[0])
    return [(KIND.get(t.type, "op"), "" if t.type == "EOF" else t.value,
             t.line) for t in toks]


def _unwrap(v):
    return v.payload if hasattr(v, "payload") else v


def guest_streams(srcs):
    """Lex every source through the guest, in ONE interpreter run."""
    prog = [library_source()]
    for k, s in enumerate(srcs):
        prog.append('let __t%d = lex_all("%s")' % (k, escape(s)))
    env = Interpreter().run("\n".join(prog) + "\n")
    out = []
    for k in range(len(srcs)):
        payload = env.get("__t%d" % k).payload
        assert isinstance(payload, WList), (
            "guest lex_all returned %r for case %d, not a token list"
            % (payload, k))
        stream = []
        for item in payload:
            rec = item.payload
            assert isinstance(rec, Record), rec
            stream.append((_unwrap(rec.fields["t"]), _unwrap(rec.fields["v"]),
                           _unwrap(rec.fields["line"])))
        out.append(stream)
    return out


def compare(name, src, host, guest):
    """Assert the three contract rules for one source. Returns nothing."""
    rejected_by_guest = bool(guest) and guest[-1][0] == "bad"
    if isinstance(host, HostRejected):
        # rule 1, one direction
        assert rejected_by_guest, (
            "[%s] host rejected %r (%s) but the guest accepted it: %r"
            % (name, src, host.message, guest))
        # rule 3
        assert guest[-1][1] == host.message, (
            "[%s] %r: host says %r, guest says %r"
            % (name, src, host.message, guest[-1][1]))
        return
    # rule 1, the other direction
    assert not rejected_by_guest, (
        "[%s] guest rejected %r (%r) but the host accepted it: %r"
        % (name, src, guest[-1][1], host))
    # rule 2
    assert host == guest, _first_difference(name, src, host, guest)


def _first_difference(name, src, host, guest):
    for i, (a, b) in enumerate(zip(host, guest)):
        if a != b:
            return ("[%s] %r: token %d differs — host %r, guest %r"
                    % (name, src, i, a, b))
    return ("[%s] %r: %d host tokens vs %d guest tokens — host %r, guest %r"
            % (name, src, len(host), len(guest), host[-3:], guest[-3:]))


# --------------------------------------------------------------------------
# table parity
# --------------------------------------------------------------------------
# Round 144 added `->` to the host's `TWO_CHAR_OPS` **and** `CONTINUES`, and
# nothing in the tree would have failed if it had touched only one of them,
# or only the host and not the guest. That is the whole mechanism by which a
# lexer table drifts out of parity, and it is the one this pins.

@pytest.fixture(scope="module")
def guest_tables():
    env = Interpreter().run(library_source() + "\nlet __z = 1\n")

    def as_list(nm):
        return [e.payload for e in env.get(nm).payload]

    def as_str(nm):
        return env.get(nm).payload

    return {
        "keywords": set(as_list("keywords")),
        "two_char_ops": set(as_list("two_char_ops")),
        "one_char_ops": as_str("one_char_ops"),
        "continue_ops": set(as_list("continue_ops")),
        "continue_kws": set(as_list("continue_kws")),
        "digits": as_str("digits"),
        "name_start_chars": as_str("name_start_chars"),
        "name_cont_chars": as_str("name_cont_chars"),
    }


def test_keyword_table_parity(guest_tables):
    assert guest_tables["keywords"] == set(KEYWORDS)


def test_two_char_op_table_parity(guest_tables):
    assert guest_tables["two_char_ops"] == set(TWO_CHAR_OPS)


def test_one_char_op_table_parity(guest_tables):
    # order matters to nobody, membership to both
    assert set(guest_tables["one_char_ops"]) == set(ONE_CHAR_OPS)
    assert len(guest_tables["one_char_ops"]) == len(ONE_CHAR_OPS)


def test_continuation_table_parity(guest_tables):
    # the host keeps one set of TOKEN TYPES; the guest splits it in two
    # because its tokens are tagged `op`/`kw` rather than typed by spelling.
    assert guest_tables["continue_ops"] == set(CONTINUES)
    assert guest_tables["continue_kws"] == set(CONTINUE_KWS)


def test_character_class_parity(guest_tables):
    # v0.21 (round 350): these three were `str.isdigit()`/`isalpha()`/
    # `isalnum()` on the host — Unicode, which a guest written in Whence
    # cannot enumerate — and are now the same explicit ASCII sets the guest
    # has always had. Sets, not strings: `_NAME_START` orders lower before
    # upper, the guest builds `lower + upper + "_"`.
    assert set(guest_tables["digits"]) == set(_DIGITS)
    assert set(guest_tables["name_start_chars"]) == set(_NAME_START)
    assert set(guest_tables["name_cont_chars"]) == set(_NAME_CONT)


def test_escape_table_parity():
    # `_ESCAPES` has no guest TABLE — the guest decodes with an if-chain —
    # so this is checked behaviourally instead: every host escape must lex
    # to the same one character on both sides, and a character that is not
    # in the table must be rejected by both. `escape()` is bypassed here on
    # purpose; these literals are written out the long way so the test
    # cannot agree with itself through a shared helper.
    srcs = ['"\\%s"' % k for k in sorted(_ESCAPES)] + ['"\\q"']
    guests = guest_streams(srcs)
    for src, guest in zip(srcs, guests):
        compare("escape", src, host_stream(src), guest)
    for k, guest in zip(sorted(_ESCAPES), guests):
        assert guest[0] == ("str", _ESCAPES[k], 1), (k, guest[0])
    assert guests[-1][-1] == ("bad", "bad escape '\\q'", 1)


# --------------------------------------------------------------------------
# stream parity — the hand corpus
# --------------------------------------------------------------------------
# One case per branch of `tokenize`, plus the cases that motivated v0.21.
# `\r` appears as a real carriage return in the Python source here; it
# reaches the guest as the `\r` escape v0.21 added (see `escape`).

CORPUS = [
    # comments
    ("comment-whole-line", "# just a comment\nlet x = 1\n"),
    ("comment-trailing", "let x = 1  # trailing\nlet y = 2\n"),
    ("comment-at-eof-no-newline", "let x = 1\n# end"),
    ("comment-only", "# nothing else"),
    ("hash-inside-string", 'let s = "#not a comment"\n'),
    # newlines and the two suppression paths
    ("newlines-plain", "let x = 1\nlet y = 2\nlet z = 3\n"),
    ("newlines-leading", "\n\n\nlet x = 1"),
    ("newlines-consecutive", "let x = 1\n\n\n\nlet y = 2"),
    ("newline-in-parens", "let x = f(1,\n2,\n3)"),
    ("newline-in-brackets", "let xs = [1,\n2]"),
    ("newline-in-record", "let r = @{a: 1,\nb: 2}"),
    ("newline-kept-in-block", "let g = map(fn(x) { x * 2\nx }, [1])"),
    ("continue-after-binop", "let x = 1 +\n2"),
    ("continue-after-colon", 'check "label":\n  1 == 1'),
    ("continue-after-comma", "let xs = [1,\n2]"),
    ("continue-after-eq", "let x =\n1"),
    ("continue-after-arrow", "fn f(a: num) ->\nnum { a }"),
    ("continue-after-and", "let x = true and\nfalse"),
    ("continue-after-or", "let x = false or\ntrue"),
    ("continue-after-not", "let x = not\nfalse"),
    ("continue-after-rescue", "let x = (1 / 0) rescue\n0"),
    ("no-continue-after-name", "let x = a\nlet y = b"),
    ("no-continue-after-close-paren", "let x = f()\nlet y = 1"),
    # whitespace, including the v0.21 guest fix
    ("spaces-and-tabs", "let\tx\t=\t1"),
    ("cr-lf-line-endings", "let x = 1\r\nlet y = 2\r\n"),
    ("cr-alone", "let x =\r 1"),
    ("cr-then-tab", "a\t\r\nb"),
    # numbers
    ("int", "let x = 12"),
    ("zero", "let x = 0"),
    ("float", "let x = 3.5"),
    ("dot-then-name-is-field", "let x = 1.foo"),
    ("dot-then-space", "let x = 1 .5"),
    ("exponent-forms", "let x = 1e5 + 1E10 + 2.5e3 + 1e-2 + 1e+2"),
    ("bare-trailing-e", "let x = 5e"),
    ("e-starts-a-name", "let x = 5experiment"),
    ("e-then-sign-no-digit", "let x = 5e+"),
    ("exponent-overflow", "let x = 1e400"),
    ("negative-exponent-overflow", "let x = -1e400"),
    ("huge-int", "let x = " + "9" * 40),
    ("huge-float-overflow", "let x = " + "9" * 400 + ".5"),
    # names and keywords
    ("every-keyword",
     "let fn if else check rescue why snip miss true false and or not"),
    ("underscore-alone", "let _ = 1"),
    ("underscore-digit", "let _9 = 1"),
    ("keyword-prefix-is-a-name", "let letter = 1\nlet iffy = 2"),
    ("mixed-case-name", "let AbC_d1 = 1"),
    # strings
    ("string-empty", 'let s = ""'),
    ("string-all-escapes", 'let s = "a\\nb\\tc\\rd\\"e\\\\f"'),
    ("string-with-braces", 'let s = "{ } @{ } [ ] ( )"'),
    ("string-unterminated-at-eof", 'let s = "abc'),
    ("string-unterminated-by-newline", 'let s = "a\nb"'),
    ("string-bad-escape", 'let s = "a\\qb"'),
    ("string-backslash-at-eof", 'let s = "a\\'),
    # operators
    ("two-char-ops", "a == b != c <= d >= e"),
    ("arrow", "fn f() -> num { 1 }"),
    ("arrow-split-is-two-ops", "a - > b"),
    ("record-open", "let r = @{}"),
    ("one-char-ops", "a + b - c * d / e % f , g : h . i = j < k > l"),
    ("brackets-nested", "let x = [1, [2, @{k: (3)}]]"),
    ("unbalanced-close", "let x = )"),
    ("close-with-empty-stack", ")]}"),
    # whole-source shapes
    ("empty-source", ""),
    ("whitespace-only", "   \t\n  \n"),
    # rejected by both
    ("reject-dollar", "let x = $"),
    ("reject-bang-alone", "let x = !"),
    ("reject-at-alone", "let x = @"),
    ("reject-non-ascii-letter", "let caf\u00e9 = 1"),
    ("reject-non-ascii-digit", "let x = \u0663"),
    ("reject-superscript-two", "let x = \u00b2"),
    ("reject-non-ascii-in-name-tail", "let ca\u00e9fe = 1"),
]


@pytest.fixture(scope="module")
def corpus_streams():
    return guest_streams([s for _, s in CORPUS])


@pytest.mark.parametrize("index", range(len(CORPUS)))
def test_hand_corpus_streams_agree(index, corpus_streams):
    name, src = CORPUS[index]
    compare(name, src, host_stream(src), corpus_streams[index])


def test_the_corpus_exercises_both_outcomes():
    # A corpus that had drifted to all-accept or all-reject would still pass
    # every case above and prove half of what this file claims.
    outcomes = [isinstance(host_stream(s), HostRejected) for _, s in CORPUS]
    assert sum(outcomes) >= 7, "too few host-rejected cases"
    assert sum(not o for o in outcomes) >= 40, "too few host-accepted cases"


# --------------------------------------------------------------------------
# stream parity — every example file GIT TRACKS
# --------------------------------------------------------------------------

def _example_files():
    """The CURATED corpus: `examples/*.lang` as enumerated by `git ls-files`.

    Round 355 (harness A) replaced a `glob.glob` here. `examples/` is not
    exclusively ours — a separate autonomous process sharing this checkout
    (the Hermes gateway) drops its own untracked `.lang` files into it, 14 of
    them at the time of the fix — and a glob cannot tell those from the real
    corpus. The consequence was not extra coverage but a suite that could
    only pass HERE: checked out clean at the same commit, this file's two
    corpus tests failed on their own size floors (`assert 12 >= 20` and
    `assert 16 >= 26`), because round 350 set those floors from a directory
    it had not distinguished and so encoded another system's file count as a
    requirement of ours.

    This is the same rule, and the same reasoning, as
    `harness/swe/fuzz.py::list_example_files`, which predates the bug. It is
    duplicated rather than imported so the whence suite stays runnable with
    no dependency on `harness/` (round 349's `-c pytest.ini` routing has the
    same goal); `harness/pristine_check.py` is what makes the duplication
    safe, since a divergence between the two shows up there as a test that
    passes in the working tree and fails from git alone.

    Falls back to the old glob if `git` is unavailable or this is not a
    checkout at all — a corpus of 16 is better than a collection error.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "examples"], cwd=ROOT,
            capture_output=True, text=True, timeout=10, check=True)
        names = sorted(os.path.join(ROOT, line)
                       for line in out.stdout.splitlines()
                       if line.startswith("examples/") and line.endswith(".lang"))
        if names:
            return names
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return sorted(glob.glob(os.path.join(ROOT, "examples", "*.lang")))


def _small_example_files():
    return [f for f in _example_files()
            if os.path.getsize(f) < BIG_FILE_CHARS]


def _run_files(paths):
    srcs = [open(p, encoding="utf-8").read() for p in paths]
    guests = guest_streams(srcs)
    for path, src, guest in zip(paths, srcs, guests):
        host = host_stream(src)
        assert not isinstance(host, HostRejected), (
            "%s does not even lex on the host: %s" % (path, host.message))
        compare(os.path.basename(path), "<%s>" % os.path.basename(path),
                host, guest)
    return sum(len(g) for g in guests)


def test_small_example_files_lex_identically():
    # Floors are FLOORS, and both are now measured against the tracked
    # corpus alone (round 355: 12 files / 3972 tokens). They exist to catch
    # a corpus that silently emptied, so they must be reachable by a fresh
    # clone — which the old `>= 20` was not.
    paths = _small_example_files()
    assert len(paths) >= 12, paths
    total = _run_files(paths)
    assert total > 3000, total


@pytest.mark.whence_slow
def test_every_example_file_lexes_identically():
    # The superset, including `self_eval.lang` lexing its own 138 KB source.
    # Round 350 measured 30 files / ~37k tokens / 0 divergences, but 14 of
    # those 30 were another system's untracked files; round 355 re-measured
    # the curated 16 at 35188 tokens, still 0 divergences.
    paths = _example_files()
    assert len(paths) >= 16, paths
    total = _run_files(paths)
    assert total > 30000, total


def test_the_corpus_is_what_git_tracks_and_not_what_the_directory_holds():
    """The regression pin for round 355's fix, and it must FAIL LOUDLY here.

    A `glob` and a `git ls-files` agree in any clean checkout, so a test
    that only asserted "the corpus is non-empty" would pass again the moment
    somebody reverted the fix on a CI box. This asserts the discrimination
    itself: every path returned is tracked, and if the directory currently
    holds untracked `.lang` files (it does on the research host, and does
    not in a fresh clone) at least one of them is excluded.
    """
    listed = {os.path.basename(p) for p in _example_files()}
    tracked = subprocess.run(["git", "ls-files", "examples"], cwd=ROOT,
                             capture_output=True, text=True, check=True)
    tracked = {os.path.basename(l) for l in tracked.stdout.splitlines()
               if l.endswith(".lang")}
    assert listed == tracked, listed ^ tracked

    on_disk = {os.path.basename(p)
               for p in glob.glob(os.path.join(ROOT, "examples", "*.lang"))}
    extra = on_disk - tracked
    if extra:                       # true here, false in a fresh clone
        assert not (listed & extra), sorted(listed & extra)


# --------------------------------------------------------------------------
# pinned gaps — real divergences that are not bugs
# --------------------------------------------------------------------------

def test_guest_tokens_carry_no_column():
    # The oldest and largest gap, and the reason rule 2 normalises to
    # (kind, value, line). Pinned rather than fixed: nothing in the guest
    # parser reads a column, and adding one would thread a fifth field
    # through every branch of `lex` to be used by nobody.
    guest = guest_streams(["let x = 1"])[0]
    assert set(guest[0]) and len(guest[0]) == 3
    host = tokenize("let x = 1")
    assert host[1].col == 5 and host[1].line == 1


def test_the_two_characters_whose_message_rendering_cannot_agree():
    # Rule 3 holds for every character except these two, and it is not
    # fixable on the guest side: the host builds its message with Python's
    # `%r`, which switches quoting for `'` and doubles a backslash, and
    # Whence has no `repr`. Exhaustively established over printable ASCII
    # (round 350) — exactly two characters, not a sample.
    disagree = []
    for code in range(32, 127):
        ch = chr(code)
        if ch == '"':
            continue        # opens a string; both sides say "unterminated
                            # string", which is agreement, not a rendering
        try:
            tokenize(ch)
        except LexError as e:
            host = str(e).split(" at line ")[0]
            if host != "unexpected character '" + ch + "'":
                disagree.append((ch, host))
    assert [d[0] for d in disagree] == ["'", "\\"], disagree
    assert dict(disagree)["'"] == 'unexpected character "\'"'
    assert dict(disagree)["\\"] == "unexpected character '\\\\'"
    # and the guest really does say the other thing, for both
    guest = guest_streams(["'", "\\"])
    assert guest[0][-1] == ("bad", "unexpected character '''", 1)
    assert guest[1][-1] == ("bad", "unexpected character '\\'", 1)


def test_a_host_lex_error_discards_the_tokens_before_it():
    # Not a token-stream divergence but a shape difference rule 1 has to be
    # written around: `tokenize` raises, so the caller gets NOTHING, while
    # the guest returns the prefix it had already built and terminates it
    # with a `bad` token. The prefixes are therefore not comparable, which
    # is why `compare` checks only the message on the rejecting path.
    assert isinstance(host_stream("let x = $"), HostRejected)
    guest = guest_streams(["let x = $"])[0]
    assert [t[0] for t in guest] == ["kw", "name", "op", "bad"]
