"""Validation gate report counts only recorded, qualifying data."""
from scripts.validation_gates import evaluate

BASE = {"segment": "customs_broker", "pain_score_0_3": "0", "invoice_rank_top3": "", "pilot_status": "none",
        "samples_received": "0", "consent_form_signed": "no"}


def test_gates_with_empty_data_are_not_met():
    result = evaluate([], [])
    assert all(not ok for _, _, ok in result["gates"].values())


def test_counts_only_qualifying_rows():
    rows = []
    for i, country in enumerate(["US"] * 6 + ["MX"] * 5 + ["UK"] * 5):
        row = dict(BASE, country=country)
        if i < 5:
            row.update(pain_score_0_3="3", invoice_rank_top3="1")
        if i < 3:
            row.update(pilot_status="paid")
        if i == 3:
            row.update(pilot_status="interested")  # interest is not a commitment
        if i < 10:
            row.update(samples_received="5", consent_form_signed="yes")
        if i == 10:
            row.update(samples_received="20", consent_form_signed="no")  # no consent, not counted
        rows.append(row)
    gates = evaluate(rows, [{"paid": "yes", "converted_to_subscription": "yes"}])["gates"]
    assert gates["interviews"] == (16, 15, True)
    assert gates["countries"][2] is True
    assert gates["max_country_share"][2] is True  # 6/16 = 0.375
    assert gates["pain_top3_with_score>=2"] == (5, 5, True)
    assert gates["paid_pilot_or_signed_loi"] == (3, 3, True)
    assert gates["consented_sample_invoices"] == (50, 50, True)


def test_country_cap_detects_concentration():
    rows = [dict(BASE, country="US")] * 10 + [dict(BASE, country="MX")] * 5
    assert evaluate(rows, [])["gates"]["max_country_share"][2] is False
