# Agent latency checks — 30 October 2026 (Hong Kong)

**Current acceptance criterion: P50 of completed answers <= 5 seconds.** The historical short per-request cutoff experiments below have been superseded. Prompt instructions contain no five-second deadline. Backend request safety timeout is 120 seconds, and Worker no longer aborts/buffers replies at 3.6 seconds. Normal Plan requests allow the Agent to finish instead of automatically switching to a basic itinerary after two seconds. Keep historical measurements for comparison, but do not use a fast timeout notice as evidence of an improved answer median.

The current benchmark reports all-request, completed-business-answer and model-backed-business-answer p50/p95, plus answer/refusal/clarification/error/timeout/basic-plan counts. It distinguishes an unexpected refusal of an in-scope question from the expected out-of-scope refusals. The synthetic mix is not a measurement of the site's real user traffic distribution. Real chat-only successful-answer medians are available separately in the private monitor as `answer_duration_p50_ms` / `answer_duration_p95_ms`, and model-backed-only medians as `model_answer_p50_ms` / `model_answer_p95_ms`.

## First online follow-up, before edge deadline

26 real HTTPS requests against the new backend: 24/26 ended within 5 seconds; all returned final events. p50 1.399 seconds, nearest-rank p95 8.096 seconds, maximum 8.216 seconds. Two first-round complex requests exceeded the target despite a backend time budget. Eight replies carried degraded=true (including cheaper-model lane downgrade); four were chat time-budget replies and two were basic saved-candidate plans. These are **not** 26 successfully verified answers. Later rounds were faster, but the slow samples are retained. This result motivated a Worker deadline covering both response headers and the entire body, rather than increasing the claimed success rate by excluding cold samples.

Local HTTP fault injection separately measured slow classification/tool/review/queue delays at 4.009 seconds, a normal answer while Postgres was stalled at 0.047 seconds, and a synthetic provider failure at 0.027 seconds. Fault injection substitutes controlled delays; it does not establish global provider reliability. Public responses contained no trace metrics. Worker tests now cover an origin that never returns headers, an SSE body that stalls after headers, oversize bodies and cancellation, with explicit failure/degraded results.

## Initial baseline and local comparison

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
