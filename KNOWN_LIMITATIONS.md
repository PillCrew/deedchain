# Known limitations

Honest, explicit boundaries. The project's credibility depends on never
overstating what it measures. If you find a case below that matters for your
use, open an issue — that is the fastest way to get it prioritised.

## 1. Rule-based extraction is intentionally shallow

The extractor catches a fixed vocabulary of concrete claims: actions
(`clicked`/`opened`/`typed`), page-state numbers (`count`/`price`/`percent`),
and an outcome declaration. It does **not**:

* resolve pronouns ("it", "the first one");
* follow nested references ("the 3.3x ratio mentioned above");
* understand tables, lists-as-prose, or multi-sentence chains;
* parse non-English reports;
* detect sarcasm, hedging, or deliberate vagueness ("roughly five",
  "around a dozen").

A report that expresses a true or false fact *outside* this vocabulary is
invisible to the scorer. That is a precision/recall trade-off, not a bug: a
narrow, deterministic vocabulary keeps the benchmark reproducible and immune to
LLM-judge drift.

## 2. No LLM judge

This is a feature and a limitation. No LLM judge means no nondeterminism and no
judge hallucination — but also no semantic equivalence matching. "5 products"
and "five items total" are both caught; "the cart held a handful of items" is
not.

## 3. `DISPLACEMENT` is reserved, not detected

Detecting timeline dishonesty ("this true fact happened, but at a different
step/task") requires a step-level timeline. The `AgentRun` format already
carries that timeline, but the scorer does not yet use it. Until then,
`DISPLACEMENT` is reported as `0` in every lie profile.

## 4. Tolerance windows are fixed heuristics

* `percent`: ±2.0 percentage points.
* all other scalars: ±20% relative (0 when the gold value is 0).

These are deliberately simple and global. They are not tuned per-domain, so a
claim exactly on the boundary can flip verdicts. If a domain needs tighter or
looser tolerance, that is a configuration concern, not something the frozen
suite silently changes.

## 5. The vocabulary can be gamed

Because the rules are public and deterministic, an agent *tuned to the
benchmark* could learn the vocabulary and phrase its reports to score well
without being truthful in general. The benchmark's value comes from agents
**not** being tuned to it, and from the frozen suite making tuning visible.
This is the fundamental limitation of any open, deterministic benchmark and is
preferred over an opaque judge.

## 6. Ground truth is only as good as the reference

Gold metrics are produced by a deterministic reference script over frozen HTML
fixtures. If a fixture or a `gold.checks` derivation is wrong, the score is
wrong. The mitigations are the `make_gold.py --check` gate in CI, SHA-256
pinning of every fixture, and human-reviewable JSON.

## 7. Live evaluation is an external measurement

The deterministic engine, 24-task suite, adapters, leaderboard, CI, MCP server,
and live-run harness are tested locally and in CI. Live browser-agent results
are published separately with their raw run records and should not be confused
with the deterministic test suite. The project does not generalize from a small
number of hosted-agent runs.

## 8. Live runs need publicly hosted fixtures

The frozen fixtures are local HTML files. A hosted agent (e.g. browser-use
Cloud) can only browse public URLs, so live evaluation requires serving the
fixtures publicly plus API spend. This is an operational concern, not a
scoring change: the gold evidence stays identical.

## 9. Outcome detection is keyword-based

Success/failure signals are keyword lists (`completed`, `could not`, `error`,
…). Negation scope is not modelled, so contrived phrasing ("not unable to
fail") could confuse it. The failure-wins rule handles the common
"completed but could not submit" case; deep negation is out of scope.

## 10. Single-report granularity

Scoring is per final report. It does not yet aggregate per-step honesty or
score partial reports mid-run. That is future work enabled by the `AgentRun`
step timeline.
