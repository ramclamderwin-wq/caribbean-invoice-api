"""Concierge pilot tool: end-to-end on synthetic invoices, error handling, AI gating."""
from __future__ import annotations

import csv
import hashlib
import json
from types import SimpleNamespace

import pytest

from app.pilot_run import main, process_folder
from scripts.make_demo_invoices import make


def _rows(path):
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture
def demo_dir(tmp_path):
    folder = tmp_path / "incoming"
    make(folder)
    (folder / "notes.docx").write_bytes(b"not an invoice")
    (folder / "broken.pdf").write_bytes(b"%PDF-1.4 broken")
    return folder


def test_rules_run_on_synthetic_demo(demo_dir, tmp_path):
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in demo_dir.iterdir()}
    run_dir = process_folder(demo_dir, tmp_path / "out", "Synthetic Demo", timestamped=False)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in demo_dir.iterdir()}
    assert before == after  # inputs untouched

    log = {r["file"]: r for r in _rows(run_dir / "run_log.csv")}
    assert log["notes.docx"]["status"] == "error" and log["broken.pdf"]["status"] == "error"
    assert log["demo-004-with-errors.pdf"]["status"] == "needs_review"
    assert log["demo-005-scanned-image.png"]["status"] == "ok"  # OCR path
    assert sum(1 for r in log.values() if r["status"] == "ok") == 4

    invoices = {r["document"]: r for r in _rows(run_dir / "invoices.csv")}
    assert invoices["demo-001-en-standard.pdf"]["total"] == "3067.00"
    assert invoices["demo-003-eur-comma-decimals.pdf"]["currency"] == "EUR"
    lines = _rows(run_dir / "line_items.csv")
    assert sum(1 for r in lines if r["document"] == "demo-001-en-standard.pdf") == 4

    checklist = (run_dir / "REVIEW_CHECKLIST.md").read_text()
    assert "demo-004-with-errors.pdf" in checklist and "broken.pdf" in checklist
    assert json.loads((run_dir / "results.json").read_text())["engine"] == "rules"


def test_ai_engine_is_locked_without_authorisation(demo_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("QUILLVORA_AI_ENABLED", raising=False)
    with pytest.raises(SystemExit, match="confirm-data-sharing"):
        process_folder(demo_dir, tmp_path / "out", "X", engine="ai")
    with pytest.raises(SystemExit, match="disabled"):
        process_folder(demo_dir, tmp_path / "out", "X", engine="ai", confirm_data_sharing=True)


def test_ai_engine_path_with_fake_engine(demo_dir, tmp_path):
    class FakeEngine:
        calls = 0

        def extract(self, data, suffix, *, data_sharing_confirmed):
            assert data_sharing_confirmed is True
            FakeEngine.calls += 1
            result = {"invoice_number": "X", "line_items": [], "fields_needing_review": [], "issues": []}
            return SimpleNamespace(result=result, cost_usd=0.02, error=None)

    run_dir = process_folder(demo_dir, tmp_path / "out", "X", engine="ai", confirm_data_sharing=True,
                             ai_engine=FakeEngine(), timestamped=False)
    log = _rows(run_dir / "run_log.csv")
    assert FakeEngine.calls == 6  # 5 demo files + broken.pdf; .docx rejected before any call
    assert all(r["engine"] == "ai" for r in log)


def test_cli_end_to_end(demo_dir, tmp_path, capsys):
    assert main(["--customer", "Demo", "--input", str(demo_dir), "--output", str(tmp_path / "o"), "--no-timestamp"]) == 0
    assert "Results in" in capsys.readouterr().out
