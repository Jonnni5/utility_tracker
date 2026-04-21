import sqlite3
from pathlib import Path
from datetime import date

APP_DIR = Path(__file__).parent.resolve()
DB_PATH = APP_DIR / "payments.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            full_address TEXT, is_active INTEGER DEFAULT 1, is_multi_apartment INTEGER DEFAULT 0
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS payment_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            description TEXT, is_recurring INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, address_id INTEGER NOT NULL, type_id INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0), due_date TEXT NOT NULL,
            paid_date TEXT, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'paid', 'overdue')),
            notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (address_id) REFERENCES addresses(id) ON DELETE CASCADE,
            FOREIGN KEY (type_id) REFERENCES payment_types(id) ON DELETE CASCADE
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS meters (
            id INTEGER PRIMARY KEY AUTOINCREMENT, address_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('electricity', 'cold_water', 'hot_water')),
            serial_number TEXT UNIQUE NOT NULL, riser_number INTEGER,
            installation_date TEXT, is_active INTEGER DEFAULT 1,
            FOREIGN KEY (address_id) REFERENCES addresses(id) ON DELETE CASCADE
        )""")

        # 🔧 Миграция: добавляем новые поля, если их ещё нет
        new_cols = [
            ("total_area", "REAL DEFAULT 0.0"),
            ("actual_area", "REAL DEFAULT 0.0"),
            ("rooms_count", "INTEGER DEFAULT 1"),
            ("is_gasified", "INTEGER DEFAULT 0"),
            ("account_number", "TEXT DEFAULT ''"),
            ("registered_count", "INTEGER DEFAULT 1")
        ]
        for col, dtype in new_cols:
            try:
                conn.execute(f"ALTER TABLE addresses ADD COLUMN {col} {dtype}")
            except sqlite3.OperationalError:
                pass

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_due_date ON payments(due_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")
        conn.commit()

def get_or_create_payment_type(name, description="", is_recurring=True):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM payment_types WHERE name = ?", (name,))
        row = cur.fetchone()
        if row: return row["id"]
        cur.execute("INSERT INTO payment_types (name, description, is_recurring) VALUES (?, ?, ?)",
                    (name, description, 1 if is_recurring else 0))
        conn.commit()
        return cur.lastrowid

def add_address(name, full_address="", is_multi_apartment=False, 
                total_area=0.0, actual_area=0.0, rooms=1, is_gasified=False, 
                account="", registered=1):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO addresses 
            (name, full_address, is_multi_apartment, total_area, actual_area, 
             rooms_count, is_gasified, account_number, registered_count) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, full_address, 1 if is_multi_apartment else 0, 
             total_area, actual_area, rooms, 1 if is_gasified else 0, account, registered))
        conn.commit()
        return cur.lastrowid

def update_address(addr_id, name, full_address="", is_multi_apartment=False, 
                   total_area=0.0, actual_area=0.0, rooms=1, is_gasified=False, 
                   account="", registered=1):
    with get_connection() as conn:
        conn.execute("""UPDATE addresses SET 
            name=?, full_address=?, is_multi_apartment=?, total_area=?, actual_area=?,
            rooms_count=?, is_gasified=?, account_number=?, registered_count=? 
            WHERE id=?""",
            (name, full_address, 1 if is_multi_apartment else 0, 
             total_area, actual_area, rooms, 1 if is_gasified else 0, account, registered, addr_id))
        return conn.total_changes > 0

def delete_address(addr_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM addresses WHERE id=?", (addr_id,))
        return conn.total_changes > 0

def get_all_addresses():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT id, name, full_address, is_multi_apartment, total_area, actual_area,
                              rooms_count, is_gasified, account_number, registered_count
                       FROM addresses WHERE is_active = 1 ORDER BY name""")
        return [dict(row) for row in cur.fetchall()]

def add_payment_type(name, description="", is_recurring=True):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO payment_types (name, description, is_recurring) VALUES (?, ?, ?)",
                    (name, description, 1 if is_recurring else 0))
        conn.commit()
        return cur.lastrowid

def update_payment_type(type_id, name, description="", is_recurring=True):
    with get_connection() as conn:
        conn.execute("UPDATE payment_types SET name=?, description=?, is_recurring=? WHERE id=?",
                     (name, description, 1 if is_recurring else 0, type_id))
        return conn.total_changes > 0

def delete_payment_type(type_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM payment_types WHERE id=?", (type_id,))
        return conn.total_changes > 0

def get_all_payment_types():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, is_recurring FROM payment_types ORDER BY name")
        return [dict(row) for row in cur.fetchall()]

def add_payment(address_id, type_id, amount, due_date, notes=""):
    with get_connection() as conn:
        cur = conn.cursor()
        due = date.fromisoformat(due_date)
        status = 'overdue' if due < date.today() else 'pending'
        cur.execute("""INSERT INTO payments (address_id, type_id, amount, due_date, status, notes)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (address_id, type_id, amount, due_date, status, notes))
        conn.commit()
        return cur.lastrowid

def update_payment(payment_id, address_id, type_id, amount, due_date, notes=""):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM payments WHERE id = ?", (payment_id,))
        row = cur.fetchone()
        current_status = row["status"] if row else "pending"
        due = date.fromisoformat(due_date)
        new_status = current_status if current_status == "paid" else ("overdue" if due < date.today() else "pending")
        cur.execute("""UPDATE payments SET address_id=?, type_id=?, amount=?, due_date=?, status=?, notes=? WHERE id=?""",
                    (address_id, type_id, amount, due_date, new_status, notes, payment_id))
        conn.commit()
        return cur.rowcount > 0

def get_payments_by_month(year, month, address_id=None):
    with get_connection() as conn:
        cur = conn.cursor()
        sql = """SELECT p.id, a.name as address_name, pt.name as type_name,
                        p.amount, p.due_date, p.paid_date, p.status, p.notes
                 FROM payments p
                 JOIN addresses a ON p.address_id = a.id
                 JOIN payment_types pt ON p.type_id = pt.id
                 WHERE strftime('%Y', p.due_date) = ? AND strftime('%m', p.due_date) = ?"""
        params = [str(year).zfill(4), str(month).zfill(2)]
        if address_id:
            sql += " AND p.address_id = ?"
            params.append(address_id)
        sql += " ORDER BY p.due_date"
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

def mark_as_paid(payment_id, paid_date=None):
    if paid_date is None: paid_date = date.today().isoformat()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE payments SET paid_date=?, status='paid' WHERE id=?", (paid_date, payment_id))
        conn.commit()
        return cur.rowcount > 0

def delete_payment(payment_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM payments WHERE id=?", (payment_id,))
        conn.commit()
        return cur.rowcount > 0

def update_overdue_statuses():
    today = date.today().isoformat()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE payments SET status='overdue' WHERE due_date<? AND status='pending'", (today,))
        conn.commit()
        return cur.rowcount

def add_meter(address_id, m_type, serial, riser=None, install_date=None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO meters (address_id, type, serial_number, riser_number, installation_date)
                       VALUES (?, ?, ?, ?, ?)""", (address_id, m_type, serial, riser, install_date))
        conn.commit()
        return cur.lastrowid

def update_meter(meter_id, address_id, m_type, serial, riser=None, install_date=None):
    with get_connection() as conn:
        conn.execute("""UPDATE meters SET address_id=?, type=?, serial_number=?, riser_number=?, installation_date=? WHERE id=?""",
                     (address_id, m_type, serial, riser, install_date, meter_id))
        return conn.total_changes > 0

def delete_meter(meter_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM meters WHERE id=?", (meter_id,))
        return conn.total_changes > 0

def get_all_meters():
    with get_connection() as conn:
        cur = conn.cursor()
        # ✅ Добавлен m.address_id для корректной работы редактирования
        cur.execute("""SELECT m.id, m.address_id, a.name as address_name, m.type, m.serial_number,
                              m.riser_number, m.installation_date
                       FROM meters m JOIN addresses a ON m.address_id = a.id
                       WHERE m.is_active = 1 ORDER BY a.name, m.type""")
        return [dict(row) for row in cur.fetchall()]

def get_payment(payment_id):
    """Возвращает детали платежа + флаг регулярности типа платежа"""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT p.address_id, p.type_id, p.amount, p.due_date, p.notes, pt.is_recurring
                       FROM payments p
                       JOIN payment_types pt ON p.type_id = pt.id
                       WHERE p.id = ?""", (payment_id,))
        row = cur.fetchone()
        return dict(row) if row else None