from agent.demo_fixtures import DOCUMENT_NAMES, run_demo_pipeline
from agent.reviewer import review_analysis
from tools.pdf_generator import generate_pdf


def _reviewed_demo_record():
    record, tool_call_log = run_demo_pipeline()
    record.review = review_analysis(record, tool_call_log, DOCUMENT_NAMES)
    return record


def test_generates_a_valid_pdf():
    pdf_bytes = generate_pdf(_reviewed_demo_record())
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_works_without_a_review_or_deal_value():
    record, _ = run_demo_pipeline()
    record.review = None
    record.transaction.deal_value = None
    pdf_bytes = generate_pdf(record)
    assert pdf_bytes.startswith(b"%PDF-")


def test_survives_special_characters_in_free_text():
    record = _reviewed_demo_record()
    record.executive_summary = "R&D synergies <case> \"quoted\" & other <tags> that could break XML parsing"
    pdf_bytes = generate_pdf(record)
    assert pdf_bytes.startswith(b"%PDF-")


def test_works_with_no_opportunities_or_risks():
    record, _ = run_demo_pipeline()
    record.opportunities = []
    record.risks = []
    for a in record.agent_assessments:
        a.opportunities = []
    pdf_bytes = generate_pdf(record)
    assert pdf_bytes.startswith(b"%PDF-")
