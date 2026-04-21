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
        cursor.execute("""CREATE TABLE IF NOT EXISTS meter_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, meter_id INTEGER NOT NULL,
            reading_date TEXT NOT NULL, previous_value REAL DEFAULT 0.0,
            current_value REAL NOT NULL, consumption REAL DEFAULT 0.0,
            invoice_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meter_id) REFERENCES meters(id) ON DELETE CASCADE,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE SET NULL
        )""")

        # 🔹 НОВАЯ ТАБЛИЦА СЧЕТОВ
        cursor.execute("""CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT, address_id INTEGER NOT NULL,
            invoice_number TEXT UNIQUE NOT NULL, invoice_date TEXT NOT NULL,
            due_date TEXT, total_amount REAL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'paid')),
            notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (address_id) REFERENCES addresses(id) ON DELETE CASCADE
        )""")

        # 🔹 ТАБЛИЦЫ ДЛЯ БУДУЩЕГО РАСЧЁТА
        cursor.execute("""CREATE TABLE IF NOT EXISTS tariffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, type_id INTEGER NOT NULL,
            rate REAL NOT NULL, start_date TEXT NOT NULL, end_date TEXT,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (type_id) REFERENCES payment_types(id)
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS consumption_norms (
            id INTEGER PRIMARY KEY AUTOINCREMENT, address_id INTEGER, type_id INTEGER,
            norm_value REAL NOT NULL, unit TEXT DEFAULT 'ед.',
            start_date TEXT NOT NULL, end_date TEXT, is_active INTEGER DEFAULT 1,
            FOREIGN KEY (address_id) REFERENCES addresses(id),
            FOREIGN KEY (type_id) REFERENCES payment_types(id)
        )""")

        # 🔧 Миграция полей для addresses
        new_cols = [
            ("total_area", "REAL DEFAULT 0.0"), ("actual_area", "REAL DEFAULT 0.0"),
            ("rooms_count", "INTEGER DEFAULT 1"), ("is_gasified", "INTEGER DEFAULT 0"),
            ("account_number", "TEXT DEFAULT ''"), ("registered_count", "INTEGER DEFAULT 1")
        ]
        for col, dtype in new_cols:
            try: conn.execute(f"ALTER TABLE addresses ADD COLUMN {col} {dtype}")
            except sqlite3.OperationalError: pass

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_due_date ON payments(due_date)")
        conn.commit()

# --- Существующие функции ---
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

def add_address(name, full_address="", is_multi_apartment=False, total_area=0.0, actual_area=0.0, rooms=1, is_gasified=False, account="", registered=1):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO addresses (name, full_address, is_multi_apartment, total_area, actual_area, rooms_count, is_gasified, account_number, registered_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, full_address, 1 if is_multi_apartment else 0, total_area, actual_area, rooms, 1 if is_gasified else 0, account, registered))
        conn.commit()
        return cur.lastrowid

def update_address(addr_id, name, full_address="", is_multi_apartment=False, total_area=0.0, actual_area=0.0, rooms=1, is_gasified=False, account="", registered=1):
    with get_connection() as conn:
        conn.execute("UPDATE addresses SET name=?, full_address=?, is_multi_apartment=?, total_area=?, actual_area=?, rooms_count=?, is_gasified=?, account_number=?, registered_count=? WHERE id=?",
                     (name, full_address, 1 if is_multi_apartment else 0, total_area, actual_area, rooms, 1 if is_gasified else 0, account, registered, addr_id))
        return conn.total_changes > 0

def delete_address(addr_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM addresses WHERE id=?", (addr_id,))
        return conn.total_changes > 0

def get_all_addresses():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, full_address, is_multi_apartment, total_area, actual_area, rooms_count, is_gasified, account_number, registered_count FROM addresses WHERE is_active = 1 ORDER BY name")
        return [dict(row) for row in cur.fetchall()]

def get_all_payment_types():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, is_recurring FROM payment_types ORDER BY name")
        return [dict(row) for row in cur.fetchall()]

def add_meter(address_id, m_type, serial, riser=None, install_date=None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO meters (address_id, type, serial_number, riser_number, installation_date) VALUES (?, ?, ?, ?, ?)", (address_id, m_type, serial, riser, install_date))
        conn.commit()
        return cur.lastrowid

def update_meter(meter_id, address_id, m_type, serial, riser=None, install_date=None):
    with get_connection() as conn:
        conn.execute("UPDATE meters SET address_id=?, type=?, serial_number=?, riser_number=?, installation_date=? WHERE id=?", (address_id, m_type, serial, riser, install_date, meter_id))
        return conn.total_changes > 0

def delete_meter(meter_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM meters WHERE id=?", (meter_id,))
        return conn.total_changes > 0

def get_all_meters():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT m.id, m.address_id, a.name as address_name, m.type, m.serial_number, m.riser_number, m.installation_date FROM meters m JOIN addresses a ON m.address_id = a.id WHERE m.is_active = 1 ORDER BY a.name, m.type")
        return [dict(row) for row in cur.fetchall()]

# 🔹 НОВЫЕ ФУНКЦИИ ДЛЯ НОВОГО ПРОЦЕССА
def get_last_reading(meter_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM meter_readings WHERE meter_id=? ORDER BY reading_date DESC LIMIT 1", (meter_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def save_meter_reading(meter_id, reading_date, current_value):
    last = get_last_reading(meter_id)
    prev_value = last["current_value"] if last else 0.0
    consumption = max(0.0, current_value - prev_value)
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO meter_readings (meter_id, reading_date, previous_value, current_value, consumption) VALUES (?, ?, ?, ?, ?)",
                    (meter_id, reading_date, prev_value, current_value, consumption))
        conn.commit()
        return cur.lastrowid

def get_unlinked_readings(address_id, since_date=None):
    """Получает показания, еще не привязанные к счету"""
    with get_connection() as conn:
        cur = conn.cursor()
        sql = """SELECT mr.id, m.type, m.serial_number, mr.reading_date, mr.previous_value, mr.current_value, mr.consumption
                 FROM meter_readings mr JOIN meters m ON mr.meter_id = m.id
                 WHERE m.address_id = ? AND mr.invoice_id IS NULL"""
        params = [address_id]
        if since_date:
            sql += " AND mr.reading_date >= ?"
            params.append(since_date)
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

def get_next_invoice_number():
    """Генерирует номер: INV-YYYYMM-NNN"""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT invoice_number FROM invoices ORDER BY id DESC LIMIT 1")
        last = cur.fetchone()
        today = date.today()
        prefix = f"INV-{today.year}{today.month:02d}"
        seq = 1
        if last and last["invoice_number"].startswith(prefix):
            try: seq = int(last["invoice_number"].split("-")[-1]) + 1
            except: pass
        return f"{prefix}-{seq:03d}"

def create_invoice(address_id, invoice_number, invoice_date, total_amount, notes="", reading_ids=None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO invoices (address_id, invoice_number, invoice_date, total_amount, notes) VALUES (?, ?, ?, ?, ?)",
                    (address_id, invoice_number, invoice_date, total_amount, notes))
        inv_id = cur.lastrowid
        if reading_ids:
            cur.executemany("UPDATE meter_readings SET invoice_id = ? WHERE id = ?", [(inv_id, rid) for rid in reading_ids])
        conn.commit()
        return inv_id

def get_invoices(year, month, address_id=None):
    with get_connection() as conn:
        cur = conn.cursor()
        sql = """SELECT i.id, a.name as address_name, i.invoice_number, i.total_amount, i.invoice_date, i.due_date, i.status, i.notes
                 FROM invoices i JOIN addresses a ON i.address_id = a.id
                 WHERE strftime('%Y', i.invoice_date) = ? AND strftime('%m', i.invoice_date) = ?"""
        params = [str(year).zfill(4), str(month).zfill(2)]
        if address_id:
            sql += " AND i.address_id = ?"
            params.append(address_id)
        cur.execute(sql + " ORDER BY i.invoice_date DESC", params)
        return [dict(r) for r in cur.fetchall()]

def pay_invoice(invoice_id, paid_date=None):
    if not paid_date: paid_date = date.today().isoformat()
    with get_connection() as conn:
        conn.execute("UPDATE invoices SET status='paid', due_date=? WHERE id=?", (paid_date, invoice_id))
        return conn.total_changes > 0

def delete_invoice(invoice_id):
    with get_connection() as conn:
        conn.execute("UPDATE meter_readings SET invoice_id = NULL WHERE invoice_id=?", (invoice_id,))
        conn.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
        return conn.total_changes > 0

# 🔹 Заглушки для будущих тарифов и норм (готовы к расширению)
def add_tariff(type_id, rate, start_date, end_date=None):
    with get_connection() as conn:
        conn.execute("INSERT INTO tariffs (type_id, rate, start_date, end_date) VALUES (?, ?, ?, ?)", (type_id, rate, start_date, end_date))
        conn.commit()

def get_tariff(type_id, date_str):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT rate FROM tariffs WHERE type_id=? AND start_date<=? AND (end_date IS NULL OR end_date>=?) AND is_active=1 ORDER BY start_date DESC LIMIT 1", (type_id, date_str, date_str))
        row = cur.fetchone()
        return row["rate"] if row else None

def add_norm(type_id, norm_value, unit, start_date, end_date=None, address_id=None):
    with get_connection() as conn:
        conn.execute("INSERT INTO consumption_norms (address_id, type_id, norm_value, unit, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?)",
                     (address_id, type_id, norm_value, unit, start_date, end_date))
        conn.commit()