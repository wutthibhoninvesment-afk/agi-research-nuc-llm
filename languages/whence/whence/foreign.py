"""The one table of names Whence does not have, and what to write instead.

v0.33 (round 386), decision 42. Round 384 built this table inside
`interp.py` because the only reader it had was the unbound-name miss. Round
386 measured the field corpus a second way --- following each parse error's
named cure rather than counting the cures --- and the measurement found the
table's knowledge sitting where the parser could not reach it:

    nano_reasoner.lang:35    if risk_status == "HIGH_RISK" then
      said   expected '{', got 'then' (blocks are always braced: ...)
      while  _FOREIGN_NAMES["then"] already read
             "an `if` needs no `then`: `if c { a } else { b }`"

    whenceguard_auditor.lang:19   for d in approved_departments {
      said   two statements on one line (two names in a row: ... a call is
             `f(x)` and text must be quoted)
      while  _FOREIGN_NAMES["for"] already read
             "Whence has no loops; iterate with `map`/`filter`/`fold` or
             recursion"

Both messages are true. Neither names the word the author actually wrote,
and the juxtaposition one advises an edit (`for(d)`, or `"for d"`) that is
wrong for a `for` loop in both of its branches. The sentence that WAS right
existed, in this repo, one module away.

The table lives here, and not in `interp.py`, because `interp.py` imports
`parser.py` --- so `parser.py` cannot import `interp.py`, and a table the
parser can read has to sit under both. That is a fact about the import
graph rather than a preference, which is what makes this the right shape
and not just a tidier one: the alternative is a second copy of thirteen
sentences, and round 343's whole finding was that the second copy of a
literal is where the drift starts. `interp._FOREIGN_NAMES` is an alias for
`FOREIGN_NAMES` and stays one, so round 384's `test_v32.py` --- the entry
rule, the frozen census, the sentence shape --- keeps testing the live
table with no edit.

THE ENTRY RULE (decision 41, unchanged, and this module does not widen it).
A name enters only if:
  (a) the FROZEN field census `state/whence/round-384/field-names.json`
      attests it --- the count is in the comment; or
  (b) a numbered SPEC decision rejects the construct it names.
And the sentence must say what to write in Whence instead. There is no
nearest-name rule, no edit distance and no guessing; round 384 built the
distance rule first and deleted it, and its reasons are still in
`interp.py` above the alias.
"""

# Group (c) is round 386's only addition to the table's membership, and it
# is made under rule (a) with no change to the rule. `zero_point_zero` is
# the SECOND most attested unbound identifier in round 384's frozen census
# --- 11 occurrences across 5 of the 14 field programs, against `println`'s
# 34 --- and round 384 entered the first, the third, the fourth, the fifth
# and the sixth while stepping over the second. It was not an oversight
# about attestation: `zero_point_zero` is not a foreign KEYWORD, it is a
# number spelled in words, so it did not look like the rest of the table.
# It meets the written rule exactly, and the sentence it needs ("write the
# literal `0.0`") is as determinate as any other here.
#
# What is deliberately NOT built: a decoder that turns any English number
# phrase into a literal. That would be a PATTERN rule --- the exact shape
# round 384 rejected when it deleted edit distance --- and it would answer
# for names no census has seen. Two attested entries are two attested
# entries.
FOREIGN_NAMES = {
    # (a) attested in the field corpus --- count in the comment
    "println": "Whence has no `println`; `print` already ends the line",  # 34
    "catch": "Whence has no `catch`; recover with `risky rescue fallback`",  # 6
    "Miss": "Whence's `miss` is lower case: `miss <reason>`",              # 6
    "return": "Whence has no `return`; a block's value is its last "
              "expression",                                                # 4
    "for": "Whence has no loops; iterate with `map`/`filter`/`fold` or "
           "recursion",                                                    # 2
    "then": "an `if` needs no `then`: `if c { a } else { b }`",            # 1
    # (b) a construct SPEC decision 2 or 3 names as deliberately absent
    "while": "Whence has no loops; iterate with `map`/`filter`/`fold` or "
             "recursion",
    "try": "Whence has no `try`; recover with `risky rescue fallback`",
    "throw": "Whence has no `throw`; a failure is a value --- write "
             "`miss <reason>`",
    "raise": "Whence has no `raise`; a failure is a value --- write "
             "`miss <reason>`",
    "null": "Whence has no null; a missing value is `miss <reason>`",
    "nil": "Whence has no nil; a missing value is `miss <reason>`",
    "None": "Whence has no None; a missing value is `miss <reason>`",
    # (c) a value the field corpus spells out in words --- attested, and
    #     entered under rule (a) exactly as the six above are
    "zero_point_zero": "Whence has no spelled-out numbers; write the "
                       "literal `0.0`",                                    # 11
    "one_hundred": "Whence has no spelled-out numbers; write the "
                   "literal `100`",                                        # 2
}

#: v0.33: the clause `miss <bare unbound name>` gets instead of a foreign
#: one. Round 384's next-step 1. `miss DEPT_NOT_APPROVED` reported `unbound
#: name 'DEPT_NOT_APPROVED'` and the author's atom went no further --- the
#: reason a `miss` was written at all was the one thing the miss did not
#: say. Decision 41's own clause covers it: a miss reason is a string.
#:
#: It REPLACES the foreign clause rather than joining it, and only in this
#: position. `miss null` would otherwise read "Whence has no null; a
#: missing value is `miss <reason>`" --- advice to write the thing the
#: author is already writing. Position beats vocabulary here because the
#: position is the more specific fact. Nothing in the field corpus is both
#: (all seven `miss <name>` sites are custom atoms), so this is a rule
#: chosen for a corner rather than measured in one, and it is pinned by a
#: test rather than left for a future round to rediscover.
MISS_REASON_HINT = "a miss reason is a string: write `miss \"%s\"`"


def name_hint(name):
    """The parenthesised clause for `name`, or `""`. One reader's view."""
    sentence = FOREIGN_NAMES.get(name)
    return " (%s)" % sentence if sentence is not None else ""


def bound_anywhere(tokens):
    """Every NAME the token stream BINDS: `let x`, `fn f`, and parameters.

    The parser's suppression set (decision 42). A foreign-word clause is
    correct only about a name the program does not define, and this repo's
    own examples define one: `meta.lang` and `self_eval.lang` both write
    `let then = parse_block(...)`, because an interpreter written in Whence
    names the then-branch of an `if` node `then`. Three bindings across two
    tracked files --- measured, not imagined, and the measurement is why
    this function exists at all. Without it decision 42 would have put
    "an `if` needs no `then`" on a parse error in the language's own
    self-interpreter.

    Deliberately a TOKEN scan and deliberately whole-file:

      - token, not AST, because the whole point is to run on a file that
        does NOT parse. An AST is exactly the thing unavailable here.
      - whole-file, not scope-accurate, because the cost of the two errors
        is not symmetric. Over-suppressing loses a hint on a program that
        still gets a true, if less specific, message; under-suppressing
        prints advice that is WRONG about the reader's own code. Decision
        32's standing rule is that the cure is silent unless computed, and
        silence is the safe side here.
      - `fn NAME (` and `fn (` both reached: the head name (when present)
        and every NAME inside the parameter list.

    It over-approximates in one known way --- a NAME inside ANY parenthesis
    that follows a `fn` head is counted, so `fn f(x) { g(then) }` would
    suppress `then`. The over-approximation only ever costs a hint, never
    adds a wrong one, and `test_v33.py` pins the direction rather than the
    exact set.
    """
    bound = set()
    n = len(tokens)
    i = 0
    while i < n:
        t = tokens[i]
        if t.type == "KW" and t.value in ("let", "fn"):
            j = i + 1
            if j < n and tokens[j].type == "NAME":
                bound.add(tokens[j].value)
                j += 1
            if t.value == "fn" and j < n and tokens[j].type == "(":
                depth = 0
                while j < n:
                    if tokens[j].type == "(":
                        depth += 1
                    elif tokens[j].type == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    elif tokens[j].type == "NAME":
                        bound.add(tokens[j].value)
                    j += 1
            i = j
            continue
        i += 1
    return bound
