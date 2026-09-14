from agent.demo_fixtures import DOCUMENT_NAMES, run_demo_pipeline
from agent.reviewer import review_analysis
from tools.pptx_generator import generate_pptx


def _reviewed_demo_record():
    record, tool_call_log = run_demo_pipeline()
    record.review = review_analysis(record, tool_call_log, DOCUMENT_NAMES)
    return record


def test_generates_a_valid_pptx():
    pptx_bytes = generate_pptx(_reviewed_demo_record())
    assert pptx_bytes.startswith(b"PK\x03\x04")  # OOXML is a zip archive
    assert len(pptx_bytes) > 1000


def test_works_without_a_review_or_deal_value():
    record, _ = run_demo_pipeline()
    record.review = None
    record.transaction.deal_value = None
    pptx_bytes = generate_pptx(record)
    assert pptx_bytes.startswith(b"PK\x03\x04")


def test_survives_special_characters_in_free_text():
    record = _reviewed_demo_record()
    record.executive_summary = "R&D synergies <case> \"quoted\" & other <tags> that could break XML parsing"
    pptx_bytes = generate_pptx(record)
    assert pptx_bytes.startswith(b"PK\x03\x04")


def test_works_with_no_opportunities_or_risks():
    record, _ = run_demo_pipeline()
    record.opportunities = []
    record.risks = []
    for a in record.agent_assessments:
        a.opportunities = []
    pptx_bytes = generate_pptx(record)
    assert pptx_bytes.startswith(b"PK\x03\x04")
