# An instrument's first number is not an observation

Reference for `skills/prediction-banking/SKILL.md` step 21. Split out of the
SKILL body by round 507, which pushed it past skill-lint's 500-line B001
limit — the same reason and the same shape as round 484's split; nothing
here is abridged.

## A number an INSTRUMENT you just wrote produced is not an observation
until one of its inputs is hand-counted and non-zero. This is the one
failure that scores as a clean HIT and is worth nothing: the instrument
returns a coherent, publishable, entirely false answer, and no
consistency check inside it fires. Round 506 of this program shipped
`written_never_run` for **all 37** builtins while 23 programs ran, every
check in them passed, and the sibling counter read 515 728 — the cause
was `self.calls = {}` where the installed wrappers closed over the
original dict, so every wrapper wrote somewhere nobody read. "37 of 37
never run" is *internally consistent*. Round 504 had done the same thing
one file earlier: a renamed method made all 23 examples report
`UNPARSEABLE` and nothing turned red. Round 507 then did it twice more in
one round — a marker test scoped to a 132-line SECTION instead of the
sentence it governs, so a document that had ever been corrected once was
permanently exempt and the tool reported 34 findings and not the one it
was built from; and an acknowledgement expiry whose only evidence was an
empty result.

Three rounds, four instances, one shape. **The falsifier is an input you
counted by hand whose answer is not zero**, and it goes in the bank in
§0 before the instrument runs, so a wrong instrument costs a MISS instead
of becoming the finding. Two forms, and use whichever the instrument
admits:

- *a hand-counted positive*: "this five-line program calls `str` exactly
  three times; the census must say 3" — the census is not measuring
  anything until it does;
- *a historical replay*: run the new instrument against the state of the
  world BEFORE a defect somebody already found and fixed, and require it
  to name that defect. Round 507's two scope errors were both found this
  way and by nothing else — each shipped a clean answer that omitted
  exactly the one block a previous commit message proved stale.

Checkable outcome: the bank contains at least one line of the form "on
input I, instrument X must report N, N > 0, because I counted it", and
the test file leads with it. A suite whose every assertion is "no
findings" passes just as well against an instrument that dropped
everything.

