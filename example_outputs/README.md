# Example outputs

`sample_opportunity.json` is a **hand-authored illustration** of the shape a
`ValueOpportunity` object takes — it matches `schemas/analysis_models.py` — not a
transcript from an actual pipeline run, since no live run has been evaluated yet
(see the root [README](../README.md#known-limitations)).

Once you run the app end-to-end against the bundled Amazon / Whole Foods sample
documents with a real `OPENAI_API_KEY`, save the generated Markdown report here
(via the download button on the 100-Day Plan page) as `amazon_whole_foods_report.md`,
and update the root README's evaluation section with the measured citation-coverage
and calculation-accuracy numbers from `tests/` plus a manual review of that report.
