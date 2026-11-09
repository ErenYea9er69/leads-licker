# Audit of the company layer (3.0.0 to 3.1.0)

This file lists every weakness found in the CEO and team layer of 3.0.0, how it was found, what 3.1.0 does about it and what stays open. Two findings were confirmed by running the code before any fix.

## Results

| # | Weakness in 3.0.0 | How it was found | Fix in 3.1.0 |
| --- | --- | --- | --- |
| R1 | A claim could pair a real quote with an unrelated sentence ("used by banks worldwide" next to the quote "Tidewatch") and pass without the auditor model | Confirmed by test | `support` check: the claim's content words must appear in the cited evidence |
| R2 | A result with a summary, no claims and no tool call passed ("Customers love the product") | Confirmed by test | `work` check: a task with tools needs a working call and at least one claim or an honest empty result |
| R3 | The summary was checked for numbers only | Code read | `summary` check against evidence, claims, earlier verified work and the request |
| R4 | A claim could cite a failed tool call as support | Code read | Rejected unless `about_failure` is set |
| R5 | Spelled numbers (forty, hundred) were never checked | Code read | Number words map to digits on both sides of every number check |
| R6 | One-word quotes counted as proof | Code read | A quote under three words fails when the evidence is long |
| R7 | The report was one text blob: no lead, no quote, no draft, no trust level | Code read | Lead cards, headline, trust level, what was tried, quality numbers, progress |
| R8 | "Nothing found" was a failure: the writer failed because there was nothing to write, and the directive stuck in needs_ceo | Code read | `nothing_found` result, one wider search, skipped downstream tasks, honest report |

## Thinking and planning

| # | Weakness | Fix |
| --- | --- | --- |
| P1 | A request that fit no plan made zero tasks. Server mode did nothing | Model planner (validated like a hand-written plan) or keyword rules, plus an auditor step |
| P2 | No preflight. A missing key, account or voice sample showed up late or never | Readiness notes on every new directive |
| P3 | A request with no site and no description failed inside the analyst | The CEO asks the owner first (`provide_info` checkpoint) |
| P4 | No replan when a search found nothing | The scout widens the search once |
| P5 | Plans were linear and never added work | The editor loop adds a revision round for the writer and a second read |
| P6 | Intent rules knew four intents | Seven plans and rules for market research, follow-up and draft review |

## Missing team members

| Missing | Why it mattered | Added |
| --- | --- | --- |
| Editor | Drafts had one reader (the writer) and the linter. Tone, relevance and over-pitching went unchecked | `editor` with verdicts, reasons and a revision round |
| Researcher | "Research competitors" had no owner. Facts came from memory | `researcher`: every fact needs a quote from a page fetched in the task |
| Follow-up tracker | Nobody watched threads after posting | `follow_up`: re-reads threads and moves leads to replied or closed |
| Memory keeper | The company forgot everything between requests, including the owner's corrections | Company memory in the store, in every work order, via `ceo_memory` |

## The owner and the host assistant

| # | Weakness | Fix |
| --- | --- | --- |
| U1 | The host followed a long protocol and could lose its place | `ceo_next_step` answers with one action |
| U2 | No way to stop a directive | `ceo_cancel_directive`, dashboard route, CLI command |
| U3 | Owner feedback on a rejected profile vanished after the retry | Stored as an owner preference |
| U4 | Nobody could tell whether the owner or the assistant answered a checkpoint | The channel is recorded and shown in the report |
| U5 | Same request twice made two directives | Deduplicated for 10 minutes |

## Reliability and cost

| # | Weakness | Fix |
| --- | --- | --- |
| S1 | A task left running by a vanished host or a restart stayed running forever | 20 minute lease, recovery in `status`, `next_step`, `run` and `work_order` |
| S2 | Evidence ids came from the ledger length. Two calls at once could share an id | Lock per directive (tested with six parallel calls) |
| S3 | A rate limit used up an attempt | Retried with backoff, no attempt used |
| S4 | A worker could burn attempts on mistakes it could fix at once | Pre-check inside the worker loop, two free revisions |
| S5 | No ceiling on tool use | 150 calls per directive |

## The auditor

| # | Weakness | Fix |
| --- | --- | --- |
| A1 | Nothing showed whether the auditor was reading or rubber stamping | A planted false claim in every batch. Passing it marks the auditor unreliable and lowers trust |
| A2 | The auditor was the same model as the workers, so errors correlate | `AGENT_REACH_AUDITOR_PROVIDER` and `AGENT_REACH_AUDITOR_MODEL` select another provider |

## What stays open

- Host mode cannot prove who answered a checkpoint. The server now records the channel. Use the dashboard for important approvals.
- Word overlap catches claims about things the evidence never mentions. It cannot judge whether a true fact supports a weak conclusion. Only the auditor model covers part of that.
- Without a model key on the server, the auditor, the second opinion and the model planner are off.
- A restarted dashboard does not resume a background run on its own. The lease returns the task to the queue after 20 minutes and the next status call or run picks it up.
- Lessons about queries are coarse. A harvest records the whole query set, not each query.
- The "thread still open" check at post time still runs only on the Reddit API path.
- The thresholds for the support check (0.6) and the summary check (0.5, words of six letters or more) come from tests, not from live traffic. If they reject good output with your model, lower `SUPPORT_MIN` and `SUMMARY_MIN` in `agent_reach/team/verifier.py` and watch the `issues` the verifier returns.
- Nothing was run against live accounts or live search providers.

## Second review: the roster (3.2.0)

The roster was checked again against the code. Evidence came from running the code, not from the role descriptions.

| Position | Finding | Decision |
| --- | --- | --- |
| compliance | Drafts are not approved yet, so the gate stops at `not_approved` before it checks rules, links, account stage or caps. The report said "not_approved" for every draft. The role also only copied the code, which the verifier recomputed. | Removed. The automatic inspector runs the gates as if the draft were approved. |
| auditor (closing task) | The role check was "made a read call". Nothing consumed its findings. In market research it had no tool to re-read fetched pages. | Removed. The auditor model in the verifier, the qualifier second opinion and the editor remain. |
| analyst, scout, qualifier, writer, editor, strategist, researcher, follow_up | Each holds different tools, answers a different question and has a check that rejects bad output. | Kept, unchanged. |
| community rules reader | The app requires the owner to read and record each community's rules as an acknowledgement. Automating it would remove that safeguard. | Not added. The inspector names the communities whose rules are missing. |
| More specialists in general | No concrete failure needed another one. | Not added. |

Inspector limits: it asks the gates about the state today. A daily cap or an interval can change before you post. It cannot see rules you have not recorded, and it cannot judge the quality of a draft; that is the editor's job.
