"""The synthetic benchmark runs end to end and scores text PDFs perfectly (regression baseline)."""
from scripts.synthetic_benchmark import report, run


def test_synthetic_benchmark_text_pdfs_baseline():
    result = run(count=12, seed=3, image_share=0.0)
    for name, stats in result["fields"].items():
        assert stats["correct"] == stats["n"], (name, result["failures"])
    li = result["line_items"]
    assert li["matched"] == li["truth"] == li["found"]
    assert "regression baseline" in report(result)
