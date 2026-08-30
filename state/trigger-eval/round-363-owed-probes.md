# skill trigger eval — round 363 (skills B), the four owed probes

mode=native model=sonnet protocol=strict

probes: 16 ok, 0 errored, exact-match 94%, negatives false-fire 0/4, cost $1.095

The four skills each deferred here by a non-skills(B) round (`state/known-unprobed-skills.json`, rounds 358/359/360/361) under the standing convention that a priced run belongs to a batch. `--only` filters cases before any probe is spawned — verified by reading `trigger_eval.py:1220` before the run, not assumed.

The one miss, `mexempt-near` displaced by `refusal-set-differential`, was re-probed at n=4 and fired 4/4 exact: draw variance, not a description defect. See `round-363-mexempt-reprobe.md`.

*(The tables below are this run's own stdout; the header above is reconstructed from the JSON because the capture kept only the tail.)*

| declaration-scope-parity | n/a | n/a | 0 | 0 | 0 |
| deleted-vs-never-written | n/a | n/a | 0 | 0 | 0 |
| engine-prefix-reuse-audit | n/a | n/a | 0 | 0 | 0 |
| errors-that-name-the-fix | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | n/a | n/a | 0 | 0 | 0 |
| generator-trampoline-evaluator | n/a | n/a | 0 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| measured-exemption | 67% | 100% | 2 | 0 | 1 |
| measured-not-declared-dependencies | 100% | 100% | 3 | 0 | 0 |
| offline-agent-testing | n/a | n/a | 0 | 0 | 0 |
| one-shot-agent-no-background-wait | n/a | n/a | 0 | 0 | 0 |
| optimization-transparency-differential | n/a | n/a | 0 | 0 | 0 |
| prediction-banking | n/a | n/a | 0 | 0 | 0 |
| preflight-priced-task-scripts | n/a | n/a | 0 | 0 | 0 |
| pristine-checkout-differential | n/a | n/a | 0 | 0 | 0 |
| refusal-set-differential | 100% | 75% | 3 | 1 | 0 |
| sampled-interval-brackets | n/a | n/a | 0 | 0 | 0 |
| self-updating-driver-loop | n/a | n/a | 0 | 0 | 0 |
| session-inheritance-audit | n/a | n/a | 0 | 0 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | n/a | n/a | 0 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |
| unenforced-documented-rule | n/a | n/a | 0 | 0 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| bnbw-near | bounded-not-binary-witness | bounded-not-binary-witness | — | yes |
| bnbw-mid | bounded-not-binary-witness | bounded-not-binary-witness | — | yes |
| bnbw-far | bounded-not-binary-witness | bounded-not-binary-witness | — | yes |
| bnbw-neg-plain-bool | — | — | — | yes |
| mexempt-near | measured-exemption | refusal-set-differential | — | NO |
| mexempt-mid | measured-exemption | measured-exemption | — | yes |
| mexempt-far | measured-exemption | measured-exemption | — | yes |
| mexempt-neg-noqa | — | — | — | yes |
| rsd-near | refusal-set-differential | refusal-set-differential | — | yes |
| rsd-mid | refusal-set-differential | refusal-set-differential | — | yes |
| rsd-far | refusal-set-differential | refusal-set-differential | — | yes |
| rsd-neg-rename | — | — | — | yes |
| mndd-near | measured-not-declared-dependencies | measured-not-declared-dependencies | — | yes |
| mndd-mid | measured-not-declared-dependencies | measured-not-declared-dependencies | — | yes |
| mndd-far | measured-not-declared-dependencies | measured-not-declared-dependencies | — | yes |
| mndd-neg-static-imports | — | — | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

[exited with code 0]
