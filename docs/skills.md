# Working with the skills

The skill pack in `skills/` is the single source of rules for the pipeline and the MCP server. The pipeline injects the short block between `<!-- prompt:start -->` and `<!-- prompt:end -->` into its prompts. The MCP server serves the whole file and its references.

## Layout

```
skills/NAME/SKILL.md            frontmatter, the prompt block, notes for people
skills/NAME/references/*.md     longer material a host AI reads when the situation needs it
skills/manifest.json            names, versions and content hashes (generated)
```

Frontmatter fields: `name`, `description`, `version`, `stage` (router, profile, search, qualify, engage, write, safety), `used_by`, `references`.

## Change a skill

1. Edit the file.
2. Run `python scripts/validate_skills.py --write`. It checks the structure, rejects em and en dashes, checks every `reach_` and `ceo_` tool name against the server, runs every example through the linter and rewrites the manifest.
3. If you changed a tool, run `python scripts/gen_tool_reference.py`.
4. Bump the skill's `version`.

To use a private copy without touching the package, set `AGENT_REACH_SKILLS_DIR` to your folder.

## Teach it your voice

Voice cloning measures habits. It does not copy sentences.

```
agent-reach discovery voice --from-account reddit:your_handle     # your own public comments
agent-reach discovery voice --file my_comments.txt                # blocks separated by a blank line
agent-reach discovery voice --show
```

Ten or more samples give a reliable card: reply length, sentence length and spread, lowercase starts, contractions and missing apostrophes, question, exclamation, ellipsis, emoji and parenthesis rates, hedges such as "imo", common openers and closers. The prompt includes the card and three typical samples. The linter scores each draft against the card and warns below 60.

## Banned words

`skills/community-copywriting/references/banned-ai-tells.txt` holds words and phrases that mark generated text. `banned-user-list.txt` holds the owner's personal list. Each line is `tier|term`. Tier `hard` blocks a draft. Tier `avoid` allows up to two per reply (`avoid_budget`). Add your own:

```
agent-reach discovery prefs --ban "synergy,circle back"
agent-reach discovery prefs --strict-avoid yes     # treat the avoid tier as hard
agent-reach discovery prefs --user-list off        # skip the personal list
```

The lists target English. The trade-off: a long hard list keeps replies clean but forces plainer wording, and a model may need two or three tries. The generator retries up to three times and then flags the draft for your edit.

## Examples

`references/examples.md` holds paired good and bad replies. The first is a model for the generator. The second proves the linter catches the failure. Add examples as you find new failures.
