from scripts.benchmark_invoices import normalise


def test_invoice_date_normalisation_accepts_iso_and_named_month():
    assert normalise("invoice_date", "2026-01-15") == "2026-01-15"
    assert normalise("invoice_date", "15 Jan 2026") == "2026-01-15"
    assert normalise("invoice_date", "January 15, 2026") == "2026-01-15"


def test_invoice_date_normalisation_only_resolves_unambiguous_numeric_dates():
    assert normalise("invoice_date", "31/01/2026") == "2026-01-31"
    assert normalise("invoice_date", "01/31/2026") == "2026-01-31"
    assert normalise("invoice_date", "01/02/2026") == ""
    assert normalise("invoice_date", "31/02/2026") == ""
