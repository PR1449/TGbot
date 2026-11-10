import sqlite3
from datetime import datetime, timezone, timedelta


DB_PATH = "heatbot.db"
MSK = timezone(timedelta(hours=3))

TABLES = ("utility_issues", "billing_questions", "emergency_situations")

STATUS_MAP = {
    "Новая":      "🆕 Зарегистрирована",
    "В работе":   "🛠 В работе",
    "Выполнена":  "✅ Выполнена",
    "Отклонена":  "❌ Отклонена",
}

CATEGORY_NAMES = {
    "utility_issues": "🔧 Коммунальные услуги и их перебои",
    "billing_questions": "📄 Вопросы по квитанциям и начислениям",
    "emergency_situations": "🚨 Аварийные ситуации",
}

def init_db():
    with sqlite3.connect(DB_PATH) as db:
        for table in TABLES:
            db.execute(f"""CREATE TABLE IF NOT EXISTS {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                created_time TEXT NOT NULL,
                user_id INTEGER,
                street TEXT NOT NULL,
                house_number TEXT NOT NULL,
                apartment_number TEXT,
                description TEXT,
                status TEXT DEFAULT 'Новая'
            )""")
            cols = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
            if "user_id" not in cols:
                db.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
        db.commit()


def insert_ticket(table: str, user_id: int, street, house_number,
                  apartment_number, description) -> int:
    if table not in TABLES:
        raise ValueError(f"Unknown table: {table}")
    now_local = datetime.now(timezone.utc).astimezone(MSK)
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute(
            f"INSERT INTO {table} (created_at, created_time, user_id, street, "
            f"house_number, apartment_number, description) VALUES (?,?,?,?,?,?,?)",
            (now_local.strftime("%Y-%m-%d"), now_local.strftime("%H:%M:%S"),
             user_id, street, house_number, apartment_number, description),
        )
        db.commit()
        return cur.lastrowid


def get_user_tickets(user_id: int) -> list[dict]:
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        tickets = []
        for table in TABLES:
            rows = db.execute(
                f"SELECT *, '{table}' AS category FROM {table} "
                f"WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            ).fetchall()
            tickets.extend(dict(r) for r in rows)
        return tickets
