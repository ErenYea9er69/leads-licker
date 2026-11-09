"""Linter behavior for AI-slop patterns in reply drafts."""

from __future__ import annotations

import pytest

from agent_reach.discovery import skillpack, voice
from agent_reach.discovery.models import ReplyPreferences

BASE = "Send the note on the due date with the invoice number and the amount in it. I did that for 6 clients and it cut my chasing a lot."


def codes(text: str, **kw) -> set:
    kw.setdefault("kind", "value_first")
    kw.setdefault("product_name", "Tidewatch")
    kw.setdefault("level", 0)
    report = voice.lint_reply(text, prefs=ReplyPreferences(), **kw)
    return {i.code for i in report.issues}


def error_codes(text: str, **kw) -> set:
    kw.setdefault("kind", "value_first")
    kw.setdefault("product_name", "Tidewatch")
    kw.setdefault("level", 0)
    return {i.code for i in voice.lint_reply(text, prefs=ReplyPreferences(), **kw).errors}


def test_clean_reply_has_no_errors():
    assert error_codes(BASE) == set()


@pytest.mark.parametrize(
    "word",
    ["unlocked", "discovering", "illuminating", "harnesses", "unveiled", "utilizes", "delved", "imagining", "remarkably", "embarked"],
)
def test_inflected_banned_words_are_caught(word):
    assert "banned_word" in error_codes(f"We {word} the invoice list and sent the note on the due date with the amount in it for every client.")


def test_inflection_does_not_match_unrelated_words():
    assert voice.find_terms("The discovery call went fine, and the keyboard was loud.", ["discover", "key"]) == []


@pytest.mark.parametrize(
    "text",
    [
        "Send one note per invoice - then wait a week before the next one goes out, and keep the wording flat for every client.",
        "Send one note per invoice -- then wait a week before the next one goes out, and keep the wording flat for every client.",
    ],
)
def test_spaced_hyphen_counts_as_a_dash(text):
    assert "dash" in error_codes(text)


def test_normalize_text_replaces_spaced_hyphen():
    out = voice.normalize_text("Send one note per invoice - then wait a week.")
    assert " - " not in out


def test_range_and_compound_words_are_not_dashes():
    assert "dash" not in error_codes("The follow-up goes out in 3-5 days. Keep a run-of-the-mill template and send it on the due date with the amount.")


@pytest.mark.parametrize(
    "text, code",
    [
        ("It's not about the tool, it's about the habit of sending the note on a fixed day each week without fail.", "contrast_frame"),
        ("This is not just a reminder tool but a whole system for getting paid on time every month, with notes sent on the due date.", "contrast_frame"),
        ("Here's why it works. Send the note on the due date with the invoice number and the amount in it, then wait a week.", "lead_in"),
        ("The catch: send the note on the due date with the invoice number and the amount in it, then wait a week.", "lead_in"),
        ("I completely understand how frustrating that is. Send the note on the due date with the invoice number and the amount.", "empathy_script"),
        ("Send the note on the due date with the invoice number and the amount in it, then wait a week. What do you think?", "closing_question"),
        ("Hey! Send the note on the due date with the invoice number and the amount in it, then wait a week before the next one.", "greeting_opener"),
        ("Great question. Send the note on the due date with the invoice number and the amount in it, then wait a week.", "flattery_opener"),
    ],
)
def test_slop_frames_are_errors(text, code):
    assert code in error_codes(text)


def test_greeting_allowed_when_owner_voice_uses_it():
    prefs = ReplyPreferences(voice_card={"top_openers": ["hey"]})
    report = voice.lint_reply(
        "Hey, send the note on the due date with the invoice number and the amount in it, then wait a week.",
        kind="value_first",
        product_name="Tidewatch",
        prefs=prefs,
        level=0,
    )
    assert "greeting_opener" not in {i.code for i in report.issues}


def test_structure_warnings_do_not_block():
    text = (
        "Send notes, set dates, and track replies. Pick a tool, a sheet, or a calendar. "
        "Most clients are busy, not rude. It's slow, not hard. Maybe it might perhaps work."
    )
    found = codes(text)
    assert {"stacked_triples", "mirror_contrast"} <= found
    assert error_codes(text) & {"stacked_triples", "mirror_contrast"} == set()


def test_all_example_replies_keep_their_verdict():
    prefs = ReplyPreferences()
    for ex in skillpack.examples():
        kind = "product_aware" if ex.level >= 2 else "value_first"
        good = voice.lint_reply(ex.good, kind=kind, product_name="Tidewatch", prefs=prefs, level=ex.level)
        assert not good.errors, (ex.title, [i.code for i in good.errors])
        assert not good.issues, (ex.title, [i.code for i in good.issues])


def test_every_disclosure_phrase_counts_as_affiliation():
    for phrase in skillpack.disclosure_phrases():
        assert voice.has_affiliation(phrase.replace("{product}", "Tidewatch")), phrase
