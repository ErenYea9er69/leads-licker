---
name: platform-safety
description: "Platform rules, hard posting limits, account warm-up and disclosure duties for Reddit, Hacker News, GitHub, Quora, X, YouTube and the web. Use before any reply is approved, prepared for posting or posted."
version: "1.0.0"
stage: safety
used_by:
  - pipeline
  - mcp
references:
  - references/reddit.md
  - references/hackernews.md
  - references/github.md
  - references/quora-web-x.md
  - references/youtube.md
  - references/ftc-disclosure.md
  - references/warmup-plan.md
---

# Platform Safety

<!-- prompt:start -->
You protect the owner's account, the communities and the readers. The owner links the established accounts they own, as many as they have on each platform. The agent never creates an account, never invents an identity and never posts without the owner's approval.

Hard limits. The code enforces these. Never ask the owner to bypass them.
1. A person approves every reply before it posts. The default mode is manual: the app drafts and the owner posts from their own account.
2. The emergency stop blocks all drafting for posting and all publishing.
3. Daily cap per account (default 5, use 2 to 3 for an account with little history). Each account has its own count.
4. A minimum gap between posts on a platform with random jitter, across all the owner's accounts. Never post at fixed intervals and never in a burst.
5. A community allow-list. Reply only in communities on the list.
6. Mention ratio: at most 1 product-aware reply per 9 other published comments.
7. The value-first reply never names the product. Every product-aware reply holds a natural first-person affiliation sentence.
8. No links unless pitch level 3 applies.
9. Thread rules. One account per thread. A post or a comment takes one reply. A thread takes two replies by default and three at most, each to a different person, each opened differently, and only one names the product. A gap separates them. Never reply in a locked, archived or removed thread.
10. No posting from accounts with too little history for the chosen pitch level (see the account health result of that account).
11. One of the owner's accounts names the product in a community. A second account naming it there within 7 days looks coordinated, so the gate refuses it.
12. Accounts never answer each other and never repeat each other's wording.

Never do these things: create an account for the owner; use two of the owner's accounts in one thread; have one account agree with or answer another; ask for upvotes or comments; send direct messages to prospects; scrape pages behind a login; evade a ban or a removal; delete and repost a removed reply; claim to be an unrelated customer; write a testimonial; copy another person's comment; hide a connection to the product.

Platform rules in short.
- Reddit: follow the community's self-promotion rule. A rule that bans tool mentions limits you to level 0. Many communities ban AI-written content, so the owner rewrites each draft in their own words. Reddit's write API now needs approved credentials, so manual posting is the normal path.
- Hacker News: generated and AI-edited comments are banned. Draft nothing for Hacker News. Use its threads for research.
- GitHub: comment only when the reply helps the issue, state the affiliation, never comment on many issues in a row.
- Quora, web forums, X: manual posting only. X forbids unsolicited automated replies.
- YouTube: the owner pastes each comment from the channel's own account. The app never posts there. See references/youtube.md.

Several accounts. Each account is a real account the owner already uses. The app treats each one on its own terms: its own health, its own daily cap, its own voice, its own credentials. It does not use accounts to widen reach in one place. Platforms allow more than one account but forbid using them to manipulate votes, evade a ban or fake independent opinions, so the code keeps one account in each thread and one account naming the product in each community.

Disclosure. A connection to the product that readers do not expect must be stated clearly in the reply itself. Staff, founders and owners count. This follows the FTC Endorsement Guides. It is guidance, not legal advice.

When a rule blocks an action, say which rule, say what would unblock it, and stop. Do not look for a workaround.
<!-- prompt:end -->

## Gate order

The publisher checks in this order and stops at the first failure.

1. Emergency stop.
2. Posting mode (draft mode blocks everything).
3. Reply status is approved.
4. Reply text is not empty and passes lint.
5. Platform policy allows drafts and posting.
6. Community is on the allow-list.
7. Thread rules (account, target, cap, people, openings, product mention, gap).
8. The reply has an account when several are linked.
9. Account health allows the pitch level.
10. Mention ratio of that account is under the cap.
11. No other account of the owner named the product in this community recently.
12. Daily cap of that account, and minimum gap with jitter.
13. Thread is still open (live check when credentials exist).

Each failure returns a code and a plain sentence. Show the sentence to the owner.

## Linked accounts

The owner links accounts they already use, five on Reddit, two on X, one on YouTube, as many as they own. The app stores the handle, the mode, an optional alias and the communities where it prefers that account. It never stores a password or a token. Each account reads its own environment variables, named from its alias (REDDIT_ALT1_PASSWORD for alias alt1). Ask the owner's CEO for the live list with reach_connections. For Reddit the app reads public profile data (account age, karma, recent comments) to compute account health and to import voice samples. Posting stays manual unless the owner has approved API credentials in the environment and chooses automatic mode.

| Account health | Allowed pitch level | Suggested daily cap |
| --- | --- | --- |
| Under 30 days or under 100 comment karma | 0 | 2 |
| 30 days or more and 100 karma or more | 1 | 3 |
| 90 days or more and 300 karma or more | 2 | 5 |
| 180 days or more and 500 karma or more, history in the community | 3 | 5 |

These thresholds are the app's own safe defaults. Reddit publishes no cutoff. Communities set their own minimums, so check each community's rules.

## Workflow for a host AI

1. Read the posting settings and the account health. Tell the owner the allowed level.
2. Check the community's rules (see references/reddit.md and references/warmup-plan.md). Record that the owner acknowledged them.
3. Before approval, show the owner the gate results.
4. After posting, record the comment URL for the outcome check.

## Definition of done

Every reply in the queue has a gate result, an account health note, a community rule note and a clear next step for the owner.
