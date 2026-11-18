import sqlite3
from pathlib import Path

DB_PATH = Path("heatbot.db")

TABLES = {
    "emergency_situations": "🚨 Аварийные ситуации",
    "billing_questions": "📄 Вопросы по квитанциям",
    "utility_issues": "🔧 Коммунальные услуги",
}

COLUMNS = """
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    created_time TEXT NOT NULL,
    street TEXT NOT NULL,
    house_number TEXT NOT NULL,
    apartment_number TEXT,
    description TEXT,
    status TEXT DEFAULT 'Новая'
"""


def create_tables():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        for table, title in TABLES.items():
            query = f"CREATE TABLE IF NOT EXISTS {table} ({COLUMNS})"
            cursor.execute(query)
            print(f"{table} — {title} создана (или уже существует)")

        conn.commit()
        print(f"Все таблицы успешно созданы в файле: {DB_PATH.resolve()}")

    except sqlite3.Error as e:
        print(f"Ошибка SQLite: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    create_tables()
