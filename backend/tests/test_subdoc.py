import sqlite3

import pytest

from app.pipeline import subdoc
from app.pipeline.subdoc import SubDoc
from app.pipeline.subtitle import Line


def _doc():
    # klip asli 100..130 dtk sumber
    return SubDoc(100, 130, [Line(1.0, 2.0, "HALO"), Line(5.0, 6.5, "WAH GILA"), Line(28.0, 30.0, "DADAH")])


def test_shift_lines_after_trim():
    doc = _doc()
    assert subdoc.shift_lines(doc, 100, 130) == doc.lines
    # awal digeser +2 dtk & akhir dipotong 5 dtk → baris pertama terpotong, terakhir hilang
    out = subdoc.shift_lines(doc, 102, 125)
    assert [(ln.start, ln.end, ln.text) for ln in out] == [(3.0, 4.5, "WAH GILA")]
    # awal dimajukan → waktu bertambah
    assert subdoc.shift_lines(doc, 95, 125)[0].start == 6.0
    assert subdoc.is_stale(doc, 102, 125) and not subdoc.is_stale(doc, 100, 130)


def test_save_load_delete(tmp_path):
    doc = _doc()
    doc.edited = True
    path = subdoc.save_doc(tmp_path, 3, doc)
    assert path.name == "clip_03.json"
    loaded = subdoc.load_doc(tmp_path, 3)
    assert loaded == doc
    subdoc.delete_doc(tmp_path, 3)
    assert subdoc.load_doc(tmp_path, 3) is None
    path.parent.mkdir(exist_ok=True)
    path.write_text("{rusak")
    assert subdoc.load_doc(tmp_path, 3) is None


def test_lines_to_words():
    words = subdoc.lines_to_words([Line(0, 2, "SATU DUA"), Line(3, 4, "")])
    assert [(w.start, w.end, w.text) for w in words] == [(0, 1, "SATU"), (1, 2, "DUA")]


def test_validate_lines():
    out = subdoc.validate_lines([{"start": 5, "end": 6, "text": " b "}, {"start": 1, "end": 2, "text": "a"}], 30)
    assert [ln.text for ln in out] == ["a", "b"]
    for bad in (
        [{"start": 1, "end": 2, "text": "  "}],
        [{"start": -1, "end": 2, "text": "x"}],
        [{"start": 3, "end": 2, "text": "x"}],
        [{"start": 29, "end": 31, "text": "x"}],
        [{"start": "a", "end": 2, "text": "x"}],
    ):
        with pytest.raises(ValueError):
            subdoc.validate_lines(bad, 30)


def test_migrate_adds_new_nullable_column(tmp_path):
    from app.db import make_engine

    db = tmp_path / "app.db"
    con = sqlite3.connect(db)  # skema lama tanpa subs_path
    con.execute('CREATE TABLE candidate (id INTEGER PRIMARY KEY, job_id VARCHAR NOT NULL, rank INTEGER NOT NULL, '
                'peak_time FLOAT NOT NULL, start FLOAT NOT NULL, "end" FLOAT NOT NULL, score INTEGER NOT NULL, '
                'selected BOOLEAN NOT NULL, clip_path VARCHAR, thumb_path VARCHAR, thumb_landscape_path VARCHAR, '
                'thumb_text VARCHAR, credit_path VARCHAR)')
    con.commit()
    con.close()
    make_engine(db).dispose()
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(candidate)")}
    assert "subs_path" in cols
