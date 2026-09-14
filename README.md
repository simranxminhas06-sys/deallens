# DealLens

DealLens turns an acquirer's and a target's public documents (annual reports,
investor presentations, financial statements) into a cited, structured
value-creation analysis — and, instead of one agent writing one report, three
specialized agents examine the deal from competing angles and argue about it:

- **Strategy Agent** — tests the acquisition rationale, market attractiveness, growth case
- **Financial Agent** — extracts figures, builds low/base/high scenarios, calculates synergies
- **Red-Team Agent** — argues against the deal, hunts for unsupported claims, challenges the other two agents by name

Every factual claim is tagged as a documented fact, a calculated result, an
assumption, or a hypothesis, and a deterministic reviewer stage independently
re-checks citations and calculations rather than trusting the agents' own
self-report.

**Try it with no API key and no cost**: pick "Demo (no API key)" in the
sidebar and click "Load demo case" — it runs the full pipeline, independent
assessments included, against a hand-authored Amazon/Whole Foods fixture
(`agent/demo_fixtures.py`). "Live (OpenAI)" mode runs the same pipeline for
real against uploaded documents, optionally supplemented by live web search
for public company background (see "Researching without uploaded documents"
below).

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

Given an acquirer name, a target name, and either uploaded documents or live
web search (plus optional transaction assumptions), it produces:

1. Company profiles (business description, financials, segments)
2. Strategic rationale for the acquisition
3. A three-agent independent assessment: Strategy's case, Financial's numbers, Red-Team's challenges to both
4. Revenue and cost-saving opportunities (from the Financial Agent, with low/base/high scenarios)
5. Operational and organizational risks
6. A 100-day integration plan
7. An executive summary with citations

## How the workflow operates

The pipeline is a sequence of discrete stages, each callable independently from
the Streamlit app — not a black-box multi-agent loop:

```
User uploads documents and/or enables live web search
        |
Agent identifies available information (documents only)  (agent/researcher.py)
        |
Researcher extracts profiles + rationale, with citations
        |
[ USER APPROVES ASSUMPTIONS ]                 (gate before any financial scenario math)
        |
INDEPENDENT ASSESSMENTS:
  Strategy Agent assesses the rationale        (agent/strategy_agent.py)
  Financial Agent computes baselines + opportunities with financial_calculator (agent/financial_agent.py)
  Red-Team Agent challenges both by name, citing evidence gaps  (agent/red_team_agent.py)
        |
Integration Planner builds risk register + 100-day plan  (agent/integration_planner.py)
        |
Reviewer checks claims, citations, and calculations       (agent/reviewer.py)
        |
Final report generated with executive summary  (tools/report_generator.py)
```

`agent/orchestrator.py` wires these together; each function takes and returns
an `AnalysisRecord`, so the Streamlit app can run one stage, show its output,
and let the user proceed (or stop) before the next. The three assessment
agents are separate Responses API calls with separate instructions/roles — deliberately
built on the same primitives as the rest of the pipeline (structured outputs +
function calling + file_search) rather than a separate agent framework, so the
whole system stays in one mental model.

## Researching without uploaded documents

Re-uploading the same background documents for every analysis gets old fast,
so the Create Analysis page has an "Also use live web search for public
company background" option (`{"type": "web_search"}` on the Responses API,
wired up in `agent/researcher.py` / `agent/llm.py`). It applies only to
company profiles and strategic rationale — the two research-stage outputs
that are naturally public information:

- With it on and documents uploaded, the Researcher draws on both, preferring
  the uploaded documents when they cover the same fact.
- With it on and no documents uploaded, company profiles and strategic
  rationale run entirely from the web — no upload required.
- Citations from the web carry a `source_url` (rendered as a link on the
  Evidence page) instead of a document name + page reference.

Deal-specific evidence stays document-only by design: the Financial Agent's
opportunities and the reviewer's document-grounding check
(`agent/reviewer.py::_check_document_grounding`) both require an uploaded
document set, so Independent Assessments and the 100-Day Plan still need
`vector_store_id` set — i.e., at least one uploaded document — even when web
search is enabled. This keeps financial claims traceable to something the
user actually supplied, in line with the project's evidence-discipline rules,
while removing the busywork from the parts of the analysis that are just
public company background.

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

## Independent assessments

Rather than one agent producing one blended narrative, three agents assess
the deal independently and then argue about it — this is the defining
structural choice of the product, not UI dressing:

- `agent/strategy_agent.py` — market attractiveness, whether the stated rationale holds up, growth case, competitive comparison
- `agent/financial_agent.py` — wraps `agent/value_creation.py`'s baseline + opportunity generation, then writes a position paragraph that names its own weakest estimate
- `agent/red_team_agent.py` — searches the documents to check whether the other two agents' claims are actually supported, then issues `Challenge` objects naming exactly which agent and which claim/opportunity title it's disputing — plus a deterministic pass that reuses the reviewer's own precision/citation heuristics, so Red-Team catches what a spreadsheet-literal check catches, not just what reads persuasively

Each `AgentAssessment` (`schemas/analysis_models.py`) carries a one-paragraph
`position` (the debate line you see in the UI), cited `key_findings`, and
either `opportunities` (Financial) or `challenges` (Red-Team). The Streamlit
"Independent Assessments" page renders these as a chat transcript.

## The reviewer stage

[`agent/reviewer.py`](agent/reviewer.py) is deterministic Python, not another
LLM call grading itself. `review_analysis()` rejects or flags:

- **Missing citations** — any `documented_fact` or `calculated_result` claim without one
- **Incorrect calculations** — cross-checks each opportunity's reported value against the actual logged `financial_calculator` tool call output
- **Assumptions presented as facts** — flags `documented_fact` claims containing speculative language ("assume," "likely," "projected," ...) — deliberately excludes "approximately"/"estimated," which are normal in a company's own rounded, audited figures and would otherwise false-positive on legitimate facts
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
- `tests/test_demo_mode.py` — runs the full fixture-based pipeline
  (`agent/demo_fixtures.py`) end to end and asserts: all three war-room agents
  are present, Red-Team actually challenges the Financial Agent, the real
  reviewer flags the deliberately under-evidenced opportunity, the
  cost-synergy calculation is *not* flagged, and two runs are byte-identical
  (no hidden randomness). No API key required — this is the fastest way to
  sanity-check the whole system after a change.

Run them with:

```bash
pytest
```

**Not yet done** (see Known limitations): an end-to-end evaluation of the live
LLM stages (researcher, war-room agents, integration planner) against the
three-sample-transaction methodology described in the project brief —
percentage of claims with valid citations *in a real run*, calculation
accuracy *in a real run*, run-to-run consistency, and whether major risks are
identified. Those numbers require actually invoking the OpenAI Responses API
and are not included here until measured.

## Known limitations

- **Demo mode is a fixture, not evidence of live accuracy.** It proves the
  data model, war-room wiring, and reviewer logic are internally consistent —
  it says nothing about how well the live LLM agents will actually perform
  against real documents.
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
streamlit run app.py
```

That's enough to try **Demo mode** — no API key, no cost. In the sidebar,
keep "Demo (no API key)" selected, go to **1. Create Analysis**, and click
"Load demo case." Then browse **2. Evidence**, **3. Independent Assessments**
(the debate transcript), and **4. 100-Day Plan** (risk register, plan, reviewer
findings, executive summary, and a downloadable report) — everything is
already populated.

For a **live run** against real OpenAI calls: switch the sidebar to "Live
(OpenAI)", set `OPENAI_API_KEY` in your environment first —

```bash
cp .env.example .env   # add your OPENAI_API_KEY
export $(cat .env | xargs)
streamlit run app.py
```

— then work through the same four pages: **1. Create Analysis** (keep the
bundled sample documents checked, or upload your own) → **2. Evidence**
(review extracted facts, approve assumptions) → **3. Independent Assessments**
(run Strategy → Financial → Red-Team) → **4. 100-Day Plan** (run risk register,
plan, reviewer, executive summary, and download the report).

Run tests any time (no API key needed) with `pytest`.

## Roadmap

Staged so each piece is working before the next is added:

1. ✅ Strategy, Financial, and Red-Team agents debating in Independent Assessments, with a no-API-key demo mode (this version).
2. **Investment Committee Agent** — reviews the three assessments, explains where they disagree, and issues a Proceed / Proceed with conditions / Further diligence / Do not proceed verdict.
3. **Interactive scenario simulator** — sliders for purchase price, growth/synergy assumptions, implementation cost, time-to-synergy, and churn, that re-run the Financial and Red-Team agents against the changed inputs.
4. **Evidence graph** — a clickable Recommendation → Claim → Calculation/Assumption → Source-document-and-page view (the data already exists in `EvidenceItem`/`Citation`; this is a UI addition).
5. **Operations, Customer, and People & Change agents** — supply-chain/duplicated-function analysis, cross-sell/cannibalization analysis, and org/culture risk + change-management planning, each following the same `AgentAssessment` pattern as Strategy/Financial/Red-Team.
6. **Partner Challenge Mode** — a Q&A screen that scores the user's own defense of the analysis (structure, evidence use, quantitative reasoning) after they've seen it.

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
