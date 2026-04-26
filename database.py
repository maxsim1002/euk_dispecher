import sqlite3
import os
from dotenv import load_dotenv
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "dispatch.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'executor',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            priority TEXT NOT NULL DEFAULT 'normal',
            type TEXT NOT NULL DEFAULT 'Прочие',
            created_by INTEGER,
            assigned_to INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deadline TIMESTAMP,
            report TEXT,
            FOREIGN KEY (created_by) REFERENCES users(id),
            FOREIGN KEY (assigned_to) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS streets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            settlement_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (settlement_id) REFERENCES settlements(id),
            UNIQUE(settlement_id, name)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS houses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            street_id INTEGER NOT NULL,
            number TEXT NOT NULL,
            FOREIGN KEY (street_id) REFERENCES streets(id),
            UNIQUE(street_id, number)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS apartments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            house_id INTEGER NOT NULL,
            number TEXT NOT NULL,
            phone TEXT,
            FOREIGN KEY (house_id) REFERENCES houses(id),
            UNIQUE(house_id, number)
        )
    ''')

    # Заполняем базу адресов начальными данными
    # пгт.Славяносербск
    cursor.execute("INSERT OR IGNORE INTO settlements (name) VALUES (?)", ("пгт.Славяносербск",))
    slavyansk_id = cursor.execute("SELECT id FROM settlements WHERE name = ?", ("пгт.Славяносербск",)).fetchone()[0]
    
    for street in ["ул.Горького", "ул.Кирова", "ул.Ленина", "пер.Центральный", "ул.Дикалова"]:
        cursor.execute("INSERT OR IGNORE INTO streets (settlement_id, name) VALUES (?, ?)", (slavyansk_id, street))
    
    # пгт.Родаково
    cursor.execute("INSERT OR IGNORE INTO settlements (name) VALUES (?)", ("пгт.Родаково",))
    rodakovo_id = cursor.execute("SELECT id FROM settlements WHERE name = ?", ("пгт.Родаково",)).fetchone()[0]
    
    for street in ["ул.Ворошилова", "ул.Шевченко", "ул.Солнечный", "кв.Ленина"]:
        cursor.execute("INSERT OR IGNORE INTO streets (settlement_id, name) VALUES (?, ?)", (rodakovo_id, street))

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            photo_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    from passlib.hash import bcrypt
    cursor.execute(
    "INSERT OR IGNORE INTO users (username, password, full_name, role) VALUES (?, ?, ?, ?)",
    ('admin', pwd_context.hash('admin123'), 'Admin', 'admin')
    )

    conn.commit()
    conn.close()


def export_db():
    """Экспортировать БД в JSON"""
    import json
    from datetime import datetime
    
    conn = get_db()
    cursor = conn.cursor()
    
    data = {
        'timestamp': datetime.now().isoformat(),
        'tables': {}
    }
    
    tables = ['users', 'tickets', 'settlements', 'streets', 'houses', 'apartments', 'comments', 'messages']
    
    for table in tables:
        try:
            rows = cursor.execute(f"SELECT * FROM {table}").fetchall()
            columns = [description[0] for description in cursor.description] if cursor.description else []
            data['tables'][table] = {
                'columns': columns,
                'rows': [dict(row) for row in rows]
            }
        except:
            pass
    
    conn.close()
    return data


def import_db(data):
    """Импортировать БД из Excel/JSON"""
    import sqlite3

    # Поля INTEGER по таблицам — пустая строка '' должна стать NULL
    INTEGER_FIELDS = {
        'tickets':     {'id', 'created_by', 'assigned_to'},
        'users':       {'id'},
        'comments':    {'id', 'ticket_id', 'user_id'},
        'messages':    {'id', 'user_id'},
        'settlements': {'id'},
        'streets':     {'id', 'settlement_id'},
        'houses':      {'id', 'street_id'},
        'apartments':  {'id', 'house_id'},
    }

    def coerce(table, col, val):
        """Привести значение к нужному типу для SQLite."""
        # Пустая строка в INTEGER-поле → NULL
        if val == '' or val == 'None':
            if col in INTEGER_FIELDS.get(table, set()):
                return None
            return None if val == 'None' else val
        # float без дробной части → int
        if isinstance(val, float) and val == int(val):
            return int(val)
        return val

    conn = get_db()
    cursor = conn.cursor()

    try:
        for table_name, table_data in data.get('tables', {}).items():
            rows = table_data.get('rows', [])
            if not rows:
                continue

            columns = list(rows[0].keys())
            placeholders = ','.join(['?' for _ in columns])
            columns_str = ','.join(columns)

            for i, row in enumerate(rows):
                values = [coerce(table_name, col, row.get(col)) for col in columns]
                try:
                    cursor.execute(
                        f"INSERT OR REPLACE INTO {table_name} ({columns_str}) VALUES ({placeholders})",
                        values
                    )
                except sqlite3.InterfaceError as e:
                    # Детальная ошибка: какая таблица, строка, поле и значение
                    bad = [(col, repr(v)) for col, v in zip(columns, values)]
                    raise Exception(
                        f"Таблица '{table_name}', строка {i+1}: {e}\n"
                        f"Значения: {bad}"
                    )

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()