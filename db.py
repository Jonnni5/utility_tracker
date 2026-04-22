import sqlite3
import json
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
        cur = conn.cursor()
        
        # 1. Адреса
        cur.execute("""CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            full_address TEXT, is_active INTEGER DEFAULT 1, is_multi_apartment INTEGER DEFAULT 0,
            total_area REAL DEFAULT 0.0, actual_area REAL DEFAULT 0.0,
            rooms_count INTEGER DEFAULT 1, is_gasified INTEGER DEFAULT 0,
            account_number TEXT DEFAULT '', registered_count INTEGER DEFAULT 1
        )""")

        # 2. Типы платежей
        cur.execute("""CREATE TABLE IF NOT EXISTS payment_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            description TEXT, is_recurring INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        # 3. Платежи (legacy)
        cur.execute("""CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, address_id INTEGER NOT NULL, type_id INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0), due_date TEXT NOT NULL,
            paid_date TEXT, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'paid', 'overdue')),
            notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (address_id) REFERENCES addresses(id) ON DELETE CASCADE,
            FOREIGN KEY (type_id) REFERENCES payment_types(id) ON DELETE CASCADE
        )""")

        # 4. Приборы учёта (обновлено: riser_number TEXT, добавлены heat и gas)
        cur.execute("""CREATE TABLE IF NOT EXISTS meters (
            id INTEGER PRIMARY KEY AUTOINCREMENT, address_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('electricity', 'cold_water', 'hot_water', 'heat', 'gas')),
            serial_number TEXT UNIQUE NOT NULL, riser_number TEXT,
            installation_date TEXT, is_active INTEGER DEFAULT 1,
            FOREIGN KEY (address_id) REFERENCES addresses(id) ON DELETE CASCADE
        )""")

        # 5. Показания счётчиков
        cur.execute("""CREATE TABLE IF NOT EXISTS meter_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, meter_id INTEGER NOT NULL,
            reading_date TEXT NOT NULL, previous_value REAL DEFAULT 0.0,
            current_value REAL NOT NULL, consumption REAL DEFAULT 0.0,
            invoice_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meter_id) REFERENCES meters(id) ON DELETE CASCADE,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE SET NULL
        )""")

        # 6. Счета
        cur.execute("""CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT, address_id INTEGER NOT NULL,
            invoice_number TEXT UNIQUE NOT NULL, invoice_date TEXT NOT NULL,
            due_date TEXT, total_amount REAL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'paid')),
            notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (address_id) REFERENCES addresses(id) ON DELETE CASCADE
        )""")

        # 7. Тарифы и нормы (для будущего расчёта)
        cur.execute("""CREATE TABLE IF NOT EXISTS tariffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, type_id INTEGER NOT NULL,
            rate REAL NOT NULL, start_date TEXT NOT NULL, end_date TEXT,
            is_active INTEGER DEFAULT 1, FOREIGN KEY (type_id) REFERENCES payment_types(id)
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS consumption_norms (
            id INTEGER PRIMARY KEY AUTOINCREMENT, address_id INTEGER, type_id INTEGER,
            norm_value REAL NOT NULL, unit TEXT DEFAULT 'ед.',
            start_date TEXT NOT NULL, end_date TEXT, is_active INTEGER DEFAULT 1,
            FOREIGN KEY (address_id) REFERENCES addresses(id),
            FOREIGN KEY (type_id) REFERENCES payment_types(id)
        )""")

        # Индексы для ускорения выборок
        cur.execute("CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_due_date ON payments(due_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")
        conn.commit()

# =============================================================================
# 📦 СПРАВОЧНИКИ: ТИПЫ ПЛАТЕЖЕЙ
# =============================================================================
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

def add_payment_type(name, description="", is_recurring=True):
    with get_connection() as conn:
        conn.execute("INSERT INTO payment_types (name, description, is_recurring) VALUES (?, ?, ?)",
                     (name.strip(), description.strip(), 1 if is_recurring else 0))
        conn.commit()

def update_payment_type(type_id, name, description="", is_recurring=True):
    with get_connection() as conn:
        conn.execute("UPDATE payment_types SET name=?, description=?, is_recurring=? WHERE id=?",
                     (name.strip(), description.strip(), 1 if is_recurring else 0, type_id))

def delete_payment_type(type_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM payment_types WHERE id=?", (type_id,))

def get_all_payment_types():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, is_recurring FROM payment_types ORDER BY name")
        return [dict(row) for row in cur.fetchall()]

# =============================================================================
# 📦 СПРАВОЧНИКИ: АДРЕСА
# =============================================================================
def add_address(name, full_address="", is_multi_apartment=False, total_area=0.0, actual_area=0.0, rooms=1, is_gasified=False, account="", registered=1):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO addresses (name, full_address, is_multi_apartment, total_area, actual_area, rooms_count, is_gasified, account_number, registered_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (name, full_address, 1 if is_multi_apartment else 0, total_area, actual_area, rooms, 1 if is_gasified else 0, account, registered))
        conn.commit()
        return cur.lastrowid

def update_address(addr_id, name, full_address="", is_multi_apartment=False, total_area=0.0, actual_area=0.0, rooms=1, is_gasified=False, account="", registered=1):
    with get_connection() as conn:
        conn.execute("""UPDATE addresses SET name=?, full_address=?, is_multi_apartment=?, total_area=?, actual_area=?, rooms_count=?, is_gasified=?, account_number=?, registered_count=?
                        WHERE id=?""",
                     (name, full_address, 1 if is_multi_apartment else 0, total_area, actual_area, rooms, 1 if is_gasified else 0, account, registered, addr_id))
        return conn.total_changes > 0

def delete_address(addr_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM addresses WHERE id=?", (addr_id,))
        return conn.total_changes > 0

def get_all_addresses():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT id, name, full_address, is_multi_apartment, total_area, actual_area, rooms_count, is_gasified, account_number, registered_count
                       FROM addresses WHERE is_active = 1 ORDER BY name""")
        return [dict(row) for row in cur.fetchall()]

# =============================================================================
# 📦 ПЛАТЕЖИ (LEGACY)
# =============================================================================
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

def get_payments_by_month(year, month, address_id=None):
    with get_connection() as conn:
        cur = conn.cursor()
        sql = """SELECT p.id, a.name as address_name, pt.name as type_name, p.amount, p.due_date, p.paid_date, p.status, p.notes
                 FROM payments p JOIN addresses a ON p.address_id = a.id JOIN payment_types pt ON p.type_id = pt.id
                 WHERE strftime('%Y', p.due_date) = ? AND strftime('%m', p.due_date) = ?"""
        params = [str(year).zfill(4), str(month).zfill(2)]
        if address_id:
            sql += " AND p.address_id = ?"
            params.append(address_id)
        cur.execute(sql + " ORDER BY p.due_date", params)
        return [dict(row) for row in cur.fetchall()]

def mark_as_paid(payment_id, paid_date=None):
    if paid_date is None: paid_date = date.today().isoformat()
    with get_connection() as conn:
        conn.execute("UPDATE payments SET paid_date=?, status='paid' WHERE id=?", (paid_date, payment_id))
        return conn.total_changes > 0

# =============================================================================
# 📦 ПРИБОРЫ УЧЁТА
# =============================================================================
def add_meter(address_id, m_type, serial, riser=None, install_date=None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO meters (address_id, type, serial_number, riser_number, installation_date)
                       VALUES (?, ?, ?, ?, ?)""",
                    (address_id, m_type, serial, riser, install_date))
        conn.commit()
        return cur.lastrowid

def update_meter(meter_id, address_id, m_type, serial, riser=None, install_date=None):
    with get_connection() as conn:
        conn.execute("""UPDATE meters SET address_id=?, type=?, serial_number=?, riser_number=?, installation_date=?
                        WHERE id=?""",
                     (address_id, m_type, serial, riser, install_date, meter_id))
        return conn.total_changes > 0

def delete_meter(meter_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM meters WHERE id=?", (meter_id,))
        return conn.total_changes > 0

def get_all_meters():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT m.id, m.address_id, a.name as address_name, m.type, m.serial_number, m.riser_number, m.installation_date
                       FROM meters m JOIN addresses a ON m.address_id = a.id WHERE m.is_active = 1 ORDER BY a.name, m.type""")
        return [dict(row) for row in cur.fetchall()]

# =============================================================================
# 📊 ПОКАЗАНИЯ И СЧЕТА
# =============================================================================
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
        cur.execute("""INSERT INTO meter_readings (meter_id, reading_date, previous_value, current_value, consumption)
                       VALUES (?, ?, ?, ?, ?)""",
                    (meter_id, reading_date, prev_value, current_value, consumption))
        conn.commit()
        return cur.lastrowid

def get_unlinked_readings(address_id, since_date=None):
    with get_connection() as conn:
        cur = conn.cursor()
        sql = """SELECT mr.id, m.type, m.serial_number, mr.reading_date, mr.previous_value, mr.current_value, mr.consumption
                 FROM meter_readings mr JOIN meters m ON mr.meter_id = m.id
                 WHERE m.address_id = ? AND mr.invoice_id IS NULL"""
        params = [address_id]
        if since_date:
            sql += " AND mr.reading_date >= ?"
            params.append(since_date)
        cur.execute(sql + " ORDER BY mr.reading_date", params)
        return [dict(r) for r in cur.fetchall()]

def get_next_invoice_number():
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
        cur.execute("""INSERT INTO invoices (address_id, invoice_number, invoice_date, total_amount, notes)
                       VALUES (?, ?, ?, ?, ?)""",
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
    if paid_date is None: paid_date = date.today().isoformat()
    with get_connection() as conn:
        conn.execute("UPDATE invoices SET status='paid', due_date=? WHERE id=?", (paid_date, invoice_id))
        return conn.total_changes > 0

def delete_invoice(invoice_id):
    with get_connection() as conn:
        conn.execute("UPDATE meter_readings SET invoice_id = NULL WHERE invoice_id=?", (invoice_id,))
        conn.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
        return conn.total_changes > 0

# =============================================================================
# 💰 ТАРИФЫ И НОРМЫ (ЗАГЛУШКИ)
# =============================================================================
def add_tariff(type_id, rate, start_date, end_date=None):
    with get_connection() as conn:
        conn.execute("INSERT INTO tariffs (type_id, rate, start_date, end_date) VALUES (?, ?, ?, ?)", (type_id, rate, start_date, end_date))
        conn.commit()

def get_tariff(type_id, date_str):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT rate FROM tariffs WHERE type_id=? AND start_date<=? AND (end_date IS NULL OR end_date>=?) AND is_active=1
                       ORDER BY start_date DESC LIMIT 1""", (type_id, date_str, date_str))
        row = cur.fetchone()
        return row["rate"] if row else None


# =============================================================================
# 
# =============================================================================
def get_invoice_by_id(invoice_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def create_invoice(address_id, invoice_number, invoice_date, total_amount, notes="", due_date=None, reading_ids=None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO invoices (address_id, invoice_number, invoice_date, total_amount, due_date, notes) 
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (address_id, invoice_number, invoice_date, total_amount, due_date, notes))
        inv_id = cur.lastrowid
        if reading_ids:
            cur.executemany("UPDATE meter_readings SET invoice_id = ? WHERE id = ?", [(inv_id, rid) for rid in reading_ids])
        conn.commit()
        return inv_id

def update_invoice(invoice_id, invoice_number, invoice_date, total_amount, notes="", due_date=None):
    with get_connection() as conn:
        conn.execute("""UPDATE invoices SET invoice_number=?, invoice_date=?, total_amount=?, due_date=?, notes=? 
                        WHERE id=?""",
                     (invoice_number, invoice_date, total_amount, due_date, notes, invoice_id))
        conn.commit()

def cancel_invoice_payment(invoice_id):
    with get_connection() as conn:
        # Возвращаем статус в "pending" (неоплачен)
        conn.execute("UPDATE invoices SET status='pending' WHERE id=?", (invoice_id,))
        conn.commit()

# =============================================================================
# 📦 ЭКСПОРТ / ИМПОРТ СПРАВОЧНИКОВ
# =============================================================================
REFERENCE_TABLES = ["addresses", "payment_types", "meters", "tariffs", "consumption_norms"]

def export_references(filepath):
    """Экспортирует все справочники в JSON файл"""
    data = {}
    with get_connection() as conn:
        cur = conn.cursor()
        for table in REFERENCE_TABLES:
            cur.execute(f"SELECT * FROM {table}")
            data[table] = [dict(row) for row in cur.fetchall()]
            
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

def import_references(filepath):
    """Импортирует справочники из JSON файла (полная замена данных)"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Прямое подключение для управления PRAGMA foreign_keys
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with conn:
            for table in REFERENCE_TABLES:
                if table not in data: continue
                rows = data[table]
                
                # Очистка таблицы перед импортом
                conn.execute(f"DELETE FROM {table}")
                if not rows: continue
                
                cols = list(rows[0].keys())
                placeholders = ','.join(['?' for _ in cols])
                col_names = ','.join(cols)
                
                conn.executemany(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", 
                    [tuple(r[c] for c in cols) for r in rows]
                )
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()