import sqlite3
from datetime import datetime, timezone, timedelta


DB_PATH = "heatbot.db"

def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS billing_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            created_time TEXT NOT NULL,
            street TEXT NOT NULL,
            house_number TEXT NOT NULL,
            apartment_number TEXT,
            description TEXT,
            status TEXT DEFAULT 'Новая'
        )""")
        db.commit()

MSK = timezone(timedelta(hours=3))

def insert_billing(street, house_number, apartment_number, description):
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(MSK)
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT INTO billing_questions (created_at, created_time, ...) VALUES (?,?,?,?,?,?)",
            (now_local.strftime("%Y-%m-%d"), now_local.strftime("%H:%M:%S"), ...),
        )
        db.commit()
