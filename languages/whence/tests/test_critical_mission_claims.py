"""Round 444 (language C) — the two claims CLAUDE.md's CRITICAL MISSION makes
about this interpreter, executed.

`CLAUDE.md` carries a block headed `🔴 CRITICAL MISSION: PRODUCTION FIX
(Round ~350 Focus)` asserting two defects in Whence and telling every round
to prioritise them:

  1. "**Fold Logic Regression:** `fold()` returns `Miss` instead of
     calculated values when using inline lambdas or external functions.
     Needs deep code inspection in `whence/interp.py`."
  2. "**Strict Syntax Enforcement:** Parser requires explicit `{}` blocks for
     all `if/else` branches in v0.19. Document this strictly…"

The block has been re-escalated to the operator as unactionable in every
next-steps list from round ~350 to round 443 — twenty-three times — and in
all of that time **nobody ran the four lines below**. It is a claim about
this repo's own code, which makes it the one class of escalation a language
round has no excuse for deferring.

Both are answered here, and the answers differ:

  * Claim 1 is FALSE as written, and the true statement next to it is
    useful. `fold` works with an inline `fn(...) {...}` and with a named
    `fn`. It returns a miss when the ARGUMENTS ARE IN THE WRONG ORDER, and
    the miss says so by name: `fold needs a list, got 0 (arguments fit
    fold(fn, acc, xs))`. That is not a regression, it is decision 32 (an
    error that can name the fix, names it) doing its job — and it is
    exactly what two of the field-corpus programs hit
    (`expense_tracker.lang` line 20, `prod_showcase_final.lang` line 20,
    both `fold needs a list, got <fn …>`), which is the most likely place
    the block's author saw a `Miss` and read it as an interpreter fault.
  * Claim 2 asks for something that ALREADY EXISTS, twice: `SPEC.md` has a
    section `### Blocks are always braced`, and `whence/parser.py` carries
    `_BRACE_HINT` so the parse error itself names the spelling.

This file is written so that it EXPIRES CORRECTLY. It reads `CLAUDE.md` and
skips if the block is gone — deleting the block is the operator's call, and
when it happens these pins stop having a subject rather than becoming
noise."""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import curecheck as C                                        # noqa: E402
from whence.interp import Interpreter                        # noqa: E402
from whence.parser import _BRACE_HINT                        # noqa: E402

CLAUDE_MD = os.path.join(C.AGI_ROOT, "CLAUDE.md")


def _claude_md():
    if not os.path.exists(CLAUDE_MD):
        return ""
    with open(CLAUDE_MD, encoding="utf-8") as fh:
        return fh.read()


_TEXT = _claude_md()
has_block = pytest.mark.skipif(
    "CRITICAL MISSION" not in _TEXT,
    reason="CLAUDE.md's CRITICAL MISSION block is gone — the claims these "
           "tests refute have no subject any more, which is the outcome "
           "round 444 recorded as the operator's to make.")


def _run(src):
    """`Interpreter.run` takes SOURCE, not a parsed `Program` — the first
    draft of this file passed `parse(src)` and got `TypeError: object of
    type 'Program' has no len()` out of the lexer, which is its own small
    lesson about an API pinned nowhere."""
    out = []
    Interpreter(out=out.append).run(src)
    return "\n".join(out)


@has_block
def test_the_block_still_says_what_these_tests_answer():
    """A pin on the CLAIM, so a reworded block cannot leave these tests
    silently answering something nobody asserts any more."""
    assert re.search(r"Fold Logic Regression", _TEXT)
    assert re.search(r"fold\(\).{0,80}Miss", _TEXT, re.S)
    assert re.search(r"Strict Syntax Enforcement", _TEXT)


@has_block
def test_claim_1_is_false_for_an_inline_lambda():
    assert _run("let xs = [1, 2, 3, 4]\n"
                "print(str(fold(fn(acc, x) { acc + x }, 0, xs)))\n") == "10"


@has_block
def test_claim_1_is_false_for_an_external_named_function():
    assert _run("fn add(acc, x) { acc + x }\n"
                "let xs = [1, 2, 3, 4]\n"
                "print(str(fold(add, 0, xs)))\n") == "10"


@has_block
def test_what_actually_produces_the_miss_is_argument_order_and_it_says_so():
    """The true statement the block is a garbled version of. The miss is not
    silent and not generic: it names the signature that would have worked."""
    got = _run("fn add(acc, x) { acc + x }\n"
               "let xs = [1, 2, 3, 4]\n"
               "print(str(fold(add, xs, 0)))\n")
    assert "fold needs a list" in got
    assert "arguments fit fold(fn, acc, xs)" in got


@has_block
def test_the_same_miss_is_what_two_field_programs_hit():
    """Not a guess about where the block's author saw a `Miss`: the two
    field programs that RUN and drop a fold miss are re-measured here.

    Skips with the corpus, like every other corpus-derived test in this
    tree — the programs belong to a separate system."""
    reason = C.field_corpus_skip_reason()
    if reason is not None:
        pytest.skip(reason)
    for name in ("expense_tracker.lang", "prod_showcase_final.lang"):
        path = os.path.join(ROOT, "examples", name)
        proc = subprocess.run([sys.executable, "run.py", path],
                              cwd=ROOT, capture_output=True, text=True,
                              timeout=120)
        assert proc.returncode == 0, (name, proc.returncode)
        assert "fold needs a list" in proc.stdout, name
        assert "arguments fit fold(fn, acc, xs)" in proc.stdout, name


@has_block
def test_claim_2_asks_for_documentation_that_exists_in_two_places():
    with open(os.path.join(ROOT, "SPEC.md"), encoding="utf-8") as fh:
        spec = fh.read()
    assert "### Blocks are always braced" in spec
    # and the parser does not merely enforce it, it names the spelling
    assert "blocks are always braced" in _BRACE_HINT
    assert "`if c { a } else { b }`" in _BRACE_HINT
