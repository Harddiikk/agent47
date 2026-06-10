"""Tests for shared/book.py — offline via a fake research function."""
import pytest

from shared.book import BookStore, load_customers, scan_book


def _write_csv(path, rows):
    lines = ["name,location,services,contact_email"]
    lines += [f"{r['name']},{r['location']},{r['services']},{r['email']}" for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- load_customers ---


def test_load_customers(tmp_path):
    csv = tmp_path / "c.csv"
    _write_csv(csv, [{"name": "Acme", "location": "NY", "services": "dental", "email": "a@a.com"}])
    rows = load_customers(csv)
    assert rows == [
        {"name": "Acme", "location": "NY", "services": "dental", "contact_email": "a@a.com"}
    ]


def test_load_customers_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_customers(tmp_path / "nope.csv")


def test_load_customers_skips_blank_names(tmp_path):
    csv = tmp_path / "c.csv"
    csv.write_text("name,location,services,contact_email\n,NY,dental,a@a.com\nReal,NY,x,b@b.com\n")
    assert [r["name"] for r in load_customers(csv)] == ["Real"]


# --- BookStore ---


def test_bookstore_save_and_all():
    s = BookStore(":memory:")
    s.save_signal(
        {
            "name": "Acme",
            "location": "NY",
            "contact_email": "a@a.com",
            "signal_type": "expansion",
            "severity": "high",
            "summary": "new clinic",
            "confidence": 0.9,
            "evidence": [{"claim": "x", "source_url": "https://a.com"}],
        }
    )
    rows = s.all_signals()
    assert len(rows) == 1
    assert rows[0]["name"] == "Acme"
    assert rows[0]["evidence"][0]["source_url"] == "https://a.com"  # round-trips JSON


# --- scan_book ---


def _fake_research(verdicts):
    def _fn(name, location="", services=""):
        return verdicts[name]
    return _fn


def test_scan_book_filters_ranks_and_persists(tmp_path):
    csv = tmp_path / "c.csv"
    _write_csv(
        csv,
        [
            {"name": "High", "location": "A", "services": "s", "email": "h@x.com"},
            {"name": "Low", "location": "B", "services": "s", "email": "l@x.com"},
            {"name": "None", "location": "C", "services": "s", "email": "n@x.com"},
        ],
    )
    verdicts = {
        "High": {"has_signal": True, "signal_type": "expansion", "severity": "high",
                 "summary": "big", "evidence": [], "confidence": 0.7, "error": ""},
        "Low": {"has_signal": True, "signal_type": "expansion", "severity": "low",
                "summary": "small", "evidence": [], "confidence": 0.9, "error": ""},
        "None": {"has_signal": False, "signal_type": "neutral", "severity": "low",
                 "summary": "", "evidence": [], "confidence": 0.0, "error": ""},
    }
    db = tmp_path / "book.db"
    out = scan_book(csv, db_path=db, research_fn=_fake_research(verdicts), max_workers=2)

    assert out["scanned"] == 3
    assert out["signals_found"] == 2
    # high severity ranks above low even though low has higher confidence
    assert [r["name"] for r in out["ranked"]] == ["High", "Low"]
    # persisted to the new table
    assert {r["name"] for r in BookStore(db).all_signals()} == {"High", "Low"}


def test_scan_book_collects_errors(tmp_path):
    csv = tmp_path / "c.csv"
    _write_csv(csv, [{"name": "Err", "location": "A", "services": "s", "email": "e@x.com"}])
    verdicts = {
        "Err": {"has_signal": False, "signal_type": "neutral", "severity": "low",
                "summary": "", "evidence": [], "confidence": 0.0, "error": "503 throttled"},
    }
    out = scan_book(csv, db_path=tmp_path / "b.db", research_fn=_fake_research(verdicts))
    assert out["signals_found"] == 0
    assert out["errors"][0]["error"] == "503 throttled"
