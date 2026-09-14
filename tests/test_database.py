from pathlib import Path

from agent.demo_fixtures import run_demo_pipeline
from db.database import list_analyses, load_analysis, save_analysis


def _tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test_deallens.db"


def test_repeated_saves_update_the_same_row_instead_of_inserting(tmp_path):
    db_path = _tmp_db(tmp_path)
    record, _ = run_demo_pipeline()

    save_analysis(record, db_path)
    first_id = record.id
    assert first_id is not None

    record.opportunities[0].estimated_value.base = 999_000_000
    save_analysis(record, db_path)
    save_analysis(record, db_path)

    assert record.id == first_id
    assert len(list_analyses(db_path)) == 1


def test_saved_record_id_survives_a_reload(tmp_path):
    db_path = _tmp_db(tmp_path)
    record, _ = run_demo_pipeline()
    save_analysis(record, db_path)

    reloaded = load_analysis(record.id, db_path)
    assert reloaded.id == record.id

    # a save after reload must update, not insert a second row
    save_analysis(reloaded, db_path)
    assert len(list_analyses(db_path)) == 1


def test_two_different_records_get_two_rows(tmp_path):
    db_path = _tmp_db(tmp_path)
    record_a, _ = run_demo_pipeline()
    record_b, _ = run_demo_pipeline()

    save_analysis(record_a, db_path)
    save_analysis(record_b, db_path)

    assert record_a.id != record_b.id
    assert len(list_analyses(db_path)) == 2
