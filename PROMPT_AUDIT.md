# Prompt and reply audit (3.3.0)

Scope: every piece of text that shapes what the owner posts. That covers the copywriting skill and its references, the reply generator prompt, the linter and its lexicons, the examples and the disclosure phrases. The other skills and the team prompts were scanned for banned words and dashes only.

## Scan result

- No em dash or en dash in any skill, prompt or example. The only dash characters in the project are the two detectors (`voice.py`, `validate_skills.py`).
- No banned word in a model prompt, except where a prompt lists the word to forbid it.

## Weaknesses found and what changed

| Area | Weakness | Change |
| --- | --- | --- |
| Linter | Inflected banned words passed (unlocked, discovering) | Inflection-aware matching, cached |
| Linter | A spaced hyphen replaced the em dash and passed | Error, and normalized to a comma |
| Linter | No check for not-X-but-Y, lead-ins, scripted sympathy, greetings, closing questions | Five new errors |
| Linter | No check for list-of-three habit, repeated openers, hedge stacks, missing contractions, missing detail | New warnings |
| Linter | A banned-word error invited a synonym swap | Message says to rewrite the sentence |
| Lexicon | No sales jargon, sign-offs or intensifiers | About 80 entries (hard and budgeted) |
| Skill prompt | Fixed 4/20/9 rhythm produced a new, copyable cadence | Removed. Length follows the idea |
| Skill prompt | A limit sentence in every reply became a template | Conditional, and not always last |
| Skill prompt | No instruction to react to one detail of the thread | Three-step start |
| Skill prompt | No ban on the problem, advice, caveat, product arc | Added, with a variety rule |
| Examples | No contractions, although the rules ask for them | Rewritten with contractions |
| Examples | Same opening shape ("At N ...") and same closing limit | Varied openings and endings |
| Examples | Examples invited copying | Header says quality bar, not template |
| Disclosure | The same bias apology in most phrases | 26 variants, apology optional |
| Disclosure | Four phrases failed the affiliation detector | Detector fixed, test added |
| Reddit voice | "Short version:" listed as a good opener | Removed, label rule added |
| Generator prompt | Examples and recent replies without a copy warning | Notes added, openings and endings must change |
| Reasons | Open wording in qualification and engagement reasons | One plain sentence, one fact |

## What the linter cannot judge

It cannot check that a reply answers the question, that a number is true or that the tone suits the thread. The verifier and the editor check grounding. The owner reads every reply before it posts.

## Open items

- The warnings are heuristics. `no_specific_detail` can misfire for owners who write names in lowercase; it is skipped when the voice card shows mostly lowercase sentences.
- A model can still copy an example's shape. The prompt forbids it and the `too_similar` check compares against recent replies, but a test against a live model is needed to measure it.
