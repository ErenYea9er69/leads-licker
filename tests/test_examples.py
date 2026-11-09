"""Every good example reply passes the linter and every bad one fails it."""

from __future__ import annotations

from agent_reach.discovery import skillpack, voice
from agent_reach.discovery.models import ReplyPreferences


def test_examples_against_the_linter():
    prefs = ReplyPreferences()
    examples = skillpack.examples()
    assert examples
    for ex in examples:
        kind = "product_aware" if ex.level >= 2 else "value_first"
        assert voice.lint_reply(ex.good, kind=kind, product_name="Tidewatch", prefs=prefs, level=ex.level).passed, ex.title
        bad_kind = "product_aware" if "Tidewatch" in ex.bad else "value_first"
        assert not voice.lint_reply(ex.bad, kind=bad_kind, product_name="Tidewatch", prefs=prefs, level=ex.level).passed, ex.title
