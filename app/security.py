from __future__ import annotations
import hashlib, os, secrets, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
DEFAULT_MONTHLY_LIMIT = int(os.getenv("DEFAULT_MONTHLY_LIMIT", "1000"))
def _db_path() -> str: return os.getenv("DATABASE_PATH", "data/invoice_api.db")
def _connect() -> sqlite3.Connection:
    path=_db_path(); Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn=sqlite3.connect(path); conn.row_factory=sqlite3.Row; return conn
def init_db() -> None:
    with _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS api_keys (id INTEGER PRIMARY KEY AUTOINCREMENT,label TEXT NOT NULL,key_hash TEXT NOT NULL UNIQUE,monthly_limit INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,plan TEXT NOT NULL DEFAULT 'free',stripe_customer_id TEXT,subscription_id TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS api_usage (id INTEGER PRIMARY KEY AUTOINCREMENT,api_key_id INTEGER NOT NULL,used_at TEXT NOT NULL,FOREIGN KEY(api_key_id) REFERENCES api_keys(id))""")
        columns={r["name"] for r in conn.execute("PRAGMA table_info(api_keys)").fetchall()}
        for n,d in {"plan":"TEXT NOT NULL DEFAULT 'free'","stripe_customer_id":"TEXT","subscription_id":"TEXT"}.items():
            if n not in columns: conn.execute(f"ALTER TABLE api_keys ADD COLUMN {n} {d}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_key_date ON api_usage(api_key_id, used_at)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_subscription ON api_keys(subscription_id) WHERE subscription_id IS NOT NULL")
        conn.execute("""CREATE TABLE IF NOT EXISTS checkout_claims(session_id TEXT PRIMARY KEY,api_key_id INTEGER NOT NULL UNIQUE,claimed_at TEXT NOT NULL,FOREIGN KEY(api_key_id) REFERENCES api_keys(id))""")
def hash_key(api_key: str) -> str: return hashlib.sha256(api_key.encode()).hexdigest()
def _new_raw_key() -> str:
    prefix="iia_test_" if os.getenv("STRIPE_SECRET_KEY","").startswith("sk_test_") else "iia_live_"
    return prefix+secrets.token_urlsafe(32)
def create_api_key(label: str, monthly_limit: int|None=None) -> tuple[str,dict[str,Any]]:
    raw=_new_raw_key(); limit=monthly_limit or DEFAULT_MONTHLY_LIMIT
    if limit<1: raise ValueError("monthly_limit must be positive")
    created=datetime.now(timezone.utc).isoformat()
    with _connect() as c:
        cur=c.execute("INSERT INTO api_keys(label,key_hash,monthly_limit,created_at) VALUES (?,?,?,?)",(label,hash_key(raw),limit,created))
        kid=cur.lastrowid
    return raw,{"id":kid,"label":label,"monthly_limit":limit,"created_at":created}
def create_paid_customer_key(session_id:str,email:str,plan:str,customer_id:str,subscription_id:str,monthly_limit:int)->str|None:
    raw=_new_raw_key(); created=datetime.now(timezone.utc).isoformat()
    with _connect() as c:
        if c.execute("SELECT 1 FROM checkout_claims WHERE session_id=?",(session_id,)).fetchone(): return None
        cur=c.execute("""INSERT INTO api_keys(label,key_hash,monthly_limit,active,created_at,plan,stripe_customer_id,subscription_id) VALUES (?,?,?,1,?,?,?,?)""",
            (f"Customer {email}",hash_key(raw),monthly_limit,created,plan,customer_id,subscription_id))
        c.execute("INSERT INTO checkout_claims(session_id,api_key_id,claimed_at) VALUES (?,?,?)",(session_id,cur.lastrowid,created))
    return raw
def get_key_record(api_key:str)->dict[str,Any]|None:
    with _connect() as c: row=c.execute("SELECT id,label,monthly_limit,active,plan,stripe_customer_id,subscription_id FROM api_keys WHERE key_hash=?",(hash_key(api_key),)).fetchone()
    return dict(row) if row else None
def key_usage(key_id:int,monthly_limit:int)->dict[str,int]:
    month=datetime.now(timezone.utc).strftime("%Y-%m")
    with _connect() as c: row=c.execute("SELECT COUNT(*) AS used FROM api_usage WHERE api_key_id=? AND substr(used_at,1,7)=?",(key_id,month)).fetchone()
    used=int(row["used"]); return {"used":used,"monthly_limit":monthly_limit,"remaining":max(0,monthly_limit-used)}
def record_usage(key_id:int)->None:
    with _connect() as c: c.execute("INSERT INTO api_usage(api_key_id,used_at) VALUES (?,?)",(key_id,datetime.now(timezone.utc).isoformat()))
def requests_in_last_minute(key_id:int)->int:
    from datetime import timedelta
    cutoff=(datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat()
    with _connect() as c: row=c.execute("SELECT COUNT(*) AS used FROM api_usage WHERE api_key_id=? AND used_at>=?",(key_id,cutoff)).fetchone()
    return int(row["used"])
def set_subscription(key_id:int,plan:str,status:str,customer_id:str|None,subscription_id:str,monthly_limit:int)->None:
    active=1 if status in {"active","trialing"} else 0
    with _connect() as c: c.execute("UPDATE api_keys SET plan=?,active=?,monthly_limit=?,stripe_customer_id=?,subscription_id=? WHERE id=?",(plan,active,monthly_limit,customer_id,subscription_id,key_id))
def set_subscription_by_id(subscription_id:str,status:str)->None:
    active=1 if status in {"active","trialing"} else 0
    with _connect() as c: c.execute("UPDATE api_keys SET active=? WHERE subscription_id=?",(active,subscription_id))
