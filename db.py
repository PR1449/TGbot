import sqlite3
from datetime import datetime, timezone, timedelta


DB_PATH = "heatbot.db"
MSK = timezone(timedelta(hours=3))

TABLES = ("utility_issues", "billing_questions", "emergency_situations")

def init_db():
    with sqlite3.connect(DB_PATH) as db:
        for table in TABLES:
            db.execute(f"""CREATE TABLE IF NOT EXISTS {table} (
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

def insert_ticket(table: str, street, house_number, apartment_number, description):
    if table not in TABLES:
        raise ValueError(f"Unknown table: {table}")
    now_local = datetime.now(timezone.utc).astimezone(MSK)
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            f"INSERT INTO {table} (created_at, created_time, street, house_number, apartment_number, description) VALUES (?,?,?,?,?,?)",
            (now_local.strftime("%Y-%m-%d"), now_local.strftime("%H:%M:%S"),
             street, house_number, apartment_number, description),
        )
        db.commit()   
