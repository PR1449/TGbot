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

CATEGORY_ORDER = {
    "emergency_situations": 0,
    "utility_issues": 1,
    "billing_questions": 2,
}

STATUS_ORDER = {
    "Новая": 0,
    "В работе": 1,
    "Выполнена": 2,
    "Отклонена": 3,
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
                status TEXT DEFAULT 'Новая',
                deleted INTEGER DEFAULT 0
            )""")
            cols = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
            if "user_id" not in cols:
                db.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
            if "deleted" not in cols:
                db.execute(f"ALTER TABLE {table} ADD COLUMN deleted INTEGER DEFAULT 0")
        db.commit()


def insert_ticket(table: str, user_id: int, street, house_number,
                  apartment_number, description) -> int:
    if table not in TABLES:
        raise ValueError(f"Unknown table: {table}")
    now_local = datetime.now(MSK)
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute(
            f"INSERT INTO {table} (created_at, created_time, user_id, street, "
            f"house_number, apartment_number, description) VALUES (?,?,?,?,?,?,?)",
            (now_local.strftime("%Y-%m-%d"), now_local.strftime("%H:%M:%S"),
             user_id, street, house_number, apartment_number, description),
        )
        db.commit()
        return cur.lastrowid


def get_user_tickets(user_id: int, start_date: str = None, end_date: str = None,
                     sort_by: str = None, categories: list[str] = None) -> list[dict]:
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        tickets = []
        tables_to_query = categories if categories else list(TABLES)
        for table in tables_to_query:
            query = f"SELECT *, '{table}' AS category FROM {table} WHERE user_id = ? AND deleted = 0"
            params: list = [user_id]

            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date)

            rows = db.execute(query, params).fetchall()
            tickets.extend(dict(r) for r in rows)

    if sort_by == "category":
        tickets.sort(key=lambda t: (CATEGORY_ORDER.get(t["category"], 9), t["created_at"]))
    elif sort_by == "date":
        tickets.sort(key=lambda t: (t["created_at"], t["created_time"]))
    elif sort_by == "status":
        tickets.sort(key=lambda t: (STATUS_ORDER.get(t["status"], 9), t["created_at"]))
    else:
        tickets.sort(key=lambda t: (t["created_at"], t["created_time"]), reverse=True)
    return tickets


def soft_delete_tickets(user_id: int) -> int:
    count = 0
    with sqlite3.connect(DB_PATH) as db:
        for table in TABLES:
            cur = db.execute(
                f"UPDATE {table} SET deleted = 1 WHERE user_id = ? AND deleted = 0",
                (user_id,),
            )
            count += cur.rowcount
        db.commit()
    return count
