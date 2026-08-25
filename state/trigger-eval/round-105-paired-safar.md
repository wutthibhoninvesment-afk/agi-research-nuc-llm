# skill trigger eval — mode=native model=sonnet arm=plain

probes: 4 ok, 0 errored, exact-match 100%, negatives false-fire 0/0, cost $0.180

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | n/a | n/a | 0 | 0 | 0 |
| engine-prefix-reuse-audit | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | n/a | n/a | 0 | 0 | 0 |
| generator-trampoline-evaluator | n/a | n/a | 0 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | n/a | n/a | 0 | 0 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | 100% | 100% | 4 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |

per-case fire rates (all-expected-fired vs exact; negatives: hit = nothing fired):
| case | runs | fired | exact | err |
|---|---|---|---|---|
| sa-far | 4 | 4 (100%) | 4 (100%) | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| sa-far | skill-authoring | skill-authoring | — | yes |
| sa-far | skill-authoring | skill-authoring | — | yes |
| sa-far | skill-authoring | skill-authoring | — | yes |
| sa-far | skill-authoring | skill-authoring | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# skill trigger eval — mode=native model=sonnet arm=staged

probes: 4 ok, 0 errored, exact-match 100%, negatives false-fire 0/0, cost $0.181

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | n/a | n/a | 0 | 0 | 0 |
| engine-prefix-reuse-audit | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | n/a | n/a | 0 | 0 | 0 |
| generator-trampoline-evaluator | n/a | n/a | 0 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | n/a | n/a | 0 | 0 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | 100% | 100% | 4 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |

per-case fire rates (all-expected-fired vs exact; negatives: hit = nothing fired):
| case | runs | fired | exact | err |
|---|---|---|---|---|
| sa-far | 4 | 4 (100%) | 4 (100%) | 0 |

| case | expect | fired | staged-distractor | foreign | ok |
|---|---|---|---|---|---|
| sa-far | skill-authoring | skill-authoring | — | — | yes |
| sa-far | skill-authoring | skill-authoring | — | — | yes |
| sa-far | skill-authoring | skill-authoring | — | — | yes |
| sa-far | skill-authoring | skill-authoring | — | — | yes |

staged distractors (5): hermes-agent-skill-authoring, llama-cpp, python-debugpy, systematic-debugging, test-driven-development
displacement (expected skill missing while a staged distractor fired): 0 probe(s)

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

# paired suppression diagnostic — model=sonnet
(fired = all expected skills fired; drop ≥2 with no distractor fire on the case = suppression)

| case | plain fired | staged fired | gap | distractor fired | verdict |
|---|---|---|---|---|---|
| sa-far | 4/4 | 4/4 | +0 | 0 run(s) | ok |
