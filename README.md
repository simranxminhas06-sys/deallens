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
sidebar and click either "Load demo case" button — each runs the full
pipeline, independent assessments included, against a hand-authored fixture
(`agent/demo_fixtures.py`). "Live (OpenAI)" mode runs the same pipeline for
real against uploaded documents, optionally supplemented by live web search
for public company background (see "Researching without uploaded documents"
below).

Two demo cases, deliberately different industries and outcomes so the tool
doesn't read as tuned to one story:

- **Amazon's 2017 acquisition of Whole Foods Market** — e-commerce acquiring
  grocery retail, using simplified synthetic documents in
  [`sample_data/`](sample_data/) (not the real filings — see that folder's
  README) so the output can be sanity-checked against what actually happened
  post-close. The revenue-synergy opportunity has no citation, so the
  reviewer flags it and the verdict lands on **Further diligence required**.
- **Pfizer's 2023 acquisition of Seagen** — large-cap pharma acquiring a
  clinical/commercial oncology biotech, a distinctly different value-creation
  story (talent-retention and regulatory risk instead of cultural/brand risk,
  R&D-platform economics instead of retail cost synergies). Its weak
  opportunity is grounded in a citation, so the review passes cleanly —
  Red-Team's objection to the assumed uplift rate is a real, separate basis
  for challenge, landing the verdict on **Proceed with conditions** instead.

The visual theme (white background, blue accent, IBM Plex Sans loaded via
Google Fonts) lives in [`.streamlit/config.toml`](.streamlit/config.toml) —
Streamlit's own theming API, not a CSS override — plus a small, deliberately
conservative CSS block at the top of `app.py` for the background wash, sidebar,
metric cards, headers, and buttons, targeting only `data-testid` attributes
(stable across Streamlit versions) rather than its internal hashed class
names. The verdict banner and evidence-type badges are custom-rendered (not
`st.success`/`st.warning`) so their colors are consistent with the theme
instead of Streamlit's default alert palette.

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
4. Revenue and cost-saving opportunities (from the Financial Agent, with low/base/high scenarios,
   a 3-year ramp to full run-rate, and a one-time cost to achieve)
5. Operational and organizational risks, scored by likelihood x impact
6. A 100-day integration plan
7. A sensitivity/tornado analysis and a combined downside/upside scenario
8. A rule-based Proceed / Proceed with conditions / Further diligence / Do not proceed verdict,
   comparing identified value creation against the deal's purchase price
9. An executive summary with citations

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
- `generate_report` — assembles the final cited Markdown report ([`tools/report_generator.py`](tools/report_generator.py)),
  also available as a PDF ([`tools/pdf_generator.py`](tools/pdf_generator.py)) or a 10-12 slide IC
  deck ([`tools/pptx_generator.py`](tools/pptx_generator.py)) — title, verdict banner, deal
  economics, company profiles, opportunity/risk tables, 100-day plan, and reviewer notes, styled
  to match the app's navy/blue theme and downloadable from Executive Summary. Deal teams hand
  slides upward, not PDFs, so this is the version someone would actually present.

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

## Sensitivity, scenarios, and the verdict

Three more deterministic, no-LLM stages sit on top of the opportunities the Financial Agent produces:

- **[`agent/sensitivity.py`](agent/sensitivity.py)** — `compute_tornado_rows()` swings one
  assumption at a time to its low/high bound (its own stated range for a synergy percentage, a
  default ±20% for a cost/revenue base or margin with no stated range), holding everything else
  fixed, and ranks assumptions by how much each one alone moves total value creation — the
  standard tornado chart. `compute_scenario_total()` is the combined companion: every assumption
  at its pessimistic (or optimistic) bound *simultaneously*, for a downside/upside case.
- **[`agent/verdict.py`](agent/verdict.py)** — a rule-based Proceed / Proceed with conditions /
  Further diligence required / Do not proceed verdict, built entirely from facts already in the
  record (the reviewer's high-severity issues, Red-Team's high-severity challenges, citation
  coverage, and value creation vs. deal value). Every reason cited traces to a specific
  `ReviewIssue` or `Challenge` — this is deliberately not another LLM call rendering an opinion,
  so it costs nothing and works in Demo mode.
- **`calculate_deal_economics()` and `calculate_ramp_adjusted_value()`** in
  [`tools/financial_calculator.py`](tools/financial_calculator.py) — the former compares total
  value creation against the deal's purchase price (captured on Create Analysis but otherwise
  unused elsewhere in the pipeline); the latter phases an opportunity's value in over three years
  and nets out a one-time cost to achieve it, instead of presenting a single undiscounted
  run-rate number.

All three are recomputed live wherever they're shown (the Sensitivity and Recommendation pages,
and the sidebar's "Live deal scorecard") rather than cached on the record, so dragging a scenario
assumption slider on Independent Assessments updates them immediately.

## Charts

Beyond the tornado chart above, three more Altair charts turn tabular data into the visuals a
deal team actually presents, all built in `app.py` directly from numbers already computed
elsewhere (no separate calculation to drift out of sync):

- **Value Creation Bridge** (Recommendation page) — a waterfall/bridge chart: cost synergies,
  then revenue synergies bridging up to total value creation, then a full total bar. The classic
  banking/consulting bridge chart for "where does this number come from."
- **3-Year Value Realization** (Independent Assessments page) — a stacked bar chart of revenue
  vs. cost synergy value by year, aggregated across every opportunity's `year_1_pct`/`year_2_pct`/
  `year_3_pct` ramp, showing when value creation actually lands rather than just its final total.
- **Risk Matrix** (Risk Register page) — the standard 3x3 likelihood × impact heat map. The grid
  itself is a static green/amber/red score backdrop; only cells holding a risk get a count label,
  so an empty cell reads as "no risk here," not as a rendering gap.

## How it was tested

- `tests/test_financial_calculator.py` — unit tests for every calculation
  function (CAGR, margins, savings/revenue scenarios, combined metrics, the
  false-precision flag), including boundary/error cases. No API key required.
- `tests/test_reviewer.py` — unit tests for the reviewer against synthetic
  `AnalysisRecord` objects: missing citations, calculation mismatches,
  duplicate opportunities, false precision, citation-coverage percentage, and
  document-grounding. No API key required.
- `tests/test_demo_mode.py` — runs the full fixture-based pipeline
  (`agent/demo_fixtures.py`) end to end and asserts: all three independent
  agents are present, Red-Team actually challenges the Financial Agent, the real
  reviewer flags the deliberately under-evidenced opportunity, the
  cost-synergy calculation is *not* flagged, and two runs are byte-identical
  (no hidden randomness). No API key required — this is the fastest way to
  sanity-check the whole system after a change.
- `tests/test_demo_mode_pfizer_seagen.py` — the same end-to-end checks against
  the second demo case, plus the assertions that make it a distinct case
  rather than a reskin: the review passes cleanly (100% citation coverage, no
  issues) and the verdict is *Proceed with conditions*, not *Further
  diligence required*.
- `tests/test_sensitivity.py` — the tornado ranking (stated bounds for a
  `_base` percentage, default ±20% swing otherwise, sorted by swing size) and
  the combined downside/upside scenario total. No API key required.
- `tests/test_verdict.py` — every branch of the rule-based verdict (clean →
  proceed; a high-severity Red-Team challenge alone → proceed with
  conditions; a high-severity reviewer issue → further diligence; low
  citation coverage → further diligence; compounding issues → do not
  proceed), plus the deal-economics reason line. No API key required.
- `tests/test_database.py` — repeated `save_analysis()` calls on the same
  record update one row instead of inserting a new one each time (this was a
  real bug: every scenario-slider drag saves, so without this a session of
  normal use would flood "Saved analyses" with duplicates), and a reloaded
  record's id survives so the next save still updates in place.
- `tests/test_pptx_generator.py` — the IC deck generator produces a valid `.pptx` (a well-formed
  OOXML zip) against the demo record, with a review, without one, with no opportunities/risks, and
  with special characters (`&`, `<`, `"`) in free text that could otherwise break XML generation.

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
keep "Demo (no API key)" selected, go to **Create Analysis**, and click
"Load demo case." Then browse the rest of the workflow — everything is
already populated, and the sidebar's "Live deal scorecard" tracks total value
creation against the original case and the deal's purchase price as you
adjust any slider.

The navigation (`st.navigation()`) is grouped into five sections that mirror how
a deal team actually works, not the order features were built in. A "Navigation
position" control in the sidebar switches between the sidebar (sections listed
with their pages) and a top bar (sections as dropdown menus) — the `DealLens`
logo (`st.logo()`) follows automatically in either mode:

**Setup**
- **Create Analysis**
- **Evidence** — company profiles and strategic rationale

**Analysis**
- **Independent Assessments** — the debate transcript, with live sliders on each opportunity to drag its underlying assumptions and watch the estimate recompute; a "3-Year Value Realization" chart at the top shows revenue vs. cost synergy stacked by year, aggregated across every opportunity
- **Sensitivity** — a tornado chart plus a downside/upside scenario, stress-testing the base case before you commit to it
- **Risk Register** — a likelihood × impact risk matrix (the standard consulting 3x3 heat map) above the table, sorted by likelihood × impact score (click "Generate risk register, integration plan, and review" here first; that one action also populates 100-Day Plan and Executive Summary)

**Decision**
- **Recommendation** — the rule-based verdict, informed by the sensitivity and risk picture, with a "Value Creation Bridge" waterfall chart (cost synergies + revenue synergies → total value creation) built from the same numbers driving the verdict

**Execution & Reporting**
- **100-Day Plan** — the phased integration plan, guiding principles, and governance — the execution plan for a deal you've decided to proceed with
- **Executive Summary** — the summary narrative plus the downloadable Markdown/PDF report or PowerPoint IC deck

**Appendix**
- **Evidence Trail** — every claim traced to its citation
- **Tables** — every structured table in the analysis (company profiles, financial baseline, opportunities, integration actions, reviewer issues) in one place

For a **live run** against real OpenAI calls: switch the sidebar to "Live
(OpenAI)", set `OPENAI_API_KEY` in your environment first —

```bash
cp .env.example .env   # add your OPENAI_API_KEY
export $(cat .env | xargs)
streamlit run app.py
```

— then work through the same pages in order: **Create Analysis** (keep the
bundled sample documents checked, or upload your own) → **Evidence**
(review extracted facts, approve assumptions) → **Independent Assessments**
(run Strategy → Financial → Red-Team) → **Sensitivity** → **Risk
Register** (run risk register, plan, reviewer, and executive summary
generation here) → everything in **Decision**, **Execution & Reporting**, and
**Appendix** (all live, no extra step needed once opportunities exist).

Run tests any time (no API key needed) with `pytest`.

## Roadmap

Staged so each piece is working before the next is added:

1. ✅ Strategy, Financial, and Red-Team agents debating in Independent Assessments, with a no-API-key demo mode (this version).
2. ✅ **Interactive scenario assumptions** — every opportunity's underlying assumptions (cost/revenue base, reduction/uplift %, margin) are live sliders on Independent Assessments, recomputed instantly via the real `financial_calculator` functions, no LLM call.
3. ✅ **Sensitivity / tornado chart, and a downside/upside scenario** — the Sensitivity page ranks every assumption by how much swinging it alone (others held fixed) moves total value creation, plus a combined worst/best case with every assumption swung at once (`agent/sensitivity.py`, this version).
4. ✅ **Investment Committee verdict** — a rule-based Proceed / Proceed with conditions / Further diligence / Do not proceed verdict on its own Recommendation page, built entirely from the reviewer's findings and Red-Team's challenges (`agent/verdict.py`, this version — deliberately not an LLM call rendering an opinion, so it's free and works in Demo mode).
5. ✅ **Deal economics and synergy ramp/cost-to-achieve** — value creation is compared against the deal's purchase price (captured on Create Analysis but previously unused anywhere in the pipeline), and each opportunity phases in over a 3-year ramp net of a one-time cost to achieve, instead of a single undiscounted run-rate number (this version).
6. ✅ **Risk likelihood x impact scoring** — the risk register is a composite 1-9 score (likelihood x impact), sorted highest first, instead of a single severity label (this version).
7. ✅ **Evidence Trail** — pick any claim-bearing item (a profile, the rationale, an opportunity, a risk, an agent's key findings) and see each underlying claim, color-coded by claim type, with the exact citation it rests on or a note that it has none (this version).
8. ✅ **PDF report export** — a formatted PDF (`tools/pdf_generator.py`, pure Python via reportlab, no system-binary dependency) alongside the existing Markdown download, with the same Recommendation/Deal Economics/ramp sections.
9. ✅ **PowerPoint IC deck export** — a 10-12 slide deck (`tools/pptx_generator.py`, pure `python-pptx`) alongside the Markdown/PDF report, styled to match the app's theme — the format a deal team actually presents, not just files.
10. ✅ **Value-creation charts** — a waterfall bridging cost + revenue synergies to total value creation (Recommendation), a 3-year value-realization stacked bar (Independent Assessments), and a likelihood x impact risk heat map (Risk Register) — the app had exactly one chart (the tornado) before this.
11. ✅ **Grouped sidebar navigation** — `st.navigation()` with five labeled sections (Setup / Analysis / Decision / Execution & Reporting / Appendix) replacing a flat 10-item radio list, so the sidebar itself communicates the deal-team workflow instead of just a numbered list.
12. ✅ **A second demo case** — Pfizer's acquisition of Seagen (large-cap pharma / clinical-stage biotech) alongside Amazon/Whole Foods, so Demo mode proves the tool generalizes across industries instead of reading as tuned to one story. Deliberately lands on a different verdict (proceed with conditions vs. further diligence) via a genuinely different evidence gap, not just different company names on the same numbers (this version).
13. **Operations, Customer, and People & Change agents** — supply-chain/duplicated-function analysis, cross-sell/cannibalization analysis, and org/culture risk + change-management planning, each following the same `AgentAssessment` pattern as Strategy/Financial/Red-Team.
14. **Partner Challenge Mode** — a Q&A screen that scores the user's own defense of the analysis (structure, evidence use, quantitative reasoning) after they've seen it.

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
