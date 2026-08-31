# Round 405 — owed probe batch, pooled

```
runs pooled: round-405-runA.json, round-405-runB.json, round-405-runC.json, round-405-runD.json

case                   expect                           per-run k/n   pooled
fsd-far                filter-shares-the-defect         0/1 0/1 0/1 2/2 2/5 [0.12,0.77]
fsd-mid                filter-shares-the-defect         0/1 1/1 0/1 1/2 2/5 [0.12,0.77]
fsd-near               filter-shares-the-defect         1/1 1/1 1/1 1/2 4/5 [0.38,0.96]
fsd-neg-list           derived-subject-set              0/1 0/1 1/1 0/2 1/5 [0.04,0.62]
iar-estimated          instruments-already-running      1/1 1/1 1/1 0/2 3/5 [0.23,0.88]
iar-far                instruments-already-running      0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
iar-mid                instruments-already-running      1/1 0/1 1/1 1/2 3/5 [0.23,0.88]
iar-near               instruments-already-running      0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
iar-neg-semantics      (none: nothing may fire)         1/1 1/1 1/1 2/2 5/5 [0.57,1.00]
kwyl-far               kill-what-you-launched           1/1 1/1 0/1 1/2 3/5 [0.23,0.88]
kwyl-mid               kill-what-you-launched           1/1 1/1 1/1 1/2 4/5 [0.38,0.96]
kwyl-near              kill-what-you-launched           1/1 1/1 1/1 2/2 5/5 [0.57,1.00]
kwyl-neg-instruments   instruments-already-running      0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
rcys-far               run-the-comparison-you-suppress  0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
rcys-far2              run-the-comparison-you-suppress  0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
rcys-mid               run-the-comparison-you-suppress  0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
rcys-near              run-the-comparison-you-suppress  0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
rcys-neg-zero          zero-rate-needs-a-distance       1/1 1/1 1/1 2/2 5/5 [0.57,1.00]
rina-baseline          residency-is-not-allocation      0/1 1/1 0/1 2/2 3/5 [0.23,0.88]
rina-far               residency-is-not-allocation      0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
rina-mid               residency-is-not-allocation      1/1 1/1 0/1 2/2 4/5 [0.38,0.96]
rina-near              residency-is-not-allocation      0/1 0/1 1/1 2/2 3/5 [0.23,0.88]
rina-neg-workingset    (none: nothing may fire)         0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
rir-far                recorder-in-the-record           0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
rir-far2               recorder-in-the-record           0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
rir-mid                recorder-in-the-record           0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
rir-near               recorder-in-the-record           0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
rir-neg-audit          (none: nothing may fire)         0/1 1/1 0/1 1/2 2/5 [0.12,0.77]
sotn-far               sanitiser-outgrows-its-noise     0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
sotn-mid               sanitiser-outgrows-its-noise     1/1 0/1 1/1 1/2 3/5 [0.23,0.88]
sotn-near              sanitiser-outgrows-its-noise     0/1 0/1 1/1 0/2 1/5 [0.04,0.62]
sotn-neg-constant      would-a-constant-have-passed     1/1 1/1 1/1 2/2 5/5 [0.57,1.00]
udp-far                untested-default-path            0/1 0/1 0/1 0/2 0/5 [0.00,0.43]
udp-mid                untested-default-path            1/1 0/1 0/1 0/2 1/5 [0.04,0.62]
udp-near               untested-default-path            0/1 0/1 1/1 0/2 1/5 [0.04,0.62]
udp-neg                unrun-checker-latency            1/1 1/1 1/1 2/2 5/5 [0.57,1.00]
wchp-far               would-a-constant-have-passed     0/1 0/1 1/1 1/2 2/5 [0.12,0.77]
wchp-far2              would-a-constant-have-passed     0/1 0/1 1/1 2/2 3/5 [0.23,0.88]
wchp-mid               would-a-constant-have-passed     1/1 1/1 1/1 1/2 4/5 [0.38,0.96]
wchp-near              would-a-constant-have-passed     1/1 1/1 1/1 2/2 5/5 [0.57,1.00]
wchp-neg-filter        filter-shares-the-defect         1/1 1/1 1/1 2/2 5/5 [0.57,1.00]

skill                              k/n      runs   Wilson 95%     verdict
untested-default-path              2/15     4      [0.04, 0.38]   BROKEN
filter-shares-the-defect           13/20    4      [0.43, 0.82]   UNDECIDED
instruments-already-running        6/25     4      [0.11, 0.43]   BROKEN
residency-is-not-allocation        10/20    4      [0.30, 0.70]   UNDECIDED
run-the-comparison-you-suppress    0/20     4      [0.00, 0.16]   BROKEN
would-a-constant-have-passed       19/25    4      [0.57, 0.89]   WORKS
kill-what-you-launched             12/15    4      [0.55, 0.93]   WORKS
recorder-in-the-record             0/20     4      [0.00, 0.16]   BROKEN
sanitiser-outgrows-its-noise       4/15     4      [0.11, 0.52]   UNDECIDED

prospective run-variance over THESE four runs:
   {'msb': 0.2666666666666667, 'msw': 0.2222222222222222, 'ratio': 1.2000000000000004, 'icc': 0.14285714285714296, 'cases': 18, 'runs': 4}

  design                probes  n_eff   n_eff/probe   (at icc=0.143)
  1 x --repeats 6        6       3.500   0.5833
  3 x --repeats 2 (r393) 6       5.250   0.8750
  3x1 + 1x2 (r405)       5       4.750   0.9500
  5 x --repeats 1        5       5.000   1.0000
  6 x --repeats 1        6       6.000   1.0000
```

## Displacement, this round's four designed runs only
```
4 report(s), 21 skill(s) with any traffic

take_rate = taken / probes of OTHER skills' cases (how often it reaches across)
loss_rate = lost / its own probes

skill                              take_rate loss_rate  take  lost  abst  fals  own_n  oth_n
lazy-fill-ceiling                     0.0632      0.00    12     0     0     5      0    190
exemption-census                      0.0632      0.00    12     0     0     0      0    190
measured-exemption                    0.0316      0.00     6     0     0     0      0    190
echoed-record-vs-measurement          0.0316      0.00     6     0     0     0      0    190
copied-mirror-drift                   0.0211      0.00     4     0     0     0      0    190
bounded-not-binary-witness            0.0211      0.00     4     0     0     0      0    190
unrun-checker-latency                 0.0162      0.00     3     0     0     0      5    185
subprocess-cli-testing                0.0158      0.00     3     0     0     0      0    190
instruments-already-running           0.0121      0.76     2    19    14     0     25    165
filter-shares-the-defect              0.0118      0.35     2     7     4     0     20    170
derived-subject-set                   0.0108      0.80     2     4     2     0      5    185
citation-registry-integrity           0.0105      0.00     2     0     0     0      0    190
would-a-constant-have-passed          0.0061      0.24     1     6     4     0     25    165
run-the-comparison-you-suppress       0.0059      1.00     1    20     2     0     20    170
sampled-interval-brackets             0.0053      0.00     1     0     0     0      0    190
untested-default-path                 0.0000      0.87     0    13     5     0     15    175
sanitiser-outgrows-its-noise          0.0000      0.73     0    11     4     0     15    175
residency-is-not-allocation           0.0000      0.50     0    10     2     0     20    170
recorder-in-the-record                0.0000      1.00     0    20    16     0     20    170
kill-what-you-launched                0.0000      0.20     0     3     2     0     15    175
deleted-vs-never-written              0.0000      0.00     0     0     0     3      0    190

per victim: is there a pair to rewrite?
victim                              lost  abst   top%  top taker
recorder-in-the-record                20    16    10%  echoed-record-vs-measurement
run-the-comparison-you-suppress       20     2    60%  exemption-census
instruments-already-running           19    14    26%  lazy-fill-ceiling
untested-default-path                 13     5    31%  echoed-record-vs-measurement
sanitiser-outgrows-its-noise          11     4    36%  copied-mirror-drift
residency-is-not-allocation           10     2    70%  lazy-fill-ceiling
filter-shares-the-defect               7     4    43%  bounded-not-binary-witness
would-a-constant-have-passed           6     4    33%  derived-subject-set
derived-subject-set                    4     2    50%  citation-registry-integrity
kill-what-you-launched                 3     2    33%  instruments-already-running

113 loss(es) total; 55 (49%) had NO catalog skill fire at all; median top-taker share of a victim's losses 36%

top displacements (victim -> taker, n):
  run-the-comparison-you-suppress  -> exemption-census                 12
  residency-is-not-allocation      -> lazy-fill-ceiling                7
  run-the-comparison-you-suppress  -> measured-exemption               6
  instruments-already-running      -> lazy-fill-ceiling                5
  untested-default-path            -> echoed-record-vs-measurement     4
  sanitiser-outgrows-its-noise     -> copied-mirror-drift              4
  untested-default-path            -> subprocess-cli-testing           3
  untested-default-path            -> unrun-checker-latency            3
  filter-shares-the-defect         -> bounded-not-binary-witness       3
  derived-subject-set              -> citation-registry-integrity      2
  recorder-in-the-record           -> echoed-record-vs-measurement     2
  sanitiser-outgrows-its-noise     -> filter-shares-the-defect         2
  would-a-constant-have-passed     -> derived-subject-set              2
  recorder-in-the-record           -> instruments-already-running      1
  recorder-in-the-record           -> sampled-interval-brackets        1
  kill-what-you-launched           -> instruments-already-running      1
  sanitiser-outgrows-its-noise     -> run-the-comparison-you-suppress  1
  residency-is-not-allocation      -> would-a-constant-have-passed     1
  run-the-comparison-you-suppress  -> bounded-not-binary-witness       1

skill                               lost  abst top MEASURED taker             NAMED in its description       hit?
untested-default-path                 13     5 echoed-record-vs-measurement   derived-subject-set,unrun-chec no
sanitiser-outgrows-its-noise          11     4 copied-mirror-drift            filter-shares-the-defect,would no
filter-shares-the-defect               7     4 bounded-not-binary-witness     derived-subject-set,measured-e no
would-a-constant-have-passed           6     4 derived-subject-set            filter-shares-the-defect,untes no
derived-subject-set                    4     2 citation-registry-integrity    carried-claim-rot,unenforced-d no

0 of 5 skill(s) whose description names a confusable AND that lost at least one probe to some taker had that NAMED skill as its top measured taker.
```
