# Safety model

The app is built so that a person always decides, and so that the replies stay useful. This page lists the rules the code enforces and the reasons.

## What the app never does

- It never creates or manages accounts, and it never stores a password, cookie or session. You link an account you already use. Only the handle is stored.
- It never posts without an approved reply and a passing gate.
- It never lets a specialist post, approve, change settings or link an account. Only the owner acts, through the owner tools.
- It never drafts for Hacker News. The site bans generated and AI-edited comments (March 2026).
- It never sends direct messages, votes, or follows users.
- It never writes a testimonial or poses as an unrelated customer. The product reply states your connection in a first-person sentence.

## Verification before work counts

Every specialist output goes through the verifier before the CEO treats it as done. Claims cite evidence ids from tool calls and must use words the evidence holds. A claim that cites only a failed call is rejected. Quotes must appear word for word in that evidence. The summary may say no more than the evidence, the claims and earlier verified work. An honest "nothing found" passes; an invented result does not. Numbers and links must come from a tool result, the owner's request or a harvested thread. A lead needs a verified quote to be high potential, and a second model reads high potential threads again. A draft must pass the linter and may state only numbers found in the profile or the thread. The auditor model receives a planted false claim in every batch, and a pass on that claim marks its verdict unreliable. An editor reads every draft. Then the posting inspector runs by itself: it asks the gates what each draft would get if you approved it today, and flags drafts edited after the editor read them. After three failed tries a task returns to the CEO. See `skills/company-operations/references/verification-rules.md`.

## Gates, in order

| Code | Meaning |
| --- | --- |
| emergency_stop | You set the stop. Nothing posts. |
| draft_mode | Posting is off. |
| not_approved | The reply has no approval. |
| empty | The reply text is empty. |
| platform_policy | The platform bans drafts or automation (Hacker News). |
| lint | The text breaks a writing rule. |
| rules_not_read | A Reddit community has no recorded rules. |
| rules_no_ai | The community bans AI-written content. |
| rules_no_promo | The community bans or limits self promotion and the reply names the product. |
| rules_no_links | The community bans links and the reply has one. |
| not_whitelisted | You set an allow-list and the community is not in it. |
| target_taken | The post or comment already has a reply. A target takes one reply. |
| thread_account | Another of your accounts replied in this thread. One account per thread. |
| thread_cap | The thread holds the most replies you allow (2 by default, 3 at most). |
| same_author | You already answered this person in the thread. |
| same_opening | Another reply in the thread opens with the same words. |
| thread_product | Another reply in the thread already names the product. |
| thread_gap | Two replies in one thread need a gap (60 minutes by default). The inspector reports it as a wait. |
| account_needed | Several accounts are linked and the reply has none. Save the reply with an account. |
| account_missing | The reply's account is no longer linked. |
| account_unknown | The account is not linked or not readable. |
| account_health | The pitch level exceeds what the account's age and karma allow. |
| rules_min_karma | The community wants more karma than the account has. |
| community_overlap | Another of your accounts named the product in this community in the last 7 days. |
| mention_ratio | More than 10 percent of recent comments would name the product. Counted per account. |
| daily_cap | The lower of your cap and the account's cap is reached. Counted per account. |
| interval | The gap since the last post is too short. The gap is jittered by up to 30 percent. |

For platforms other than Reddit, account health uses age only (30 days for level 1, 90 days for level 2) and caps the level at 2.

## Automatic posting

Off by default. It needs all of these: posting mode `automatic`, `AGENT_REACH_ALLOW_AUTOPOST=1`, approved API credentials in the environment, and a platform with an API path in this app (Reddit, GitHub). Reddit stopped self-service API keys in November 2025, so Reddit posting through the API works only if Reddit approved your application. X forbids unsolicited automated replies, so X stays manual.

## The pitch ladder

Level 0 helps only. Level 1 describes the kind of tool without a brand. Level 2 names the product once with a natural affiliation sentence and no link. Level 3 adds a link, only when the thread asks for one and the community allows links. The default is 2. The account's health lowers it, never raises it.

## Disclosure

US FTC endorsement guidance expects a clear statement of a material connection. The linter requires a natural first-person statement ("I built X", "I work on X", "I'm on the X team") in the same reply that names the product. It rejects legal footers and tags such as "Disclosure:" or "#ad", because they read as automation and communities remove them. The text for your region may need more. Check local rules.

## Untrusted text

Posts, comments, usernames and pages are data. The pipeline and the MCP server strip hidden characters, flag instruction-like phrases and wrap text as untrusted. A thread with injection patterns is skipped.

## Known limits

The linter checks what it can measure. It does not decide whether a human or a platform classifier will think a reply is generated. Edit every reply so it matches how you write, keep your product replies under 1 in 10, and use the warm-up plan in `skills/platform-safety/references/warm-up-plan.md` for a young account.
