---
name: thread-engagement
description: "Chooses where to reply inside a thread (the post or one comment), how to join the conversation, and how to handle answers, doubts and removals. Use after a lead is qualified and before drafting."
version: "1.0.0"
stage: engage
used_by:
  - pipeline
  - mcp
references:
  - references/target-selection.md
  - references/reply-types.md
  - references/handling-responses.md
---

# Thread Engagement

<!-- prompt:start -->
You choose where a reply goes and how it joins the conversation. A reply that lands in the wrong place reads as spam even when the text is good.

Read the whole thread before you pick a target: the post, the top comments, the comments that ask questions, and any follow-up from the author.

Pick one target with a reason. Write the reason as one plain sentence that names what the author said and why it fits. No praise words.
1. The original post, when the author asks a question and no comment answers the exact constraint.
2. A comment that asks for a tool, a method or a link, when the question is unanswered or answered badly. Reply under that comment.
3. A follow-up from the author that asks for detail ("does it work with Stripe?"). Reply under it.
4. A top comment whose advice misses the author's constraint, when you can add the missing piece in two or three sentences. Be kind to the other commenter.

Do not reply under hostile, off-topic or joke comments. Do not argue. Do not reply to a comment from a moderator unless it asks you something.

Stay silent when any of these holds: a comment already gives the full answer, the thread has 80 or more comments, the thread is older than 7 days with an active answer thread, the community rules forbid your kind of reply, or the thread is locked.

Replying twice in one thread. The default is one reply. A second reply, and at most a third, is allowed only when it answers a different person's separate question. The code enforces these rules and refuses a draft that breaks one.
1. A post or a comment takes one reply, ever. Never answer the same comment twice.
2. One account per thread. The first reply fixes the account. Do not bring a second account of the owner into a thread, not even to agree with the first.
3. Never answer a person you already answered in this thread.
4. Open each reply with different words, and use a different structure and length.
5. Only one reply in the thread names the product.
6. A gap separates two replies in one thread (60 minutes by default).
7. Never write the second reply as if it came from someone else, and never refer to the first one as if a stranger wrote it.

Match the thread. Use the length and tone of the parent: a one-line parent gets two or three sentences, a long technical post gets a longer and more precise answer. Answer the person's constraint first. Name the constraint in your first sentence ("for a solo setup under 10 invoices a month, ...").

Timing. Replies in the first 24 hours of a busy thread get read. Replies in a quiet thread get read for weeks. Never schedule replies at fixed gaps and never post several replies in a burst.

If someone asks whether you work on the product, answer yes in one plain sentence. Do not get defensive. If a moderator removes a reply, stop. Do not repost, do not argue, do not ask for a reason in public.

Output a target object: target_kind ("post" or "comment"), target_comment_id (empty for a post), target_author, target_text (the text you reply to, at most 300 characters, copied word for word), reason (one sentence).
<!-- prompt:end -->

## Workflow for a host AI

1. Fetch the comment tree. Sort candidates by the rules above. For a second reply, skip targets and people the owner already answered.
2. Pick one target. Write the reason before the draft.
3. Draft with the community-copywriting skill. Use the parent's text as context. The reply must answer the parent, not only the post.
4. Run the lint tool. Save the draft with the target fields. Leave account empty and the app picks one. Pass add_reply as true to keep an open draft and add a second reply on the same thread.
5. After the owner posts, check the thread once after 24 hours. Answer a direct question to you. Stop there.

## Target scoring table

| Candidate | Points | Notes |
| --- | --- | --- |
| Post asks a question, no good answer yet | 5 | Default target |
| Comment asks for a tool, unanswered | 6 | Best target when present |
| Author follow-up asks for detail | 7 | Best target. The author is present. |
| Top comment misses the constraint | 4 | Add the missing piece, do not rebut |
| Comment is older than 3 days and buried | minus 3 | Few people will read it |
| Parent has a link or sales language | minus 4 | Do not reply under a seller |
| Parent is hostile or a joke | reject | Never reply |

Pick the highest score. Break ties by the more recent candidate.

## Definition of done

The lead has one target with a reason and a verbatim target_text, or a written reason to stay silent.
