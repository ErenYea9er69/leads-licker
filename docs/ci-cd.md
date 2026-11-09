# CI/CD

One workflow lives in `.github/workflows/ci.yml`. It uses only first-party actions.

## ci.yml (push to main, every pull request)

| Job | What it checks |
| --- | --- |
| lint | ruff on the package, scripts and tests. mypy on the discovery, MCP and team code |
| skills | `validate_skills.py` and `gen_tool_reference.py --check` |
| test | pytest on Python 3.10, 3.12 and 3.13, each against MCP SDK 1.x and 2.x (6 runs) |
| package | builds the wheel, installs it in a clean virtualenv, runs the CLI, loads all tools and checks that company mode hides the specialist tools |
| workflows | actionlint on the workflow files |
| docker | builds the image and checks that `agent-reach mcp` answers an MCP `initialize` request |

`package` and `docker` run after lint, skills and test pass. A new run for the same branch cancels the old one.

## Local equivalents

```
ruff check agent_reach scripts tests
mypy agent_reach/discovery agent_reach/mcp agent_reach/team
pytest
python scripts/validate_skills.py
python scripts/gen_tool_reference.py --check
python -m build && pip install dist/*.whl
```

## Not exercised

The Docker steps were not run where this workflow was written (no Docker daemon). Run `ci.yml` once on a branch before relying on it.

## Not included

There is no release or canary workflow. Add them when you publish the package. A weekly job that runs `agent-reach discovery check llm` with a repository secret is worth adding: model names retire often.
