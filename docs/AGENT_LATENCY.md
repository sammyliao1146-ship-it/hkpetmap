# Agent latency checks — 30 October 2026 (Hong Kong)

All prompts are synthetic. Before: live https://hkpetmap.com, 12 chat scenarios, concurrency 2. After: local HTTP service with the configured real model provider and temporary local Postgres, 13 scenarios repeated twice (26 requests), concurrency 2. These are different network paths; do not attribute all differences to code or claim a production SLA from local results.

Baseline: 4/12 requests ended within 5 seconds; 10 returned a final answer. Nearest-rank p95 25.111s; maximum 25.111s. Phone/follow-up prompts incorrectly asked for clarification; one search ended without a final event and the disclosure attempt failed classification.

Local after: 26/26 ended within 5 seconds; 25 returned a final answer. Nearest-rank p95 4.009s; maximum 4.009s. 8 responses had degraded=true (including model-lane downgrade). Four chat replies hit the time budget and two structured plans used the explicitly labelled candidate fallback. One disclosure request returned a classifier error; a subsequent denial-only local rule handles this family without a model. Online follow-up measurements should be used for final deployment assessment.

| Scenario | Live before (s) | Local after, first run (s) | After outcome |
| --- | ---: | ---: | --- |
| nearby | 3.516 | 0.152 | scope refusal |
| cuisine_rating | 12.644 | 0.132 | saved answer / clarification / scope refusal |
| phone | 2.076 | 0.03 | saved answer / clarification / scope refusal |
| budget | 11.595 | 0.032 | saved answer / clarification / scope refusal |
| follow_up | 5.169 | 0.014 | saved answer / clarification / scope refusal |
| ambiguous_directions | 8.411 | 0.013 | saved answer / clarification / scope refusal |
| transport | 7.985 | 0.012 | saved answer / clarification / scope refusal |
| mall_rules | 14.694 | 0.011 | saved answer / clarification / scope refusal |
| live_hours | 15.618 | 4.009 | time-budget response, not verified completion |
| off_topic | 2.417 | 2.314 | scope refusal |
| injection | 3.601 | 3.882 | error |
| trip | 25.111 | 4.009 | time-budget response, not verified completion |
| structured_plan | not measured | 2.136 | validated candidate fallback |

Regression checks: 174 backend tests, including temporary real PostgreSQL. Fault tests cover a slow model/tool/reviewer chain, response-before-storage ordering, cancelled work, incomplete draft suppression, whole-message fast-path boundaries and parking-covered Plan fallback. They do not simulate global network failures or guarantee timing under arbitrary CPU load.

No model migration or removal of source/scope checks was used. The warm-service computation deadline is 4 seconds; it cannot bound Render startup, network transit or event-loop blocking. A complete newly researched answer for every possible question in 5 seconds remains unproven.

Reproduce using `python -m scripts.benchmark_agent --base-url URL --output /tmp/report.json --repeat 2`. This calls paid model/search services. Raw reports in this directory omit answer bodies; local full answers were used to check outcome quality.
