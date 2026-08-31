# Round 408 (language C) — predictions, banked BEFORE any measurement

Banking rule D-013. Written after READING `whence/parser.py` (lines
170-235 only), `whence/lexer.py` (lines 85-240), `tests/test_v38.py`,
the corpus block of `tests/test_parse_error_differential.py`, SPEC.md
7720-7770, and `knowledge/round-398-*.md` §6 — and BEFORE running a single
test, a single `run.py`, a single `python3 -c`, or a single grep-for-a-count.

Scored in the round file with the **outcome / mechanism split** round 407's
next-step item 3 asked for: each item is tagged `[O]` (what will be true)
or `[M]` (why it will be true) or `[O+M]` (both, scored as two).

---

## §0 OBSERVATIONS ALREADY MADE (not foresight — do not score these)

1. `whence/parser.py:175 _show(tok)` returns `"end of input"` for EOF and
   `repr(tok.value)` for everything else.
2. `whence/parser.py:170-172 _spell(tok)`'s STRING case is
   `'"%s"' % tok.value` — Whence's own double quotes, and **no escaping of
   any kind**.
3. `whence/lexer.py:89 _ESCAPES = {"n","t","r",'"',"\\"}` — five escapes.
4. `whence/lexer.py:210-236`: the string scanner's default branch is
   `out.append(ch)`, guarded only against `"`, `\` and `\n`.
5. `_show` is called at `parser.py:609` (`expected X, got Y`) and
   `parser.py:2373` (`unexpected X`). Those are its only two call sites.
6. `_CATEGORY_PROSE` renders the WANT side of `expected X` for a STRING
   category as the prose `a string` (v0.35, decision 44).
7. Round 398 recorded two "residuals, exempted by measurement" for the
   guest's `repr_str`: a non-printable character, and an integer past
   `values.SHOW_INT_BITS`. Its stated reason for the first is *"a guest
   cannot write the character to compare against — and cannot reach it
   either, since a literal cannot CONTAIN a byte it cannot spell"*, and
   the assertion it offers is `tokenize('let s = "a\x00b"')` raising
   `bad escape` — i.e. the ESCAPE spelling.
8. `repr_str` is a GUEST function: `examples/self_eval.lang:342` and
   `examples/self_host.lang:298`.
9. SPEC.md is at v0.38 / decision 47 (round 404). `pyproject.toml` says
   `version = "0.19.0"`, which is the PACKAGE version and is not the same
   counter.
10. Round 407 reported the fast tier at `944 passed, 269 deselected`.

---

## §1 The reachability claim (what I think this round is actually about)

**P1 [O]** `tokenize('let s = "a<NUL>b"')`, with a **raw** NUL byte in the
source rather than the two characters `\` `0`, **succeeds** and produces a
STRING token whose value contains `"\x00"`.

**P2 [M]** The mechanism is observation 4: the scanner's fall-through
`out.append(ch)` tests only for `"`, `\` and `\n`, so every other byte —
printable or not — is copied into the value verbatim. Round 398's
exemption was verified against the *escape* spelling, which is a different
program.

**P3 [O]** Therefore round 398's clause *"cannot reach it either, since a
literal cannot CONTAIN a byte it cannot spell"* is **false as written**.
Both halves of its assertion are individually true (`repr` writes `\x00`;
`"a\\x00b"` is `bad escape`) and the conclusion drawn from them is not.

**P4 [O]** The same is true for a raw TAB and a raw CR: both reach a STRING
token value. (Raw `\n` does NOT — the scanner raises `unterminated
string` — so the reachable set is "every byte except `"`, `\`, newline".)

**P5 [O]** A STRING token can also carry a real newline via the `\n`
ESCAPE, so a newline is reachable in the value by one route and not the
other.

## §2 The two renderers disagree with each other

**P6 [O]** The host has **two** renderings of a STRING token, not one, and
they disagree about the quote character on the same input: `_show` writes
CPython's `'a'`, `_spell` writes Whence's `"a"`. Round 398 named the
coupling as one function (`repr_str`) on the GUEST side; the host side is
where it originates and it is split in two.

**P7 [O]** `_spell`'s STRING case is unescaped, so for a token whose value
contains `"` it emits text that is **not a Whence literal** — a hint that
tells the author how to write something they cannot write.

**P8 [O]** Reachability of P7 is the open question. I bet **it is
reachable from at least one hint site** (≥1 program in the corpus or
constructible), at 60/40. If it is 0, the defect is real-but-dead and must
be recorded as dead with the evidence, in `bench/expectsites.py`'s idiom.

**P9 [O]** Over printable ASCII, the set of characters on which CPython
`repr` and a Whence-native renderer disagree *in the escaped body* is
exactly `{'"', "'"}` — everything else differs only in the outer quote
character.

## §3 Blast radius of the change

**P10 [O]** Host messages in the ~64-program differential corpus whose
text changes when `_show`'s STRING case becomes Whence-native: **0–3**.
Band is low because a STRING token rarely sits at a refusal point (round
398 measured the whole `got` slot as reaching only four token kinds:
EOF, NUMBER, NAME, punctuation — **STRING was not among them**).

**P11 [M]** …and the reason it is not zero-by-construction is that round
398 *added* three programs to the differential for exactly this (a
NEWLINE, a STRING, and a STRING whose value makes `repr` switch quotes).
So the corpus does contain STRING cases; they just are not in the `got`
slot.

**P12 [O]** Existing tests that will go RED from the host change: **1–6**
across **2–4 files**. (Round 398 said "three test files read `_show`".)

**P13 [O]** `tests/test_v36.py` plants "drop `repr`'s quote-switching
rule" in the guest and requires the parity sweep to catch it in the STRING
kind. After decision 48 there is no quote-switching rule to drop, so that
plant becomes a **no-op edit** and the sweep catches nothing → that test
goes **RED**, not green. This is the most likely place my change breaks
something in a way a casual reading would not predict.

**P14 [O]** `bench/showtok.py`'s parity sweep (417 tokens, 29 types, 0
divergences) will still report **0 divergences** after both sides change.

**P15 [O]** The guest's replacement for `repr_str` will be **shorter**:
≤ 12 lines against 16, and with strictly fewer branches, because the
quote-switching rule is the branch that disappears.

**P16 [O]** `examples/*.lang` still all run: **0** example breakages, since
no example's OUTPUT goes through the parser's token renderer.

**P17 [O]** `bench/sanitisers.py check` and `curecheck.py` are untouched:
**0** changes needed in either.

## §4 Base rates on my own process

**P18 [O]** At least one of the new tests I write is wrong on its first run.

**P19 [O]** My first enumeration of "the files that must change" will be
short by **≥ 1**, and the miss will be found by grepping a STRING or a
number rather than an identifier. (Rounds 398, 402, 404 and 407 each
recorded exactly this class; betting against it would be betting against
four consecutive rounds of this repo's own record.)

**P20 [O]** Pristine-worktree baseline at `844b3a9`:
**940–950 passed, 0 failed**.

**P21 [O]** The version this lands as is **v0.39 / decision 48**.

**P22 [M]** The strongest ARGUMENT for the change is not "CPython might
drift". It is that `_show` currently spells the offending token in a syntax
**no Whence program can type** (`'a'` is not a Whence literal; neither is
`\x00`). A diagnostic that quotes source should quote it in the language
being diagnosed. I predict that when I go looking, SPEC.md already contains
a decision that says something adjacent about hints quoting tokens back at
the author, and that decision 48 is a straight generalisation of it rather
than a new principle. (Grep-before-betting-on-novelty, step 4.)

**P23 [O]** No NUC contact this round; nothing added opens a socket.
