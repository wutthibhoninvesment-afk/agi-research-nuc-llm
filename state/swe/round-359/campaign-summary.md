# Round 359 — `param_erasure` campaign results

Two 2500-program campaigns, identical plan
(`[(359, sr=0.5, 1000), (7, 0.5, 500), (11, 0.9, 500), (13, 0.1, 500)]`),
run before and after the `_shadowed_shape_stmt` LATE placement landed.

| bucket | before (`campaign-param-erasure.json`) | after (`campaign-param-erasure-late.json`) |
|---|---|---|
| programs | 2500 | 2500 |
| seconds | 109.6 | 116.9 |
| no parameter contracts | 1333 | 1337 |
| **compared, agreed** | **791** | **788** |
| exempt, unused | 101 | 53 |
| **exempt, used** | **47** | **93** |
| every binding provenance-tainted | 8 | 8 |
| parse_error | 209 | 209 |
| timeout | 11 | 12 |
| **mismatch** | **0** | **0** |

## What the exempt-and-used programs were actually diverging on

| cause | before | after |
|---|---|---|
| v0.22 argument-order clause ONLY (both forms resolved the spec to the same value) | **47 / 47** | 27 / 93 |
| the spec resolved differently — different miss TEXT | 0 | 44 / 93 |
| the spec resolved differently — different VALUE (v0.19 succeeds, the erased form misses) | 0 | 22 / 93 |

Round 347 wrote the exemption for the defining-env/calling-env question
(round 342 §7). Before the late placement, the corpus could not reach that
question at all: `_shadowed_shape_stmt` always emitted the shadowing `let`
BEFORE the annotated fn, so both forms saw the shadow. The exemption was
correct, load-bearing, and load-bearing for a different reason than the one
it was written for — which is only visible because the oracle MEASURES its
exemptions instead of returning early on them.
