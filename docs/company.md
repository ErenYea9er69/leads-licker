# The company layer

You talk to the CEO. The CEO plans the work, hands it to specialists, checks every result and reports only what passed.

## Members

| Role | Job | Tools it holds | Extra check |
| --- | --- | --- | --- |
| analyst | Business profile from your site or description | fetch site text, save profile | features and prices appear in the source |
| scout | Plans queries, harvests open threads | plan queries, harvest | every listed thread came from a harvest of this task |
| qualifier | Scores threads, saves real leads | read items, read thread, save lead | verified quote, second model opinion |
| writer | Drafts replies in your voice | reply context, lint, save reply, voice | linter passed, no invented numbers |
| editor | Second read of every draft: approve, revise, reject | read replies, lint | every draft has a verdict with reasons |
| strategist | Reviews results | insights, leads, account health | numbers come from tools |
| researcher | Competitors and market from fetched pages | fetch site text | each fact has a quote from a page fetched in the task |
| follow_up | Re-reads threads where you replied | read thread, set lead status | each thread was read in the task |
| inspector | Posting gates for every draft. Automatic: code, no model, no assistant | none | computed by the engine from the database |

You can hire more with `ceo_hire_specialist`. No specialist can post, approve, change settings or link accounts.

## Why these members

The roster was reviewed against the code, and every position had to show work no other part of the system does.

- Kept: analyst, scout, qualifier, writer, editor, strategist, researcher, follow_up. Each needs judgment, reads different tools and answers a different question.
- Removed, compliance: it only copied the gate code from a tool, and the verifier then recomputed the same code, so it added no judgment. Worse, a draft is not approved yet, so the gate stopped every draft at the approval gate and the report said "not_approved" for all of them. The real blockers (rules not recorded, account stage, links) never showed. This was confirmed by test before the change.
- Removed, auditor (the final task): its only check was that it made a read call, nothing used its findings, and in market research it had no tool that could re-read the fetched pages. The independent check that matters lives in the verifier: the auditor model with a planted false claim, the qualifier's second opinion and the editor.
- Added, inspector: it replaces both. It is code, not a model. It asks the gates what each draft would get if you approved it today and posting were on, and it flags a draft edited after the editor read it or a lead whose quote is not verified. It costs no model call and no assistant turns.
- Considered and not added, a community-rules reader: the app makes the owner read and record each community's rules on purpose, as an acknowledgement. A specialist that records them for you would remove that safeguard. The inspector now tells you exactly which communities still need their rules recorded.

## Interview and background work

A new owner starts with `ceo_intake`. The CEO asks one or two questions at a time: product, target users, problems in the customers' words, where they talk, competitors, site, accounts, voice, language, rules and how to post. The host assistant passes each answer in the owner's own words. The CEO never fills a gap.

Once the product and the target users are known, the CEO starts the search on its own, in a background thread on the server, for the platforms the owner named (Reddit, Hacker News and the web by default). The call returns at once. While the search runs, the CEO asks the questions the search does not need first (accounts, voice, language, rules, posting). The next call reports what each job found. A source that failed is marked failed, with the reason. An empty result from failing providers is a failure, not "nothing found".

The threads found this way wait in the database, flagged as found ahead of the scout. The scout's own harvest step claims each one once, with a fresh health check, so the verifier still sees every reported thread inside a harvest result of the scout's task. Nothing is scored or drafted early. The intake runs at most three searches for one interview, and only when the facts changed.

With a server model the CEO also opens the full plan in the background. The analyst builds the profile and stops at the owner checkpoint. Without a server model the host assistant plays the specialists after the interview.

## Plans

find_customers, draft_replies, review_drafts, weekly_review, setup_voice, market_research, follow_up. A request that fits none is planned by the server model (then validated like a hand-written plan) or by keyword rules without a model.

## What happens when nothing is found

The scout reports `nothing_found` with a reason. The CEO sends it out once more with a wider brief. If it is still empty, the qualifier, writer, editor and inspection steps are skipped, the request completes, and the report says what was tried and what to change. The same holds when threads come back but none qualify.

## Verification

Every result passes the checks in `skills/company-operations/references/verification-rules.md`. The worker runs the same checks before it hands a result in, so it fixes most issues without using an attempt. The auditor model gets one planted false claim in every batch. If it passes that claim, its verdict is marked unreliable and the trust level drops to low.

## Memory

`ceo_memory` stores your standing preferences. The team adds lessons: queries that returned nothing, communities that gave strong leads, reasons the editor questioned a draft and reasons a task was rejected. Specialists see up to eight notes in their work order. Memory is never evidence, and a claim that cites it is rejected.

## Recovery and limits

- A task that runs longer than 20 minutes without a result returns to the queue.
- A rate limit or timeout from the model waits and retries without using an attempt.
- A directive may make 150 tool calls. Raise `tool_budget` on the directive if a large job needs more.
- The same open request is not planned twice within 10 minutes.
- `ceo_cancel_directive` ends open tasks. Verified work stays in the report.

## Limits that remain

- In host mode the assistant relays your checkpoint answers. The server records the channel (assistant, dashboard or cli). Use the dashboard when it matters.
- Without a model key on the server, the auditor model, the second opinion and the model planner are off. The deterministic checks still run.
- The word-overlap check for claims and summaries catches claims about things the evidence never mentions. It cannot judge whether a true fact supports a weak conclusion. The auditor model covers part of that.
- Memory notes about queries are coarse: a harvest records its whole query set, not each query.
- The "thread still open" check at post time still runs only on the Reddit API publishing path.
