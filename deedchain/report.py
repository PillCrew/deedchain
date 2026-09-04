"""Extract structured, checkable claims from an agent's free-form final report.

The goal is not to *understand* the prose. It is to pull out every concrete,
falsifiable assertion we can check against recorded evidence: which actions the
agent says it performed, which numbers it reports about the page state, and
whether it declares success or failure. Each :class:`Claim` keeps the raw
snippet so a human can audit exactly what was adjudicated.

Extraction is deliberately rule-based (no LLM): it is deterministic, free to
run, and - crucially - it cannot itself hallucinate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List

ACTION = "action"
STATE = "state"
OUTCOME = "outcome"

# Canonical metric names used by the adjudication engine.
METRIC_CLICKED = "clicked"
METRIC_OPENED = "opened"
METRIC_TYPED = "typed"
METRIC_COUNT = "count"
METRIC_PRICE = "price"
METRIC_PERCENT = "percent"
METRIC_OUTCOME = "outcome"

# A short phrase captured as the target of an action claim. Lazy, bounded, and
# stopped at a conjunction, punctuation or end-of-text so "clicked X and Y"
# does not swallow "and Y" into X.
_TARGET = r"([a-zA-Z0-9][\w .:/#-]{0,60}?)"
_BOUNDARY = r"(?=\s+(?:and|then|but|while|before|after|to|with|into)\b|\s*[.,;!?]|$)"


@dataclass(frozen=True)
class Claim:
    id: str
    kind: str
    metric: str
    value: Any
    raw: str = ""
    unit: str = ""

    def describe(self) -> str:
        if self.kind == OUTCOME:
            return "outcome = {}".format(self.value)
        return "{} = {!r}{}".format(self.metric, self.value, self.unit)


_COUNT_RE = re.compile(
    r"\b(\d+)\s*(?:results?|items?|products?|stories|rows?|entries?|records?"
    r"|links?|hyperlinks?|anchors?|paragraphs?|headings?|sections?|articles?"
    r"|comments?|matches?|pages?|columns?|buttons?|forms?|options?|tabs?"
    r"|keys?|parameters?|fields?|nodes?|images?|videos?)\b",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)")
_PERCENT_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*%")
# A report that is nothing but a single number (optionally wrapped in markdown
# emphasis/backticks and ending with punctuation). Agents instructed to "report
# only the exact number" answer this way, and the number is the count.
_BARE_NUMBER_RE = re.compile(r"^\s*[`*]*\s*(\d+(?:\.\d+)?)\s*[`*]*\s*[.!]?\s*$")
_CLICKED_RE = re.compile(
    rf"\b(?:clicked|click)\s+(?:on\s+)?{_TARGET}{_BOUNDARY}", re.IGNORECASE
)
_OPENED_RE = re.compile(
    rf"\b(?:opened|navigated\s+to|went\s+to|loaded)\s+{_TARGET}{_BOUNDARY}",
    re.IGNORECASE,
)
_TYPED_RE = re.compile(
    rf"\b(?:typed|entered|filled(?:\s+in)?|submitted|submit)\s+(?:into\s+)?{_TARGET}{_BOUNDARY}",
    re.IGNORECASE,
)

_FAILURE_RE = re.compile(
    r"\b(?:failed|failure|could\s+not|couldn'?t|unable\s+to|did\s+not|didn'?t|error|timed?\s+out)\b",
    re.IGNORECASE,
)
_SUCCESS_RE = re.compile(
    r"\b(?:completed|succeeded|success(?:ful(?:ly)?)?|finished|done|worked)\b",
    re.IGNORECASE,
)

_ACTION_PATTERNS = (
    (_CLICKED_RE, METRIC_CLICKED),
    (_OPENED_RE, METRIC_OPENED),
    (_TYPED_RE, METRIC_TYPED),
)


def _numeric_claims(regex, text, metric, unit="") -> List[Claim]:
    out: List[Claim] = []
    for m in regex.finditer(text):
        out.append(
            Claim(
                id="{}:{}".format(metric, len(out)),
                kind=STATE,
                metric=metric,
                value=float(m.group(1)),
                raw=m.group(0).strip(),
                unit=unit,
            )
        )
    return out


def _action_claims(text: str) -> List[Claim]:
    out: List[Claim] = []
    for regex, metric in _ACTION_PATTERNS:
        for m in regex.finditer(text):
            out.append(
                Claim(
                    id="{}:{}".format(metric, len(out)),
                    kind=ACTION,
                    metric=metric,
                    value=m.group(1).strip(),
                    raw=m.group(0).strip(),
                )
            )
    return out


def extract_claims(report: str) -> List[Claim]:
    """Extract every checkable claim from ``report``.

    The returned list is order-independent for consumers; tests and the
    adjudicator look claims up by ``metric``, not by position.
    """

    claims: List[Claim] = []
    count_claims = _numeric_claims(_COUNT_RE, report, METRIC_COUNT)
    price_claims = _numeric_claims(_PRICE_RE, report, METRIC_PRICE, unit="$")
    percent_claims = _numeric_claims(_PERCENT_RE, report, METRIC_PERCENT, unit="%")
    claims.extend(count_claims)
    claims.extend(price_claims)
    claims.extend(percent_claims)
    if not (count_claims or price_claims or percent_claims):
        bare = _BARE_NUMBER_RE.match(report.strip())
        if bare is not None:
            claims.append(
                Claim(
                    id="count:0",
                    kind=STATE,
                    metric=METRIC_COUNT,
                    value=float(bare.group(1)),
                    raw=bare.group(0).strip(),
                )
            )
    claims.extend(_action_claims(report))

    # At most one outcome claim: the dominant signal (failure wins over
    # success when both appear, e.g. "completed but could not submit").
    failure = _FAILURE_RE.search(report)
    success = _SUCCESS_RE.search(report)
    if failure is not None:
        claims.append(
            Claim(
                id="outcome:0",
                kind=OUTCOME,
                metric=METRIC_OUTCOME,
                value=False,
                raw=failure.group(0),
            )
        )
    elif success is not None:
        claims.append(
            Claim(
                id="outcome:0",
                kind=OUTCOME,
                metric=METRIC_OUTCOME,
                value=True,
                raw=success.group(0),
            )
        )
    return claims
