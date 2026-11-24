from app.security import create_api_key, get_key_record, init_db, key_usage, record_usage


def test_api_key_is_stored_as_hash_and_usage_is_counted(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    init_db()
    raw_key, metadata = create_api_key("test customer", 2)
    record = get_key_record(raw_key)
    assert record is not None
    assert record["label"] == "test customer"
    assert record["monthly_limit"] == 2
    assert raw_key.startswith("iia_live_")
    record_usage(record["id"])
    usage = key_usage(record["id"], record["monthly_limit"])
    assert usage["used"] == 1
    assert usage["remaining"] == 1
    assert get_key_record("not-a-real-key") is None
