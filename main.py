import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
from datetime import date, datetime
import calendar
import db
from config_manager import ConfigManager

try:
    from tkcalendar import Calendar
except ImportError:
    Calendar = None

METER_TYPE_MAP = {
    "electricity": "⚡ Электричество",
    "cold_water": "💧 Холодная вода",
    "hot_water": "🔥 Горячая вода"
}
METER_TYPE_REVERSE = {v: k for k, v in METER_TYPE_MAP.items()}


class CTkDateField(ctk.CTkFrame):
    """Компактное поле даты с всплывающим календарём"""
    def __init__(self, master, date_pattern="yyyy-MM-dd", placeholder="ГГГГ-ММ-ДД", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.date_pattern = date_pattern
        self.entry = ctk.CTkEntry(self, placeholder_text=placeholder)
        self.entry.pack(side="left", fill="x", expand=True)
        self.btn = ctk.CTkButton(self, text="📅", width=40, command=self._open_calendar)
        self.btn.pack(side="right", padx=(5, 0))
        self.entry.bind("<Button-1>", lambda e: self._open_calendar())
        self._cal_window = None

    def _open_calendar(self):
        if self._cal_window and self._cal_window.winfo_exists():
            self._cal_window.lift()
            return

        self._cal_window = ctk.CTkToplevel(self)
        self._cal_window.title("Выберите дату")
        self._cal_window.geometry("260x290")
        self._cal_window.resizable(False, False)
        self._cal_window.transient(self.winfo_toplevel())
        self._cal_window.grab_set()

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 5
        self._cal_window.geometry(f"+{x}+{y}")

        if Calendar:
            try:
                cal = Calendar(self._cal_window, selectmode='day', date_pattern=self.date_pattern, locale='ru_RU')
            except Exception:
                cal = Calendar(self._cal_window, selectmode='day', date_pattern=self.date_pattern)
            cal.pack(pady=10, padx=10)
            ctk.CTkButton(self._cal_window, text="✅ Выбрать", command=lambda: self._set_date(cal.get_date())).pack(pady=5)
        else:
            ctk.CTkLabel(self._cal_window, text="⚠️ Установите: pip install tkcalendar").pack(pady=20)

    def _set_date(self, date_str):
        self.entry.delete(0, "end")
        self.entry.insert(0, date_str)
        if self._cal_window and self._cal_window.winfo_exists():
            self._cal_window.destroy()

    def get_date(self): return self.entry.get().strip()
    def set_date(self, date_str):
        if date_str:
            self.entry.delete(0, "end")
            self.entry.insert(0, date_str)


class PaymentTracker(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Учёт коммунальных платежей")
        self.geometry("1150x700")

        self.config_mgr = ConfigManager()
        ctk.set_appearance_mode(self.config_mgr.get("theme", "System"))
        ctk.set_default_color_theme("blue")

        self.MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
        self.MONTH_TO_NUM = {m: i+1 for i, m in enumerate(self.MONTH_NAMES)}
        self.month_var = tk.StringVar()

        db.init_db()
        db.update_overdue_statuses()
        self.addresses = db.get_all_addresses()
        self._sort_state = {}
        self.theme_var = tk.StringVar(value=self.config_mgr.get("theme", "System"))

        self._setup_ui()
        self.load_payments()

    def _setup_ui(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        dirs_menu = tk.Menu(menubar, tearoff=0)
        dirs_menu.add_command(label="🏠 Адреса", command=self._manage_addresses)
        dirs_menu.add_command(label="📋 Типы платежей", command=self._manage_types)
        dirs_menu.add_command(label="🔧 Приборы учета", command=self._manage_meters)
        dirs_menu.add_command(label="⚙️ Настройки услуг", command=self._manage_config)
        menubar.add_cascade(label="📂 Справочники", menu=dirs_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_radiobutton(label="🌞 Светлая", variable=self.theme_var, value="Light", command=self._change_theme)
        view_menu.add_radiobutton(label="🌙 Тёмная", variable=self.theme_var, value="Dark", command=self._change_theme)
        view_menu.add_radiobutton(label="💻 Системная", variable=self.theme_var, value="System", command=self._change_theme)
        menubar.add_cascade(label="👁️ Вид", menu=view_menu)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="📤 Экспорт справочников (CSV)", command=self._export_dictionaries)
        file_menu.add_command(label="📥 Импорт справочников (CSV)", command=self._import_dictionaries)
        file_menu.add_separator()
        file_menu.add_command(label="🔄 Обновить данные", command=self.load_payments)
        file_menu.add_separator()
        file_menu.add_command(label="❌ Выход", command=self.destroy)
        menubar.add_cascade(label="📁 Файл", menu=file_menu)

        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=20, pady=(10, 10))

        # 🔹 Генерация списка месяцев (прошлый, текущий, следующий год)
        today = date.today()
        month_options = []
        for y in range(today.year - 1, today.year + 2):
            for m_name in self.MONTH_NAMES:
                month_options.append(f"{m_name} {y}")
        self.month_var.set(f"{self.MONTH_NAMES[today.month-1]} {today.year}")

        ctk.CTkLabel(header, text="📊 Платежи за ", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=10, pady=10)
        
        self.month_cb = ctk.CTkComboBox(header, values=month_options, variable=self.month_var, width=160)
        self.month_cb.pack(side="left", padx=5, pady=10)
        self.month_cb.configure(command=lambda _: self.load_payments())
        
        ctk.CTkLabel(header, text="месяц", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=(0, 10), pady=10)

        addr_names = ["📍 Все адреса"] + [a["name"] for a in self.addresses]
        self.address_var = tk.StringVar(value=addr_names[0])
        self.address_cb = ctk.CTkComboBox(header, values=addr_names, variable=self.address_var, width=200)
        self.address_cb.pack(side="left", padx=10, pady=10)
        self.address_cb.configure(command=lambda _: self.load_payments())

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right", padx=5, pady=10)

        self.btn_bill = ctk.CTkButton(btn_frame, text="📄 Счёт", fg_color="#6610f2", hover_color="#520dc2", width=90, command=self._open_bill_form)
        self.btn_bill.pack(side="left", padx=3)
        self.btn_add = ctk.CTkButton(btn_frame, text="➕ Добавить", fg_color="#28a745", hover_color="#218838", width=100, command=self._open_add_dialog)
        self.btn_add.pack(side="left", padx=3)
        self.btn_edit = ctk.CTkButton(btn_frame, text="✏️ Изменить", fg_color="#fd7e14", hover_color="#e66a00", width=100, command=self._open_edit_dialog)
        self.btn_edit.pack(side="left", padx=3)
        self.btn_paid = ctk.CTkButton(btn_frame, text="✅ Оплатить", width=90, command=self._mark_as_paid)
        self.btn_paid.pack(side="left", padx=3)
        self.btn_delete = ctk.CTkButton(btn_frame, text="🗑️ Удалить", fg_color="#dc3545", hover_color="#c82333", width=90, command=self._delete_payment)
        self.btn_delete.pack(side="left", padx=3)
        self.btn_refresh = ctk.CTkButton(btn_frame, text="🔄", width=40, command=self.load_payments)
        self.btn_refresh.pack(side="left", padx=3)

        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=20, pady=10)

        columns = ("id", "address", "type", "amount", "due", "paid", "status", "notes")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        cols_cfg = {
            "id": ("ID", 50, "center"), "address": ("Адрес", 140, "center"),
            "type": ("Тип", 130, "center"), "amount": ("Сумма, ₽", 100, "e"),
            "due": ("Срок", 100, "center"), "paid": ("Дата оплаты", 110, "center"),
            "status": ("Статус", 100, "center"), "notes": ("Примечание", 250, "center")
        }
        for col, (txt, w, anch) in cols_cfg.items():
            self._sort_state[col] = False
            self.tree.heading(col, text=txt, command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=w, anchor=anch)

        self.tree.tag_configure("overdue", foreground="#e63946", background="#fde8e8")
        self.tree.tag_configure("paid", foreground="#2d6a4f", background="#e8f5e9")
        self.tree.tag_configure("pending", foreground="#212529")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.status_bar = ctk.CTkLabel(self, text="Готово к работе", anchor="w", font=ctk.CTkFont(size=12))
        self.status_bar.pack(fill="x", padx=20, pady=(0, 10))

    def _change_theme(self):
        theme = self.theme_var.get()
        ctk.set_appearance_mode(theme)
        self.config_mgr.set("theme", theme)

    def _sort_treeview(self, col):
        self._sort_state[col] = not self._sort_state[col]
        reverse = self._sort_state[col]
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        key_type = str
        if col == "id": key_type = int
        elif col == "amount": key_type = float

        def safe_key(t):
            val = t[0]
            if not val or val == "—": return float('-inf') if key_type in (int, float) else ""
            try: return key_type(val)
            except: return 0 if key_type in (int, float) else ""

        items.sort(key=safe_key, reverse=reverse)
        for idx, (_, k) in enumerate(items):
            self.tree.move(k, '', idx)

    def load_payments(self):
        for item in self.tree.get_children(): self.tree.delete(item)

        # 🔹 Парсинг выбранного месяца
        val = self.month_var.get().strip().split()
        if len(val) == 2:
            month = self.MONTH_TO_NUM.get(val[0], date.today().month)
            year = int(val[1])
        else:
            month, year = date.today().month, date.today().year

        selected = self.address_var.get()
        addr_id = next((a["id"] for a in self.addresses if a["name"] == selected), None) if selected != "📍 Все адреса" else None

        for p in db.get_payments_by_month(year, month, addr_id):
            tag = p["status"] if p["status"] in ("overdue", "paid", "pending") else "pending"
            self.tree.insert("", "end", values=(
                p["id"], p["address_name"], p["type_name"], f"{p['amount']:.2f}",
                p["due_date"], p["paid_date"] or "—", p["status"], p["notes"] or ""
            ), tags=(tag,))

        m_name = next((k for k, v in self.MONTH_TO_NUM.items() if v == month), str(month))
        self.status_bar.configure(text=f"Загружено: {len(self.tree.get_children())} записей | {m_name} {year} | Фильтр: {selected}")

    def _export_dictionaries(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV файлы", "*.csv")], title="Сохранить справочники")
        if not filepath: return
        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['table', 'id', 'name', 'description', 'full_address', 'is_multi_apartment', 'is_recurring'])
                for a in db.get_all_addresses():
                    writer.writerow(['address', a['id'], a['name'], '', a.get('full_address', ''), a.get('is_multi_apartment', 0), ''])
                for t in db.get_all_payment_types():
                    writer.writerow(['type', t['id'], t['name'], t.get('description', ''), '', '', t.get('is_recurring', 1)])
            messagebox.showinfo("Успех", f"Справочники экспортированы:\n{filepath}")
        except Exception as e: messagebox.showerror("Ошибка", str(e))

    def _import_dictionaries(self):
        filepath = filedialog.askopenfilename(filetypes=[("CSV файлы", "*.csv")], title="Выберите файл справочников")
        if not filepath: return
        try:
            addr_count = type_count = skip_count = 0
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    table = row.get('table', '').strip().lower()
                    name = row.get('name', '').strip()
                    if not name: continue
                    try:
                        if table == 'address':
                            db.add_address(name, row.get('full_address', '').strip(), row.get('is_multi_apartment', '0').strip() == '1')
                            addr_count += 1
                        elif table == 'type':
                            db.add_payment_type(name, row.get('description', '').strip(), row.get('is_recurring', '1').strip() == '1')
                            type_count += 1
                    except Exception: skip_count += 1

            self.addresses = db.get_all_addresses()
            self.address_cb.configure(values=["📍 Все адреса"] + [a["name"] for a in self.addresses])
            self.address_var.set(self.address_cb.cget("values")[0])
            self.load_payments()
            msg = f"Импорт завершен!\n✅ Адресов: {addr_count}\n✅ Типов: {type_count}"
            if skip_count > 0: msg += f"\n⏭️ Пропущено дубликатов: {skip_count}"
            messagebox.showinfo("Результат", msg)
        except Exception as e: messagebox.showerror("Ошибка импорта", str(e))

    def _manage_meters(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("🔧 Приборы учёта")
        dlg.geometry("850x550")
        dlg.grab_set()

        frame = ctk.CTkFrame(dlg)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        tree = ttk.Treeview(frame, columns=("id", "address", "type", "serial", "riser", "date"), show="headings", selectmode="browse")
        tree.heading("id", text="ID"); tree.column("id", width=40, anchor="center")
        tree.heading("address", text="Адрес"); tree.column("address", width=180)
        tree.heading("type", text="Тип"); tree.column("type", width=140, anchor="center")
        tree.heading("serial", text="Серийный №"); tree.column("serial", width=150, anchor="center")
        tree.heading("riser", text="Стояк"); tree.column("riser", width=60, anchor="center")
        tree.heading("date", text="Дата установки"); tree.column("date", width=120, anchor="center")

        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscroll=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def refresh():
            for i in tree.get_children(): tree.delete(i)
            for m in db.get_all_meters():
                type_name = METER_TYPE_MAP.get(m["type"], m["type"])
                riser_val = m["riser_number"] if m["riser_number"] else "—"
                tree.insert("", "end", values=(m["id"], m["address_name"], type_name, m["serial_number"], riser_val, m["installation_date"] or "—"))

        refresh()

        def open_meter_dialog(existing=None):
            win = ctk.CTkToplevel(dlg)
            win.title("Редактирование ПУ" if existing else "Добавление ПУ")
            win.geometry("450x580")
            win.grab_set()
            win.resizable(False, False)

            addrs = db.get_all_addresses()
            if not addrs:
                messagebox.showwarning("Внимание", "Сначала добавьте адрес в справочниках")
                win.destroy()
                return

            ctk.CTkLabel(win, text="📍 Адрес:").pack(fill="x", padx=20, pady=(15, 0))
            if existing:
                default_addr = next((a["name"] for a in addrs if a["id"] == existing.get("address_id")), addrs[0]["name"])
            else:
                default_addr = addrs[0]["name"]
            addr_var = tk.StringVar(value=default_addr)
            ctk.CTkComboBox(win, values=[a["name"] for a in addrs], variable=addr_var).pack(fill="x", padx=20, pady=5)

            ctk.CTkLabel(win, text="⚡ Тип счётчика:").pack(fill="x", padx=20, pady=(10, 0))
            type_var = tk.StringVar(value=METER_TYPE_MAP.get(existing["type"], "⚡ Электричество") if existing else "⚡ Электричество")
            ctk.CTkComboBox(win, values=list(METER_TYPE_MAP.values()), variable=type_var).pack(fill="x", padx=20, pady=5)

            ctk.CTkLabel(win, text="🔢 Серийный номер:").pack(fill="x", padx=20, pady=(10, 0))
            serial_var = tk.StringVar(value=existing["serial_number"] if existing else "")
            ctk.CTkEntry(win, textvariable=serial_var).pack(fill="x", padx=20, pady=5)

            ctk.CTkLabel(win, text="🚿 Номер стояка (для воды):").pack(fill="x", padx=20, pady=(10, 0))
            riser_var = tk.StringVar(value=str(existing["riser_number"]) if existing and existing["riser_number"] else "")
            ctk.CTkEntry(win, textvariable=riser_var).pack(fill="x", padx=20, pady=5)

            ctk.CTkLabel(win, text="📅 Дата установки:").pack(fill="x", padx=20, pady=(10, 0))
            date_field = CTkDateField(win, date_pattern="yyyy-MM-dd", placeholder="ГГГГ-ММ-ДД")
            date_field.pack(fill="x", padx=20, pady=5)
            if existing and existing["installation_date"]:
                date_field.set_date(existing["installation_date"])

            def save():
                name = addr_var.get().strip()
                if not name: return messagebox.showwarning("Внимание", "Выберите адрес")
                addr_id = next(a["id"] for a in addrs if a["name"] == name)
                m_type = METER_TYPE_REVERSE.get(type_var.get())
                serial = serial_var.get().strip()
                if not serial: return messagebox.showwarning("Внимание", "Введите серийный номер")

                riser_str = riser_var.get().strip()
                riser = int(riser_str) if riser_str.isdigit() else None
                date_str = date_field.get_date() or None

                if existing: db.update_meter(existing["id"], addr_id, m_type, serial, riser, date_str)
                else: db.add_meter(addr_id, m_type, serial, riser, date_str)

                refresh()
                win.destroy()

            ctk.CTkButton(win, text="💾 Сохранить", command=save, fg_color="#007bff").pack(pady=15)

        def add(): open_meter_dialog()
        def edit():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите строку")
            mid = tree.item(sel[0])["values"][0]
            m = next((x for x in db.get_all_meters() if x["id"] == mid), None)
            if m: open_meter_dialog(m)
        def delete():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите строку")
            vals = tree.item(sel[0])["values"]
            if messagebox.askyesno("Удаление", f"Удалить прибор #{vals[3]} ({vals[2]})?"):
                db.delete_meter(tree.item(sel[0])["values"][0])
                refresh()

        btn_top = ctk.CTkFrame(dlg, fg_color="transparent"); btn_top.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(btn_top, text="➕ Добавить", command=add, width=120).pack(side="left", padx=5)
        btn_bot = ctk.CTkFrame(dlg, fg_color="transparent"); btn_bot.pack(fill="x", padx=10, pady=(5,10))
        ctk.CTkButton(btn_bot, text="✏️ Изменить", command=edit, width=120, fg_color="#fd7e14").pack(side="left", padx=5)
        ctk.CTkButton(btn_bot, text="🗑️ Удалить", command=delete, width=120, fg_color="#dc3545").pack(side="left", padx=5)
        ctk.CTkButton(btn_bot, text="❌ Закрыть", command=dlg.destroy, width=120).pack(side="right", padx=5)

    def _manage_config(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("⚙️ Настройки услуг и параметров")
        dlg.geometry("720x720")
        dlg.grab_set()

        params_frame = ctk.CTkFrame(dlg)
        params_frame.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(params_frame, text="📐 Параметры расчёта", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=5)

        row1 = ctk.CTkFrame(params_frame, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(row1, text="👥 Проживающих:", width=140, anchor="w").pack(side="left")
        residents_var = tk.IntVar(value=self.config_mgr.get("residents_count", 1))
        ctk.CTkEntry(row1, textvariable=residents_var, width=60).pack(side="left", padx=5)

        row2 = ctk.CTkFrame(params_frame, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(row2, text="🚿 Стояков воды:", width=140, anchor="w").pack(side="left")
        risers_var = tk.IntVar(value=self.config_mgr.get("water_risers_count", 1))
        ctk.CTkEntry(row2, textvariable=risers_var, width=60).pack(side="left", padx=5)

        row3 = ctk.CTkFrame(params_frame, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(row3, text="⚡ Тариф электричества:", width=140, anchor="w").pack(side="left")
        elec_mode_var = tk.StringVar(value="Однотарифный")
        ctk.CTkComboBox(row3, values=["Однотарифный", "Двухтарифный (День/Ночь)"],
                        variable=elec_mode_var, width=200).pack(side="left", padx=5)
        if self.config_mgr.get("electricity_mode", "single") == "day_night":
            elec_mode_var.set("Двухтарифный (День/Ночь)")

        scroll = ctk.CTkScrollableFrame(dlg, height=450)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        mkd_data = self.config_mgr.get("services_mkd", []).copy()
        house_data = self.config_mgr.get("services_house", []).copy()

        def build_section(parent, title, data_list):
            frame = ctk.CTkFrame(parent)
            frame.pack(fill="x", pady=8)
            ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=5)
            tree_frame = ctk.CTkFrame(frame, fg_color="transparent")
            tree_frame.pack(fill="x", padx=10, pady=5)
            tree = ttk.Treeview(tree_frame, columns=("name", "unit"), show="headings", height=5)
            tree.heading("name", text="Название услуги"); tree.column("name", width=300)
            tree.heading("unit", text="Ед. изм."); tree.column("unit", width=100, anchor="center")
            tree.pack(side="left", fill="both", expand=True)
            sb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
            tree.configure(yscroll=sb.set)
            sb.pack(side="right", fill="y")

            def refresh():
                for i in tree.get_children(): tree.delete(i)
                for svc in data_list: tree.insert("", "end", values=(svc["name"], svc["unit"]))

            def add():
                win = ctk.CTkToplevel(dlg); win.title("Добавить"); win.geometry("300x250"); win.grab_set()
                ctk.CTkLabel(win, text="Название:").pack(pady=(10,2)); nv = tk.StringVar(); ctk.CTkEntry(win, textvariable=nv).pack(pady=5)
                ctk.CTkLabel(win, text="Ед. изм.:").pack(pady=2); uv = tk.StringVar(value="₽"); ctk.CTkEntry(win, textvariable=uv).pack(pady=5)
                def save():
                    if nv.get().strip(): data_list.append({"name": nv.get().strip(), "unit": uv.get().strip()}); refresh(); win.destroy()
                ctk.CTkButton(win, text="➕ Добавить", command=save, fg_color="#28a745").pack(pady=15)

            def edit():
                sel = tree.selection()
                if not sel: return messagebox.showwarning("Внимание", "Выберите строку")
                idx = tree.index(sel[0])
                win = ctk.CTkToplevel(dlg); win.title("Редактировать"); win.geometry("300x250"); win.grab_set()
                ctk.CTkLabel(win, text="Название:").pack(pady=(10,2)); nv = tk.StringVar(value=data_list[idx]["name"]); ctk.CTkEntry(win, textvariable=nv).pack(pady=5)
                ctk.CTkLabel(win, text="Ед. изм.:").pack(pady=2); uv = tk.StringVar(value=data_list[idx]["unit"]); ctk.CTkEntry(win, textvariable=uv).pack(pady=5)
                def save():
                    if nv.get().strip(): data_list[idx] = {"name": nv.get().strip(), "unit": uv.get().strip()}; refresh(); win.destroy()
                ctk.CTkButton(win, text="💾 Сохранить", command=save, fg_color="#007bff").pack(pady=15)

            def delete():
                sel = tree.selection()
                if not sel: return messagebox.showwarning("Внимание", "Выберите строку")
                if messagebox.askyesno("Удаление", "Удалить эту услугу из конфига?"):
                    idx = tree.index(sel[0]); data_list.pop(idx); refresh()

            btns = ctk.CTkFrame(frame, fg_color="transparent")
            btns.pack(fill="x", padx=10, pady=5)
            ctk.CTkButton(btns, text="➕ Добавить", command=add, width=120).pack(side="left", padx=5)
            ctk.CTkButton(btns, text="✏️ Изменить", command=edit, width=120, fg_color="#fd7e14").pack(side="left", padx=5)
            ctk.CTkButton(btns, text="🗑️ Удалить", command=delete, width=120, fg_color="#dc3545").pack(side="left", padx=5)
            refresh()

        build_section(scroll, "🏢 Услуги для МКД", mkd_data)
        build_section(scroll, "🏡 Услуги для частного дома", house_data)

        def save_all():
            self.config_mgr.set("residents_count", max(1, residents_var.get()))
            self.config_mgr.set("water_risers_count", max(1, risers_var.get()))
            self.config_mgr.set("electricity_mode", "day_night" if elec_mode_var.get().startswith("Двух") else "single")
            self.config_mgr.set("services_mkd", mkd_data)
            self.config_mgr.set("services_house", house_data)
            messagebox.showinfo("Успех", "✅ Настройки сохранены в config.json")
            dlg.destroy()

        ctk.CTkButton(dlg, text="💾 Сохранить настройки", command=save_all, fg_color="#28a745", height=40).pack(pady=10, padx=10)

    def _open_bill_form(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("📄 Ввод показаний / Счёт")
        dialog.geometry("500x750")
        dialog.grab_set()

        addrs = db.get_all_addresses()
        if not addrs:
            messagebox.showwarning("Внимание", "Сначала добавьте адрес в Справочниках")
            dialog.destroy()
            return

        residents = self.config_mgr.get("residents_count", 1)
        risers = max(1, self.config_mgr.get("water_risers_count", 1))
        elec_mode = self.config_mgr.get("electricity_mode", "single")

        addr_names = [a["name"] for a in addrs]
        addr_var = tk.StringVar(value=addr_names[0])

        ctk.CTkLabel(dialog, text="📍 Выберите адрес:").pack(fill="x", padx=20, pady=(15,5))
        addr_cb = ctk.CTkComboBox(dialog, values=addr_names, variable=addr_var)
        addr_cb.pack(fill="x", padx=20)

        ctk.CTkLabel(dialog, text="📅 Дата счёта:").pack(fill="x", padx=20, pady=(10,5))
        date_field = CTkDateField(dialog, date_pattern="yyyy-MM-dd", placeholder="ГГГГ-ММ-ДД")
        date_field.pack(fill="x", padx=20, pady=5)

        info_lbl = ctk.CTkLabel(dialog, text="", font=ctk.CTkFont(size=11, slant="italic"))
        info_lbl.pack(fill="x", padx=20, pady=5)

        services_frame = ctk.CTkScrollableFrame(dialog, height=300)
        services_frame.pack(fill="both", expand=True, padx=20, pady=5)
        service_entries = {}

        def build_services():
            for widget in services_frame.winfo_children(): widget.destroy()
            service_entries.clear()

            sel_addr = next((a for a in addrs if a["name"] == addr_var.get()), None)
            is_mkd = sel_addr["is_multi_apartment"] if sel_addr else True
            services = self.config_mgr.get("services_mkd" if is_mkd else "services_house", [])

            info_lbl.configure(text=f"👥 Проживающих: {residents} | 🚿 Стояков: {risers} | ⚡ {'День/Ночь' if elec_mode=='day_night' else 'Однотарифный'}")
            ctk.CTkLabel(services_frame, text=f"{'🏢 МКД' if is_mkd else '🏡 Частный дом'} — Введите показания:",
                         font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=5)

            for svc in services:
                name = svc["name"].lower()
                unit = svc["unit"]

                if any(w in name for w in ["вода", "хвс", "гвс"]):
                    for i in range(1, risers + 1):
                        entry_name = f"{svc['name']} (Стояк {i})"
                        row = ctk.CTkFrame(services_frame, fg_color="transparent")
                        row.pack(fill="x", pady=3)
                        ctk.CTkLabel(row, text=entry_name, width=160, anchor="w").pack(side="left", padx=5)
                        entry = ctk.CTkEntry(row, width=100, placeholder_text="0.00")
                        entry.pack(side="left", padx=5)
                        ctk.CTkLabel(row, text=unit, width=50, anchor="center").pack(side="left", padx=5)
                        service_entries[entry_name] = entry
                elif any(w in name for w in ["электрич", "электро"]):
                    if elec_mode == "day_night":
                        for period in ["День", "Ночь"]:
                            entry_name = f"{svc['name']} ({period})"
                            row = ctk.CTkFrame(services_frame, fg_color="transparent")
                            row.pack(fill="x", pady=3)
                            ctk.CTkLabel(row, text=entry_name, width=160, anchor="w").pack(side="left", padx=5)
                            entry = ctk.CTkEntry(row, width=100, placeholder_text="0.00")
                            entry.pack(side="left", padx=5)
                            ctk.CTkLabel(row, text=unit, width=50, anchor="center").pack(side="left", padx=5)
                            service_entries[entry_name] = entry
                    else:
                        row = ctk.CTkFrame(services_frame, fg_color="transparent")
                        row.pack(fill="x", pady=3)
                        ctk.CTkLabel(row, text=svc["name"], width=160, anchor="w").pack(side="left", padx=5)
                        entry = ctk.CTkEntry(row, width=100, placeholder_text="0.00")
                        entry.pack(side="left", padx=5)
                        ctk.CTkLabel(row, text=unit, width=50, anchor="center").pack(side="left", padx=5)
                        service_entries[svc["name"]] = entry
                else:
                    row = ctk.CTkFrame(services_frame, fg_color="transparent")
                    row.pack(fill="x", pady=3)
                    ctk.CTkLabel(row, text=svc["name"], width=160, anchor="w").pack(side="left", padx=5)
                    entry = ctk.CTkEntry(row, width=100, placeholder_text="0.00")
                    entry.pack(side="left", padx=5)
                    ctk.CTkLabel(row, text=unit, width=50, anchor="center").pack(side="left", padx=5)
                    service_entries[svc["name"]] = entry

        addr_var.trace_add("write", lambda *_: build_services())
        build_services()

        def save_bill():
            try:
                due_date = date_field.get_date()
                if not due_date: raise ValueError("Выберите дату")
                sel_addr = next(a for a in addrs if a["name"] == addr_var.get())
                count = 0
                for svc_name, entry in service_entries.items():
                    val = entry.get().strip().replace(",", ".")
                    if not val or val == "0": continue
                    amount = float(val)
                    type_id = db.get_or_create_payment_type(svc_name, is_recurring=True)
                    db.add_payment(sel_addr["id"], type_id, amount, due_date)
                    count += 1
                dialog.destroy()
                self.load_payments()
                self.status_bar.configure(text=f"📄 Сохранено {count} записей за {due_date}")
            except Exception as e: messagebox.showerror("Ошибка", str(e))

        ctk.CTkButton(dialog, text="💾 Сохранить счёт", command=save_bill, fg_color="#6610f2").pack(pady=15)

    def _manage_addresses(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Управление адресами")
        dlg.geometry("1000x550")
        dlg.grab_set()

        frame = ctk.CTkFrame(dlg)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        cols = ("id", "name", "account", "full", "mkd", "total_a", "actual_a", "rooms", "gas", "reg")
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")

        col_cfg = {
            "id": ("ID", 40, "center"), "name": ("Ярлык", 120, "w"),
            "account": ("Лиц. счёт", 90, "center"), "full": ("Полный адрес", 220, "w"),
            "mkd": ("МКД", 50, "center"), "total_a": ("Общ. м²", 70, "center"),
            "actual_a": ("Факт. м²", 70, "center"), "rooms": ("Комн.", 50, "center"),
            "gas": ("Газ", 50, "center"), "reg": ("Проп.", 50, "center")
        }
        for c, (txt, w, anch) in col_cfg.items():
            tree.heading(c, text=txt)
            tree.column(c, width=w, anchor=anch)

        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscroll=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def refresh():
            for i in tree.get_children(): tree.delete(i)
            for a in db.get_all_addresses():
                tree.insert("", "end", values=(
                    a["id"], a["name"], a.get("account_number") or "—",
                    a.get("full_address") or "",
                    "✅" if a.get("is_multi_apartment") else "❌",
                    a.get("total_area") or 0.0, a.get("actual_area") or 0.0,
                    a.get("rooms_count") or 1,
                    "✅" if a.get("is_gasified") else "❌",
                    a.get("registered_count") or 1
                ))
        refresh()

        def open_edit(existing=None):
            edit_dlg = ctk.CTkToplevel(dlg)
            edit_dlg.title("Редактирование адреса" if existing else "Новый адрес")
            edit_dlg.geometry("480x780")
            edit_dlg.grab_set()
            edit_dlg.resizable(False, False)

            n_var = tk.StringVar(value=existing["name"] if existing else "")
            f_var = tk.StringVar(value=existing.get("full_address") or "")
            mkd_var = tk.BooleanVar(value=bool(existing.get("is_multi_apartment")) if existing else False)
            acc_var = tk.StringVar(value=existing.get("account_number") or "")
            total_a_var = tk.StringVar(value=str(existing.get("total_area") or 0.0))
            actual_a_var = tk.StringVar(value=str(existing.get("actual_area") or 0.0))
            rooms_var = tk.StringVar(value=str(existing.get("rooms_count") or 1))
            reg_var = tk.StringVar(value=str(existing.get("registered_count") or 1))
            gas_var = tk.BooleanVar(value=bool(existing.get("is_gasified")) if existing else False)

            def pack_field(lbl, var, width=120):
                row = ctk.CTkFrame(edit_dlg, fg_color="transparent")
                row.pack(fill="x", padx=20, pady=4)
                ctk.CTkLabel(row, text=lbl, width=150, anchor="w").pack(side="left")
                ctk.CTkEntry(row, textvariable=var, width=width).pack(side="left", padx=5)

            ctk.CTkLabel(edit_dlg, text="📍 Название / Ярлык:").pack(fill="x", padx=20, pady=(10, 2))
            ctk.CTkEntry(edit_dlg, textvariable=n_var).pack(fill="x", padx=20)
            ctk.CTkLabel(edit_dlg, text="🏠 Полный адрес:").pack(fill="x", padx=20, pady=(6, 2))
            ctk.CTkEntry(edit_dlg, textvariable=f_var).pack(fill="x", padx=20)
            ctk.CTkCheckBox(edit_dlg, text="🏢 Это многоквартирный дом", variable=mkd_var).pack(fill="x", padx=20, pady=4)
            pack_field("💳 Лицевой счёт:", acc_var, 100)
            pack_field("Площадь общая (м²):", total_a_var, 80)
            pack_field("Площадь факт. (м²):", actual_a_var, 80)
            pack_field("Количество комнат:", rooms_var, 60)
            pack_field("Прописано человек:", reg_var, 60)
            ctk.CTkCheckBox(edit_dlg, text="🔥 Дом газифицирован", variable=gas_var).pack(fill="x", padx=20, pady=6)

            def save():
                name = n_var.get().strip()
                full = f_var.get().strip()
                if not name:
                    return messagebox.showwarning("Внимание", "Введите название")
                try:
                    total_a = float(total_a_var.get().replace(',', '.').strip() or 0)
                    actual_a = float(actual_a_var.get().replace(',', '.').strip() or 0)
                    rooms = int(rooms_var.get().strip() or 1)
                    reg = int(reg_var.get().strip() or 1)
                except ValueError:
                    return messagebox.showerror("Ошибка", "Проверьте числовые поля (допустимы только цифры и точка)!")

                if existing:
                    db.update_address(existing["id"], name, full, mkd_var.get(),
                                      total_a, actual_a, rooms, gas_var.get(), acc_var.get().strip(), reg)
                else:
                    db.add_address(name, full, mkd_var.get(),
                                   total_a, actual_a, rooms, gas_var.get(), acc_var.get().strip(), reg)

                refresh()
                self._sync_main_address_list()
                edit_dlg.destroy()

            ctk.CTkButton(edit_dlg, text="💾 Сохранить", command=save, fg_color="#007bff").pack(pady=15)

        def edit_selected():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите строку")
            addr = next((a for a in db.get_all_addresses() if a["id"] == tree.item(sel[0])["values"][0]), None)
            if addr: open_edit(addr)

        def delete_selected():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите строку")
            vals = tree.item(sel[0])["values"]
            if messagebox.askyesno("Удаление", f"Удалить адрес '{vals[1]}'?\n⚠️ Все связанные платежи будут удалены!"):
                db.delete_address(vals[0])
                refresh()
                self._sync_main_address_list()
                self.load_payments()

        btn_top = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_top.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(btn_top, text="➕ Добавить", command=lambda: open_edit(), width=120).pack(side="left", padx=5)

        btn_bot = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_bot.pack(fill="x", padx=10, pady=(5, 10))
        ctk.CTkButton(btn_bot, text="✏️ Изменить", fg_color="#fd7e14", command=edit_selected, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_bot, text="🗑️ Удалить", fg_color="#dc3545", command=delete_selected, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_bot, text="❌ Закрыть", command=dlg.destroy, width=120).pack(side="right", padx=5)

    def _manage_types(self):
        dlg = ctk.CTkToplevel(self); dlg.title("Управление типами платежей"); dlg.geometry("600x400"); dlg.grab_set()
        frame = ctk.CTkFrame(dlg); frame.pack(fill="both", expand=True, padx=10, pady=10)
        tree = ttk.Treeview(frame, columns=("id", "name", "desc", "rec"), show="headings", selectmode="browse")
        tree.heading("id", text="ID"); tree.column("id", width=40, anchor="center")
        tree.heading("name", text="Название"); tree.column("name", width=200)
        tree.heading("desc", text="Описание"); tree.column("desc", width=250)
        tree.heading("rec", text="Регул."); tree.column("rec", width=60, anchor="center")
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview); tree.configure(yscroll=sb.set)
        tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        def refresh():
            for i in tree.get_children(): tree.delete(i)
            for t in db.get_all_payment_types(): tree.insert("", "end", values=(t["id"], t["name"], t["description"], "✅" if t["is_recurring"] else "❌"))
        refresh()
        def open_edit(existing=None):
            edit_dlg = ctk.CTkToplevel(dlg); edit_dlg.title("Редактирование типа" if existing else "Новый тип"); edit_dlg.geometry("400x300"); edit_dlg.grab_set(); edit_dlg.resizable(False, False)
            ctk.CTkLabel(edit_dlg, text="Название:").pack(fill="x", padx=20, pady=(10,5))
            n_var = tk.StringVar(value=existing["name"] if existing else ""); ctk.CTkEntry(edit_dlg, textvariable=n_var).pack(fill="x", padx=20)
            ctk.CTkLabel(edit_dlg, text="Описание:").pack(fill="x", padx=20, pady=(10,5))
            d_var = tk.StringVar(value=existing["description"] if existing else ""); ctk.CTkEntry(edit_dlg, textvariable=d_var).pack(fill="x", padx=20)
            is_rec_var = tk.BooleanVar(value=bool(existing["is_recurring"]) if existing else True)
            ctk.CTkCheckBox(edit_dlg, text="🔄 Регулярный платёж", variable=is_rec_var).pack(fill="x", padx=20, pady=10)
            def save():
                name, desc = n_var.get().strip(), d_var.get().strip()
                if not name: return messagebox.showwarning("Внимание", "Введите название")
                if existing: db.update_payment_type(existing["id"], name, desc, is_rec_var.get())
                else: db.add_payment_type(name, desc, is_rec_var.get())
                refresh(); edit_dlg.destroy()
            ctk.CTkButton(edit_dlg, text="💾 Сохранить", command=save, fg_color="#007bff").pack(pady=15)
        def edit_selected():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите строку")
            t = next((x for x in db.get_all_payment_types() if x["id"] == tree.item(sel[0])["values"][0]), None)
            if t: open_edit(t)
        def delete_selected():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите строку")
            vals = tree.item(sel[0])["values"]
            if messagebox.askyesno("Удаление", f"Удалить тип '{vals[1]}'?\n⚠️ Все связанные платежи будут удалены!"):
                db.delete_payment_type(vals[0]); refresh()
        btn_top = ctk.CTkFrame(dlg, fg_color="transparent"); btn_top.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(btn_top, text="➕ Добавить", command=lambda: open_edit()).pack(side="left", padx=5)
        btn_bot = ctk.CTkFrame(dlg, fg_color="transparent"); btn_bot.pack(fill="x", padx=10, pady=(5,10))
        ctk.CTkButton(btn_bot, text="✏️ Изменить", fg_color="#fd7e14", command=edit_selected).pack(side="left", padx=5)
        ctk.CTkButton(btn_bot, text="🗑️ Удалить", fg_color="#dc3545", command=delete_selected).pack(side="left", padx=5)
        ctk.CTkButton(btn_bot, text="❌ Закрыть", command=dlg.destroy).pack(side="right", padx=5)

    def _sync_main_address_list(self):
        self.addresses = db.get_all_addresses()
        new_vals = ["📍 Все адреса"] + [a["name"] for a in self.addresses]
        self.address_cb.configure(values=new_vals)
        current = self.address_var.get()
        if current not in new_vals: self.address_var.set(new_vals[0])

    def _open_add_dialog(self):
        dialog = ctk.CTkToplevel(self); dialog.title("Новый платёж"); dialog.geometry("440x640"); dialog.grab_set()
        addrs = db.get_all_addresses()
        if not addrs: messagebox.showerror("Внимание", "Сначала добавьте адрес в Справочниках"); dialog.destroy(); return
        types = db.get_all_payment_types()
        if not types: messagebox.showerror("Внимание", "Справочник типов пуст"); dialog.destroy(); return

        a_names = [a["name"] for a in addrs]; t_names = [t["name"] for t in types]
        ctk.CTkLabel(dialog, text="📍 Адрес:").pack(fill="x", padx=20, pady=(15,5))
        a_var = tk.StringVar(value=a_names[0]); ctk.CTkComboBox(dialog, values=a_names, variable=a_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="Тип:").pack(fill="x", padx=20, pady=(10,5))
        t_var = tk.StringVar(value=t_names[0]); ctk.CTkComboBox(dialog, values=t_names, variable=t_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="Сумма:").pack(fill="x", padx=20, pady=(10,5))
        amt_var = tk.StringVar(value="0.00"); ctk.CTkEntry(dialog, textvariable=amt_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="Срок:").pack(fill="x", padx=20, pady=(10,5))
        date_field = CTkDateField(dialog, date_pattern="yyyy-MM-dd", placeholder="ГГГГ-ММ-ДД")
        date_field.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(dialog, text="Примечание:").pack(fill="x", padx=20, pady=(10,5))
        n_var = tk.StringVar(); ctk.CTkEntry(dialog, textvariable=n_var).pack(fill="x", padx=20)

        def save():
            try:
                aid = next(a["id"] for a in addrs if a["name"]==a_var.get())
                tid = next(t["id"] for t in types if t["name"]==t_var.get())
                amt = float(amt_var.get().replace(",", "."))
                if amt < 0: raise ValueError("Сумма > 0")
                due = date_field.get_date()
                if not due: raise ValueError("Выберите дату")
                db.add_payment(aid, tid, amt, due, n_var.get().strip())
                dialog.destroy(); self.load_payments(); self.status_bar.configure(text="🎉 Добавлено")
            except Exception as e: messagebox.showerror("Ошибка", str(e))
        ctk.CTkButton(dialog, text="💾 Сохранить", command=save, fg_color="#007bff").pack(pady=20)

    def _open_edit_dialog(self):
        sel = self.tree.selection()
        if not sel: return messagebox.showwarning("Внимание", "Выберите строку!")
        vals = self.tree.item(sel[0])["values"]
        pid, cur_addr, cur_type, cur_amt, cur_due, _, _, cur_notes = vals
        dlg = ctk.CTkToplevel(self); dlg.title(f"Редактирование #{pid}"); dlg.geometry("440x640"); dlg.grab_set()
        addrs = db.get_all_addresses(); types = db.get_all_payment_types()
        if not addrs or not types: return messagebox.showerror("Ошибка", "Справочники пусты.")
        a_names = [a["name"] for a in addrs]; t_names = [t["name"] for t in types]
        ctk.CTkLabel(dlg, text="📍 Адрес:").pack(fill="x", padx=20, pady=(15,5))
        a_var = tk.StringVar(value=cur_addr if cur_addr in a_names else a_names[0]); ctk.CTkComboBox(dlg, values=a_names, variable=a_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dlg, text="Тип:").pack(fill="x", padx=20, pady=(10,5))
        t_var = tk.StringVar(value=cur_type if cur_type in t_names else t_names[0]); ctk.CTkComboBox(dlg, values=t_names, variable=t_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dlg, text="Сумма:").pack(fill="x", padx=20, pady=(10,5))
        amt_var = tk.StringVar(value=str(cur_amt)); ctk.CTkEntry(dlg, textvariable=amt_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dlg, text="Срок:").pack(fill="x", padx=20, pady=(10,5))
        date_field = CTkDateField(dlg, date_pattern="yyyy-MM-dd", placeholder="ГГГГ-ММ-ДД")
        date_field.pack(fill="x", padx=20, pady=5)
        if cur_due and cur_due != "—": date_field.set_date(cur_due)
        ctk.CTkLabel(dlg, text="Примечание:").pack(fill="x", padx=20, pady=(10,5))
        n_var = tk.StringVar(value=cur_notes if cur_notes != "—" else ""); ctk.CTkEntry(dlg, textvariable=n_var).pack(fill="x", padx=20)

        def save():
            try:
                aid = next(a["id"] for a in addrs if a["name"]==a_var.get())
                tid = next(t["id"] for t in types if t["name"]==t_var.get())
                amt = float(amt_var.get().replace(",", ".")); due = date_field.get_date()
                if not due: raise ValueError("Выберите дату")
                db.update_payment(pid, aid, tid, amt, due, n_var.get().strip())
                dlg.destroy(); self.load_payments(); self.status_bar.configure(text="✏️ Обновлено")
            except Exception as e: messagebox.showerror("Ошибка", str(e))
        ctk.CTkButton(dlg, text="💾 Сохранить", command=save, fg_color="#fd7e14").pack(pady=20)

    def _mark_as_paid(self):
        sel = self.tree.selection()
        if not sel: return messagebox.showwarning("Внимание", "Выберите строку!")
        vals = self.tree.item(sel[0])["values"]
        pid, status = vals[0], vals[6]
        if status == "paid": return messagebox.showinfo("Инфо", "Уже оплачен")
        if not messagebox.askyesno("Подтверждение", f"Отметить #{pid} как оплаченный?"): return

        db.mark_as_paid(pid)
        payment_data = db.get_payment(pid)
        recurring_msg = ""
        if payment_data and payment_data.get("is_recurring") == 1:
            try:
                due_dt = datetime.strptime(payment_data["due_date"], "%Y-%m-%d")
                year, month = due_dt.year, due_dt.month + 1
                if month > 12: month, year = 1, year + 1
                max_day = calendar.monthrange(year, month)[1]
                day = min(due_dt.day, max_day)
                next_due_date = datetime(year, month, day).strftime("%Y-%m-%d")
                db.add_payment(payment_data["address_id"], payment_data["type_id"], payment_data["amount"], next_due_date, payment_data["notes"])
                recurring_msg = " | 🔄 Автоматически создан платёж на след. месяц"
            except Exception as e:
                print(f"⚠️ Ошибка создания регулярного платежа: {e}")

        self.load_payments()
        self.status_bar.configure(text=f"✅ Оплачен #{pid}{recurring_msg}")

    def _delete_payment(self):
        sel = self.tree.selection()
        if not sel: return messagebox.showwarning("Внимание", "Выберите строку!")
        vals = self.tree.item(sel[0])["values"]
        if messagebox.askyesno("Удаление", f"Удалить {vals[1]} | {vals[2]} | {vals[3]}₽?\nДействие необратимо."):
            if db.delete_payment(vals[0]): self.load_payments(); self.status_bar.configure(text="🗑️ Удалено")


if __name__ == "__main__":
    PaymentTracker().mainloop()