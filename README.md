# DealLens

DealLens is a focused prototype that turns an acquirer's and a target's public
documents (annual reports, investor presentations, financial statements) into a
cited, structured value-creation analysis: company profiles, strategic
rationale, revenue and cost synergy opportunities, a risk register, a 100-day
integration plan, and an executive summary — every factual claim tagged as a
documented fact, a calculated result, an assumption, or a hypothesis.

Demo case: **Amazon's 2017 acquisition of Whole Foods Market**, using simplified
synthetic documents in [`sample_data/`](sample_data/) (not the real filings — see
that folder's README) so the output can be sanity-checked against what actually
happened post-close.

## The business problem

Early-stage M&A value-creation analysis is slow, manual, and hard to audit:
analysts read hundreds of pages of filings to build company profiles, then hand-
build synergy estimates in spreadsheets that mix documented facts, back-of-
envelope math, and outright guesses with no clear separation between them. DealLens
automates the first pass — extraction, baseline calculation, opportunity
generation, integration planning — while keeping every claim traceable to either
a source citation or an explicit, stated assumption, so a human reviewer knows
exactly what to diligence further.

## What the agent does

Given an acquirer name, a target name, and uploaded documents (plus optional
transaction assumptions), it produces:

1. Company profiles (business description, financials, segments)
2. Strategic rationale for the acquisition
3. Revenue opportunities
4. Cost-saving opportunities
5. Operational and organizational risks
6. Preliminary financial scenarios (low / base / high)
7. A 100-day integration plan
8. An executive summary with citations

## How the workflow operates

The pipeline is a sequence of discrete stages, each callable independently from
the Streamlit app — not a black-box multi-agent loop:

```
User uploads documents
        |
Agent identifies available information       (agent/researcher.py)
        |
Document Researcher extracts profiles + rationale, with citations
        |
[ USER APPROVES ASSUMPTIONS ]                 (gate before any financial scenario math)
        |
Financial tool calculates baseline metrics    (agent/value_creation.py + tools/financial_calculator.py)
        |
Value Creation Analyst develops opportunities (agent/value_creation.py)
        |
Integration Planner builds risk register + 100-day plan  (agent/integration_planner.py)
        |
Reviewer checks claims, citations, and calculations       (agent/reviewer.py)
        |
Final report generated with executive summary  (tools/report_generator.py)
```

`agent/orchestrator.py` wires these together; each function takes and returns
an `AnalysisRecord`, so the Streamlit app can run one stage, show its output,
and let the user proceed (or stop) before the next.

## Tools the agent can call

Implemented in [`tools/financial_calculator.py`](tools/financial_calculator.py)
and [`agent/researcher.py`](agent/researcher.py), exposed to the model as
OpenAI Responses API function tools:

- `calculate_growth_rate` — CAGR between two values
- `calculate_margin` — operating/gross margin from revenue and profit
- `calculate_savings_scenario` — low/base/high cost synergy from a cost base + reduction assumptions
- `calculate_revenue_scenario` — low/base/high revenue synergy from a revenue base + uplift assumptions
- `calculate_combined_metric` — pro-forma combined metric with an optional synergy/dis-synergy adjustment
- `search_uploaded_documents` — semantic search over the uploaded documents (via the vector store), so later stages can pull evidence without re-running full file_search
- `save_analysis` / `load_analysis` — SQLite persistence ([`db/database.py`](db/database.py))
- `generate_report` — assembles the final cited Markdown report ([`tools/report_generator.py`](tools/report_generator.py))

The model is instructed to never do arithmetic in prose — every numeric
estimate must come from a logged tool call, which the reviewer stage then
independently re-checks (see below).

## Structured outputs and claim classification

Every extracted fact and every proposed opportunity is a Pydantic model
(`schemas/analysis_models.py`) with an explicit `claim_type`:

- `documented_fact` — directly supported by a citation
- `calculated_result` — produced by a `financial_calculator` tool call
- `assumption` — explicitly provided by the user or stated by the agent for scenario analysis
- `hypothesis` — requires further diligence, no citation or calculation behind it yet

`ValueOpportunity` objects also carry `estimated_value.{low,base,high}`,
`assumptions`, `key_risks`, `implementation_difficulty`, `time_horizon`, and
`calculation_method` — see [`example_outputs/sample_opportunity.json`](example_outputs/sample_opportunity.json)
for the full shape.

## The reviewer stage

[`agent/reviewer.py`](agent/reviewer.py) is deterministic Python, not another
LLM call grading itself. `review_analysis()` rejects or flags:

- **Missing citations** — any `documented_fact` or `calculated_result` claim without one
- **Incorrect calculations** — cross-checks each opportunity's reported value against the actual logged `financial_calculator` tool call output
- **Assumptions presented as facts** — flags `documented_fact` claims containing hedging language ("assume," "approximately," "likely," ...)
- **Duplicate recommendations** — title-similarity check across opportunities
- **Unrealistically precise estimates** — flags dollar figures with more significant figures than diligence-stage analysis supports
- **Recommendations unrelated to the supplied documents** — flags opportunities with no citation to an uploaded document

It also reports `citation_coverage_pct` and a `claim_type_coverage` breakdown,
which feed the evaluation metrics below.

## How it was tested

- `tests/test_financial_calculator.py` — unit tests for every calculation
  function (CAGR, margins, savings/revenue scenarios, combined metrics, the
  false-precision flag), including boundary/error cases. No API key required.
- `tests/test_reviewer.py` — unit tests for the reviewer against synthetic
  `AnalysisRecord` objects: missing citations, calculation mismatches,
  duplicate opportunities, false precision, citation-coverage percentage, and
  document-grounding. No API key required.

Run them with:

```bash
pytest
```

**Not yet done** (see Known limitations): an end-to-end evaluation of the live
LLM stages (researcher, value-creation analyst, integration planner) against
the three-sample-transaction methodology described in the project brief —
percentage of claims with valid citations *in a real run*, calculation
accuracy *in a real run*, run-to-run consistency, and whether major risks are
identified. Those numbers require actually invoking the OpenAI Responses API
and are not included here until measured.

## Known limitations

- **No end-to-end run has been evaluated yet.** The reviewer, calculator, and
  schemas are unit-tested; the LLM stages (researcher/analyst/planner) have not
  been run and scored against real output. Do not treat any citation-accuracy
  or calculation-accuracy figure as measured until this has been done and this
  README updated with the result — see `example_outputs/README.md`.
- **Sample documents are synthetic**, not real SEC filings, so citations point
  at a simplified demo document rather than an actual annual report. Swap in
  real filings for a production-quality run (see `sample_data/README.md`).
- **Single-pass reviewer.** The reviewer flags issues but the pipeline does not
  currently loop back to have the agent auto-fix a failed check — a human (or a
  second orchestrator pass) has to act on the flagged issues.
- **No PDF-specific extraction tuning.** File search handles PDFs via OpenAI's
  built-in parsing; scanned/image-only PDFs or complex tables may extract
  poorly without additional preprocessing.
- **No authentication, multi-user support, or rate limiting** — this is a
  single-user local prototype.
- **Cost/latency**: each full run makes on the order of 10-15 Responses API
  calls (profiles, rationale, baseline, two opportunity batches, risks, plan,
  executive summary) plus tool-calling round trips; there's no caching between
  runs of the same documents yet.

## How to run

```bash
git clone <this-repo>
cd deallens
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_API_KEY
export $(cat .env | xargs)
streamlit run app.py
```

Then, in the app: **1. Create Analysis** (keep the bundled sample documents
checked, or upload your own) → **2. Evidence** (review extracted facts, approve
assumptions) → **3. Value Creation** (run baseline + opportunities) →
**4. 100-Day Plan** (run risk register, plan, reviewer, executive summary, and
download the final report).

Run tests any time (no API key needed) with `pytest`.

## What a production version would add

- An orchestrator loop where the reviewer's flagged issues are fed back to the
  relevant stage for one automatic revision pass before reaching the user.
- Real evaluation harness: three sample transactions with human-authored
  "gold" outputs, scored automatically for citation validity and calculation
  accuracy on every CI run.
- Multi-user auth, persistent document storage, and audit logging of every
  tool call and model response (not just the in-session tool-call log).
- Support for structured financial statement ingestion (XBRL) instead of
  relying solely on file-search-over-PDF extraction.
- Versioned re-runs so a user can adjust one assumption and see which
  downstream opportunities/plan items change, without re-running the whole
  pipeline.
