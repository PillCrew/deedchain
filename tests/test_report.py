"""Tests for claim extraction (deedchain.report)."""

from deedchain.report import (
    ACTION,
    OUTCOME,
    STATE,
    METRIC_CLICKED,
    METRIC_COUNT,
    METRIC_OPENED,
    METRIC_OUTCOME,
    METRIC_PERCENT,
    METRIC_PRICE,
    METRIC_TYPED,
    extract_claims,
)


def _by_metric(report):
    claims = extract_claims(report)
    return {m: [c for c in claims if c.metric == m] for m in {c.metric for c in claims}}


def test_extracts_action_targets():
    grouped = _by_metric("I clicked the top story and opened item 42.")
    assert len(grouped[METRIC_CLICKED]) == 1
    assert grouped[METRIC_CLICKED][0].value == "the top story"
    assert grouped[METRIC_CLICKED][0].kind == ACTION
    assert len(grouped[METRIC_OPENED]) == 1
    assert grouped[METRIC_OPENED][0].value == "item 42"


def test_extracts_numeric_state():
    grouped = _by_metric("Found 9 products, price $12.00, up 3.5%.")
    assert grouped[METRIC_COUNT][0].value == 9.0
    assert grouped[METRIC_PRICE][0].value == 12.0
    assert grouped[METRIC_PERCENT][0].value == 3.5
    assert all(c.kind == STATE for c in grouped[METRIC_COUNT])


def test_outcome_success():
    claims = extract_claims("The task was completed successfully.")
    outcomes = [c for c in claims if c.kind == OUTCOME]
    assert len(outcomes) == 1
    assert outcomes[0].metric == METRIC_OUTCOME
    assert outcomes[0].value is True


def test_outcome_failure_wins_over_success():
    claims = extract_claims("It completed but I could not submit the form.")
    outcomes = [c for c in claims if c.kind == OUTCOME]
    assert len(outcomes) == 1
    assert outcomes[0].value is False


def test_no_outcome_when_no_signal():
    claims = extract_claims("I looked at the page.")
    assert all(c.kind != OUTCOME for c in claims)


def test_does_not_swallow_conjunction_into_action_target():
    grouped = _by_metric("I clicked the login button and logged in.")
    assert grouped[METRIC_CLICKED][0].value == "the login button"


def test_action_target_stops_at_into():
    grouped = _by_metric("I typed Alice into the name field.")
    assert grouped[METRIC_TYPED][0].value == "Alice"


def test_extracts_count_words_links_paragraphs_headings():
    grouped = _by_metric(
        "The page has 9 links, 2 paragraphs and 1 heading."
    )
    values = [c.value for c in grouped[METRIC_COUNT]]
    assert values == [9.0, 2.0, 1.0]


def test_bare_number_report_is_count():
    grouped = _by_metric("9")
    assert grouped[METRIC_COUNT][0].value == 9.0
    assert grouped[METRIC_COUNT][0].kind == STATE


def test_bare_number_with_markdown_and_punctuation():
    assert _by_metric("**24**")[METRIC_COUNT][0].value == 24.0
    assert _by_metric("`33`.")[METRIC_COUNT][0].value == 33.0
