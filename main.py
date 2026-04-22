import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date, datetime
import calendar
import db
from config_manager import ConfigManager

try:
    from tkcalendar import Calendar
except ImportError:
    Calendar = None

# 🔹 Константы
METER_TYPE_MAP = {
    "electricity": "⚡ Электричество",
    "cold_water": "💧 Холодная вода",
    "hot_water": "🔥 Горячая вода",
    "heat": "🌡️ Отопление",
    "gas": "🔥 Газ"
}
STATUS_RU = {"pending": "⏳ Ожидает", "paid": "✅ Оплачен"}


class CTkDateField(ctk.CTkFrame):
    """Компактное поле даты с календарём"""
    def __init__(self, master, placeholder="ГГГГ-ММ-ДД", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.entry = ctk.CTkEntry(self, placeholder_text=placeholder)
        self.entry.pack(side="left", fill="x", expand=True)
        self.btn = ctk.CTkButton(self, text="📅", width=40, command=self._open_calendar)
        self.btn.pack(side="right", padx=(5, 0))
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
        self._cal_window.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height() + 5}")

        if Calendar:
            try: cal = Calendar(self._cal_window, selectmode='day', locale='ru_RU')
            except Exception: cal = Calendar(self._cal_window, selectmode='day')
            cal.pack(pady=10, padx=10)
            ctk.CTkButton(self._cal_window, text="✅ Выбрать", command=lambda: self._set_date(cal.get_date())).pack(pady=5)
        else:
            ctk.CTkLabel(self._cal_window, text="⚠️ pip install tkcalendar").pack(pady=20)

    def _set_date(self, d):
        self.entry.delete(0, "end")
        self.entry.insert(0, d)
        if self._cal_window and self._cal_window.winfo_exists():
            self._cal_window.destroy()

    def get_date(self): return self.entry.get().strip()
    def set_date(self, d):
        if d:
            self.entry.delete(0, "end")
            self.entry.insert(0, d)


class PaymentTracker(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Учёт коммунальных платежей")
        self.geometry("1350x750")
        self.config_mgr = ConfigManager()
        ctk.set_appearance_mode(self.config_mgr.get("theme", "System"))
        ctk.set_default_color_theme("blue")
        
        self.MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
        self.MONTH_TO_NUM = {m: i+1 for i, m in enumerate(self.MONTH_NAMES)}
        self.month_var = tk.StringVar()
        self.year_var = tk.StringVar()

        db.init_db()
        self.addresses = db.get_all_addresses()
        self._sort_state = {}
        self.theme_var = tk.StringVar(value=self.config_mgr.get("theme", "System"))

        self._setup_ui()
        self.load_invoices()

    def _setup_ui(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        dirs_menu = tk.Menu(menubar, tearoff=0)
        dirs_menu.add_command(label="🏠 Адреса", command=self._manage_addresses)
        dirs_menu.add_command(label="📋 Типы платежей", command=self._manage_types)
        dirs_menu.add_command(label="🔧 Приборы учета", command=self._manage_meters)
        menubar.add_cascade(label="📂 Справочники", menu=dirs_menu)
        
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="⚙️ Открыть настройки", command=self._open_settings)
        menubar.add_cascade(label="⚙️ Настройки", menu=settings_menu)        

        view_menu = tk.Menu(menubar, tearoff=0)
        for lbl, val in [("🌞 Светлая", "Light"), ("🌙 Тёмная", "Dark"), ("💻 Системная", "System")]:
            view_menu.add_radiobutton(label=lbl, variable=self.theme_var, value=val, 
                                      command=lambda v=val: (ctk.set_appearance_mode(v), self.config_mgr.set("theme", v)))
        menubar.add_cascade(label="👁️ Вид", menu=view_menu)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="📤 Экспорт", command=self._export_data)
        file_menu.add_command(label="📥 Импорт", command=self._import_data)
        file_menu.add_separator()
        file_menu.add_command(label="❌ Выход", command=self.destroy)
        menubar.add_cascade(label="📁 Файл", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="ℹ️ О программе", command=self._show_about)
        help_menu.add_command(label="❓ Помощь", command=self._show_help)
        menubar.add_cascade(label="❓", menu=help_menu)

        # 🔹 Шапка
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=20, pady=10)

        today = date.today()
        years = [str(y) for y in range(today.year - 10, today.year + 11)]
        self.month_var.set(self.MONTH_NAMES[today.month-1])
        self.year_var.set(str(today.year))

        ctk.CTkLabel(header, text="📊 Счета за:  ", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=10, pady=10)
        
        self.month_cb = ctk.CTkComboBox(header, values=self.MONTH_NAMES, variable=self.month_var, width=120)
        self.month_cb.pack(side="left", padx=2, pady=10)
        
        self.year_cb = ctk.CTkComboBox(header, values=years, variable=self.year_var, width=80)
        self.year_cb.pack(side="left", padx=5, pady=10)

        self.month_var.trace_add("write", lambda *_: self.load_invoices())
        self.year_var.trace_add("write", lambda *_: self.load_invoices())

        addr_names = ["📍 Все адреса"] + [a["name"] for a in self.addresses]
        self.address_var = tk.StringVar(value=addr_names[0])
        self.address_cb = ctk.CTkComboBox(header, values=addr_names, variable=self.address_var, width=200)
        self.address_cb.pack(side="left", padx=10, pady=10)
        self.address_cb.configure(command=lambda _: self.load_invoices())

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right", padx=5)

        ctk.CTkButton(btn_frame, text="📊 Передать показания", fg_color="#17a2b8", hover_color="#138496", width=160, command=self._open_readings_form).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="📄 Создать счёт", fg_color="#6610f2", hover_color="#520dc2", width=130, command=self._open_invoice_form).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="✅ Оплатить", width=90, command=self._mark_paid).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="↩️ Отменить", fg_color="#fd7e14", hover_color="#e66a00", width=100, command=self._cancel_payment).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="✏️ Редакт.", fg_color="#28a745", hover_color="#218838", width=100, command=self._edit_invoice).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="🗑️ Удалить", fg_color="#dc3545", hover_color="#c82333", width=90, command=self._delete_invoice).pack(side="left", padx=3)

        # 🔹 Таблица счетов
        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=20, pady=10)

        cols = ("id", "number", "address", "amount", "date", "status", "notes")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        
        cfg = {
            "id": ("ID", 40), "number": ("№ Счёта", 140), "address": ("Адрес", 200), 
            "amount": ("Сумма, ₽", 100), "date": ("Дата", 100), "status": ("Статус", 100), "notes": ("Примечание", 300)
        }
        for c, (t, w) in cfg.items():
            self._sort_state[c] = False
            self.tree.heading(c, text=t, command=lambda col=c: self._sort_tree(col))
            self.tree.column(c, width=w, anchor="center" if c != "address" else "w")

        self.tree.tag_configure("pending", foreground="#856404", background="#fff3cd")
        self.tree.tag_configure("paid", foreground="#155724", background="#d4edda")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 🔹 Нижняя панель: статус слева, версия справа
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=20, pady=5)

        self.status_bar = ctk.CTkLabel(bottom_frame, text="Готово", anchor="w", font=ctk.CTkFont(size=12))
        self.status_bar.pack(side="left", fill="x", expand=True)

        self.version_label = ctk.CTkLabel(bottom_frame, text="Версия ПО 1.0.0", anchor="e", font=ctk.CTkFont(size=11, weight="bold"))
        self.version_label.pack(side="right")

    def _sort_tree(self, col):
        self._sort_state[col] = not self._sort_state[col]
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        key = float if col == "amount" else int if col == "id" else str
        items.sort(key=lambda x: key(x[0]) if x[0] not in ("", "—") else 0, reverse=self._sort_state[col])
        for i, (_, k) in enumerate(items):
            self.tree.move(k, '', i)

    def load_invoices(self):
        if not hasattr(self, 'tree') or self.tree is None:
            return
        for i in self.tree.get_children():
            self.tree.delete(i)
        try:
            month = self.MONTH_TO_NUM.get(self.month_var.get().strip(), date.today().month)
            year = int(self.year_var.get().strip())
        except Exception:
            month, year = date.today().month, date.today().year
        
        addr_name = self.address_var.get()
        addr_id = next((a["id"] for a in self.addresses if a["name"] == addr_name), None) if addr_name != "📍 Все адреса" else None

        for inv in db.get_invoices(year, month, addr_id):
            tag = "paid" if inv["status"] == "paid" else "pending"
            self.tree.insert("", "end", values=(
                inv["id"], inv["invoice_number"], inv["address_name"], 
                f"{inv['total_amount']:.2f}", inv["invoice_date"], 
                STATUS_RU.get(inv["status"], inv["status"]), inv["notes"] or ""
            ), tags=(tag,))
        self.status_bar.configure(text=f"Загружено: {len(self.tree.get_children())} счетов | {self.month_var.get()} {self.year_var.get()}")

    # 🔹 ФОРМА ПЕРЕДАЧИ ПОКАЗАНИЙ
    def _open_readings_form(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("📊 Передача показаний")
        dlg.geometry("600x600")
        dlg.grab_set()

        addrs = db.get_all_addresses()
        if not addrs:
            messagebox.showwarning("Внимание", "Добавьте адрес в справочниках")
            return

        ctk.CTkLabel(dlg, text="📍 Адрес: ").pack(fill="x", padx=20, pady=5)
        addr_var = tk.StringVar(value=addrs[0]["name"])
        ctk.CTkComboBox(dlg, values=[a["name"] for a in addrs], variable=addr_var).pack(fill="x", padx=20)

        ctk.CTkLabel(dlg, text="📅 Дата передачи: ").pack(fill="x", padx=20, pady=5)
        date_field = CTkDateField(dlg, placeholder="ГГГГ-ММ-ДД")
        date_field.pack(fill="x", padx=20)
        date_field.set_date(date.today().isoformat())

        ctk.CTkLabel(dlg, text="📟 Показания (пустые поля): ", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=20, pady=(15,5))
        
        frame = ctk.CTkScrollableFrame(dlg, height=300)
        frame.pack(fill="both", expand=True, padx=20, pady=5)
        inputs = {}

        def build():
            for w in frame.winfo_children(): w.destroy()
            inputs.clear()
            sel = next((a for a in addrs if a["name"] == addr_var.get()), None)
            if not sel: return
            
            for m in [x for x in db.get_all_meters() if x["address_id"] == sel["id"]]:
                last = db.get_last_reading(m["id"])
                prev = last["current_value"] if last else 0.0
                
                row = ctk.CTkFrame(frame, fg_color="transparent")
                row.pack(fill="x", pady=3)
                ctk.CTkLabel(row, text=f"{METER_TYPE_MAP.get(m['type'], m['type'])} | {m['serial_number']}", width=200, anchor="w").pack(side="left", padx=5)
                ctk.CTkLabel(row, text=f"(Предыд: {prev})", width=90, fg_color="gray").pack(side="left", padx=2)
                var = tk.StringVar(value="")
                ctk.CTkEntry(row, textvariable=var, width=100, placeholder_text="Введите").pack(side="left", padx=5)
                inputs[m["id"]] = (prev, var)

        addr_var.trace_add("write", lambda *_: build())
        build()

        def save():
            try:
                d = date_field.get_date()
                if not d: raise ValueError("Укажите дату")
                
                sel = next(a for a in addrs if a["name"] == addr_var.get())
                count = 0
                for mid, (prev, var) in inputs.items():
                    v = var.get().strip().replace(",", ".")
                    if not v: continue
                    cur = float(v)
                    if cur < prev:
                        messagebox.showwarning("Ошибка", f"Показания меньше предыдущих ({prev})!")
                        return
                    if cur == prev: continue
                    db.save_meter_reading(mid, d, cur)
                    count += 1
                dlg.destroy()
                self.status_bar.configure(text=f"✅ Сохранено: {count} показаний")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

        ctk.CTkButton(dlg, text="💾 Сохранить показания", command=save, fg_color="#17a2b8").pack(pady=10)

    # 🔹 ФОРМА СОЗДАНИЯ СЧЁТА (НОВАЯ ЛОГИКА)
    def _open_invoice_form(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("📄 Создание счёта")
        dlg.geometry("750x740")  # Увеличена высота для нового поля
        dlg.grab_set()

        addrs = db.get_all_addresses()
        if not addrs: return

        # 1. Адрес (пустой по умолчанию)
        ctk.CTkLabel(dlg, text="📍 Адрес: ").pack(fill="x", padx=20, pady=5)
        addr_var = tk.StringVar()
        ctk.CTkComboBox(dlg, values=[a["name"] for a in addrs], variable=addr_var).pack(fill="x", padx=20)

        # 2. Дата счёта
        ctk.CTkLabel(dlg, text="📅 Дата счёта: ").pack(fill="x", padx=20, pady=5)
        date_field = CTkDateField(dlg, placeholder="ГГГГ-ММ-ДД")
        date_field.pack(fill="x", padx=20)
        date_field.set_date(date.today().isoformat())

        # 🔹 3. НОВОЕ ПОЛЕ: Срок оплаты
        ctk.CTkLabel(dlg, text="⏳ Оплатить до: ").pack(fill="x", padx=20, pady=5)
        due_date_field = CTkDateField(dlg, placeholder="ГГГГ-ММ-ДД")
        due_date_field.pack(fill="x", padx=20)
        # Автоподстановка: сегодня + 10 дней
        try:
            from datetime import timedelta
            due_date_field.set_date((date.today() + timedelta(days=10)).isoformat())
        except Exception: pass

        # 4. Тип платежа (из справочника)
        ctk.CTkLabel(dlg, text="💳 Тип платежа: ").pack(fill="x", padx=20, pady=5)
        types = db.get_all_payment_types()
        type_names = [t["name"] for t in types] if types else ["Не выбран"]
        type_var = tk.StringVar(value=type_names[0])
        ctk.CTkComboBox(dlg, values=type_names, variable=type_var).pack(fill="x", padx=20)

        # 5. Номер счёта (ручной ввод)
        ctk.CTkLabel(dlg, text="№ Счёта: ", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=20, pady=5)
        inv_var = tk.StringVar()
        ctk.CTkEntry(dlg, textvariable=inv_var, width=150).pack(anchor="w", padx=20)

        # 6. Сумма (пустая)
        ctk.CTkLabel(dlg, text="💰 Сумма к оплате (₽): ", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=20, pady=(10,5))
        amt_var = tk.StringVar()
        ctk.CTkEntry(dlg, textvariable=amt_var, font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", padx=20, pady=5)

        # 7. Привязанные показания (скрыто по умолчанию)
        readings_container = ctk.CTkFrame(dlg, fg_color="transparent")
        ctk.CTkLabel(readings_container, text="📟 Привязанные показания: ", font=ctk.CTkFont(size=12)).pack(fill="x", padx=0, pady=5)
        tree_frame = ctk.CTkFrame(readings_container)
        tree_frame.pack(fill="both", expand=True, padx=0, pady=5)

        cols_cfg = [("type", "Тип", 120), ("sn", "SN", 120), ("prev", "Предыд.", 80), ("cur", "Тек.", 80), ("cons", "Расход", 80)]
        tree = ttk.Treeview(tree_frame, columns=[c[0] for c in cols_cfg], show="headings", height=6)
        for col_id, col_name, w in cols_cfg:
            tree.heading(col_id, text=col_name)
            tree.column(col_id, width=w, anchor="center")
        tree.pack(fill="both", expand=True)
        
        readings_container.pack_forget()

        def load_readings():
            for i in tree.get_children(): tree.delete(i)
            sel_name = addr_var.get()
            if not sel_name: return
            sel = next((a for a in addrs if a["name"] == sel_name), None)
            if not sel: return
            month_start = f"{date.today().year}-{date.today().month:02d}-01"
            for r in db.get_unlinked_readings(sel["id"], since_date=month_start):
                tree.insert("", "end", values=(
                    METER_TYPE_MAP.get(r["type"], r["type"]), r["serial_number"],
                    r["previous_value"], r["current_value"], r["consumption"]
                ))

        def toggle_readings(*_):
            is_utility = type_var.get().strip().lower() == "коммунальные платежи"
            if is_utility:
                readings_container.pack(fill="both", expand=True, padx=20, pady=5)
                load_readings()
            else:
                readings_container.pack_forget()

        type_var.trace_add("write", toggle_readings)
        addr_var.trace_add("write", lambda *_: load_readings() if readings_container.winfo_ismapped() else None)

        def save():
            try:
                d = date_field.get_date()
                if not d: raise ValueError("Укажите дату счёта")
                if not addr_var.get(): raise ValueError("Выберите адрес")
                if not type_var.get(): raise ValueError("Выберите тип платежа")
                inv_num = inv_var.get().strip()
                if not inv_num: raise ValueError("Введите номер счёта вручную")

                sel = next(a for a in addrs if a["name"] == addr_var.get())
                amt = float(amt_var.get().replace(",", "."))
                due_date = due_date_field.get_date() or None  # 🔹 Забираем значение нового поля

                reading_ids = []
                if type_var.get().strip().lower() == "коммунальные платежи":
                    month_start = f"{date.today().year}-{date.today().month:02d}-01"
                    reading_ids = [r["id"] for r in db.get_unlinked_readings(sel["id"], since_date=month_start)]

                # Передаём due_date в БД
                db.create_invoice(sel["id"], inv_num, d, amt, due_date=due_date, reading_ids=reading_ids)
                dlg.destroy()
                self.load_invoices()
                self.status_bar.configure(text=f"✅ Счёт {inv_num} создан | Срок: {due_date or '—'}")
            except ValueError as ve:
                messagebox.showwarning("Внимание", str(ve))
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

        ctk.CTkButton(dlg, text="💾 Создать счёт", command=save, fg_color="#6610f2").pack(pady=15)

    def _mark_paid(self):
        sel = self.tree.selection()
        if not sel: return
        inv_id = self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Оплата", "Отметить счёт как оплаченный?"):
            db.pay_invoice(inv_id)
            self.load_invoices()

    def _cancel_payment(self):
        sel = self.tree.selection()
        if not sel: return
        inv_id = self.tree.item(sel[0])["values"][0]
        status_text = self.tree.item(sel[0])["values"][5] # Колонка "Статус"
        
        if "✅" not in status_text:
            return messagebox.showwarning("Внимание", "Можно отменить только оплаченные счета")
            
        if messagebox.askyesno("Отмена оплаты", "Вернуть счёт в состояние 'Ожидает оплаты'?"):
            db.cancel_invoice_payment(inv_id)
            self.load_invoices()
            self.status_bar.configure(text="↩️ Оплата счёта отменена")

    def _edit_invoice(self):
        sel = self.tree.selection()
        if not sel: return
        inv_id = self.tree.item(sel[0])["values"][0]
        self._open_invoice_form(invoice_id=inv_id)

    def _delete_invoice(self):
        sel = self.tree.selection()
        if not sel: return
        vals = self.tree.item(sel[0])["values"]
        if messagebox.askyesno("Удаление", f"Удалить счёт {vals[1]}?\nПоказания будут отвязаны."):
            db.delete_invoice(vals[0])
            self.load_invoices()

    # 🔹 СПРАВОЧНИК АДРЕСОВ
    def _manage_addresses(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("🏠 Справочник адресов")
        dlg.geometry("950x580")
        dlg.grab_set()
        dlg.transient(self)

        cols = ("id", "name", "full_address", "total_area", "rooms", "account")
        tree = ttk.Treeview(dlg, columns=cols, show="headings", selectmode="browse")
        col_cfg = {
            "id": ("ID", 40), "name": ("Название", 180), "full_address": ("Полный адрес", 350),
            "total_area": ("Площадь, м²", 90), "rooms": ("Комн.", 60), "account": ("Л/С", 100)
        }
        for c, (t, w) in col_cfg.items():
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="center" if c != "name" and c != "full_address" else "w")
        tree.pack(fill="both", expand=True, padx=20, pady=(20, 10))

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)

        def refresh_table():
            for i in tree.get_children(): tree.delete(i)
            for addr in db.get_all_addresses():
                tree.insert("", "end", values=(
                    addr["id"], addr["name"], addr.get("full_address") or "—",
                    f"{addr['total_area']:.1f}", addr.get("rooms_count", 1), addr.get("account_number") or "—"
                ))
            self.addresses = db.get_all_addresses()
            self.address_cb.configure(values=["📍 Все адреса"] + [a["name"] for a in self.addresses])
        refresh_table()

        def open_form(addr_id=None):
            form = ctk.CTkToplevel(dlg)
            form.title("➕ Новый адрес" if not addr_id else "✏️ Редактирование")
            form.geometry("520x520")
            form.grab_set()
            form.transient(dlg)

            data = next((a for a in self.addresses if a["id"] == addr_id), None) if addr_id else None
            v = {k: tk.StringVar() for k in ["name", "addr", "total", "actual", "rooms", "acc", "reg"]}
            v["multi"] = tk.BooleanVar()
            v["gas"] = tk.BooleanVar()

            if data:
                v["name"].set(data["name"])
                v["addr"].set(data.get("full_address") or "")
                v["multi"].set(bool(data.get("is_multi_apartment")))
                v["total"].set(str(data.get("total_area", 0.0)))
                v["actual"].set(str(data.get("actual_area", 0.0)))
                v["rooms"].set(str(data.get("rooms_count", 1)))
                v["gas"].set(bool(data.get("is_gasified")))
                v["acc"].set(data.get("account_number") or "")
                v["reg"].set(str(data.get("registered_count", 1)))

            fields = [
                ("Название:", v["name"]), ("Полный адрес:", v["addr"]),
                ("Общая площадь (м²):", v["total"]), ("Жилая площадь (м²):", v["actual"]),
                ("Кол-во комнат:", v["rooms"]), ("Лицевой счёт:", v["acc"]),
                ("Кол-во прописанных:", v["reg"])
            ]
            for i, (lbl, var) in enumerate(fields):
                ctk.CTkLabel(form, text=lbl).grid(row=i, column=0, padx=10, pady=5, sticky="w")
                ctk.CTkEntry(form, textvariable=var).grid(row=i, column=1, padx=10, pady=5, sticky="ew")

            ctk.CTkCheckBox(form, text="Многоквартирный дом", variable=v["multi"]).grid(row=len(fields), column=0, columnspan=2, padx=10, pady=5, sticky="w")
            ctk.CTkCheckBox(form, text="Газифицирован", variable=v["gas"]).grid(row=len(fields)+1, column=0, columnspan=2, padx=10, pady=5, sticky="w")
            form.grid_columnconfigure(1, weight=1)

            def save():
                try:
                    name = v["name"].get().strip()
                    if not name: raise ValueError("Поле 'Название' обязательно")
                    args = (
                        name, v["addr"].get().strip(), v["multi"].get(),
                        float(v["total"].get() or "0"), float(v["actual"].get() or "0"),
                        int(v["rooms"].get() or "1"), v["gas"].get(),
                        v["acc"].get().strip(), int(v["reg"].get() or "1")
                    )
                    if addr_id: db.update_address(addr_id, *args)
                    else: db.add_address(*args)
                    form.destroy()
                    refresh_table()
                except Exception as e:
                    messagebox.showerror("Ошибка ввода", str(e))

            ctk.CTkButton(form, text="💾 Сохранить", command=save).grid(row=len(fields)+3, column=0, columnspan=2, pady=15)

        ctk.CTkButton(btn_frame, text="➕ Добавить", command=lambda: open_form(), width=120).pack(side="left", padx=5)
        def edit_action():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите адрес")
            open_form(tree.item(sel[0])["values"][0])
        ctk.CTkButton(btn_frame, text="✏️ Изменить", command=edit_action, width=120).pack(side="left", padx=5)
        
        def delete_action():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите адрес")
            addr_id = tree.item(sel[0])["values"][0]
            if messagebox.askyesno("Подтверждение", "Удалить этот адрес?\nСвязанные платежи и счета будут удалены."):
                db.delete_address(addr_id)
                refresh_table()
        ctk.CTkButton(btn_frame, text="🗑️ Удалить", fg_color="#dc3545", hover_color="#c82333", command=delete_action, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="❌ Закрыть", command=dlg.destroy, width=100).pack(side="right", padx=5)

    # 🔹 СПРАВОЧНИК ТИПОВ ПЛАТЕЖЕЙ
    def _manage_types(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("📋 Справочник типов платежей")
        dlg.geometry("850x520")
        dlg.grab_set()
        dlg.transient(self)

        cols = ("id", "name", "desc", "recurring")
        tree = ttk.Treeview(dlg, columns=cols, show="headings", selectmode="browse")
        cfg = {"id": ("ID", 40), "name": ("Название", 220), "desc": ("Описание", 420), "recurring": ("Регулярный", 100)}
        for c, (t, w) in cfg.items():
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="center" if c != "name" and c != "desc" else "w")
        tree.pack(fill="both", expand=True, padx=20, pady=(20, 10))

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)

        def refresh_table():
            for i in tree.get_children(): tree.delete(i)
            for t in db.get_all_payment_types():
                tree.insert("", "end", values=(
                    t["id"], t["name"], t.get("description") or "—", 
                    "✅ Да" if t["is_recurring"] else "❌ Нет"
                ))
        refresh_table()

        def open_form(type_id=None):
            form = ctk.CTkToplevel(dlg)
            form.title("➕ Новый тип" if not type_id else "✏️ Редактирование")
            form.geometry("460x320")
            form.grab_set()
            form.transient(dlg)

            data = next((t for t in db.get_all_payment_types() if t["id"] == type_id), None) if type_id else None
            v_name = tk.StringVar()
            v_desc = tk.StringVar()
            v_rec = tk.BooleanVar(value=True)

            if data:
                v_name.set(data["name"])
                v_desc.set(data.get("description") or "")
                v_rec.set(bool(data["is_recurring"]))

            ctk.CTkLabel(form, text="Название: *").grid(row=0, column=0, padx=10, pady=8, sticky="w")
            ctk.CTkEntry(form, textvariable=v_name).grid(row=0, column=1, padx=10, pady=8, sticky="ew")
            ctk.CTkLabel(form, text="Описание:").grid(row=1, column=0, padx=10, pady=8, sticky="w")
            ctk.CTkEntry(form, textvariable=v_desc).grid(row=1, column=1, padx=10, pady=8, sticky="ew")
            ctk.CTkCheckBox(form, text="Регулярный платёж (ежемесячный)", variable=v_rec).grid(row=2, column=0, columnspan=2, padx=10, pady=8, sticky="w")
            form.grid_columnconfigure(1, weight=1)

            def save():
                name = v_name.get().strip()
                if not name:
                    messagebox.showerror("Ошибка", "Поле 'Название' обязательно")
                    return
                try:
                    desc = v_desc.get().strip()
                    is_rec = v_rec.get()
                    if type_id: db.update_payment_type(type_id, name, desc, is_rec)
                    else: db.add_payment_type(name, desc, is_rec)
                    form.destroy()
                    refresh_table()
                except Exception as e:
                    messagebox.showerror("Ошибка сохранения", str(e))
            ctk.CTkButton(form, text="💾 Сохранить", command=save).grid(row=3, column=0, columnspan=2, pady=15)

        ctk.CTkButton(btn_frame, text="➕ Добавить", command=lambda: open_form(), width=120).pack(side="left", padx=5)
        def edit_action():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите тип платежа")
            open_form(tree.item(sel[0])["values"][0])
        ctk.CTkButton(btn_frame, text="✏️ Изменить", command=edit_action, width=120).pack(side="left", padx=5)
        def delete_action():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите тип платежа")
            t_id = tree.item(sel[0])["values"][0]
            if messagebox.askyesno("Подтверждение", "Удалить этот тип?\n⚠️ Все связанные платежи будут удалены каскадно."):
                db.delete_payment_type(t_id)
                refresh_table()
        ctk.CTkButton(btn_frame, text="🗑️ Удалить", fg_color="#dc3545", hover_color="#c82333", command=delete_action, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="❌ Закрыть", command=dlg.destroy, width=100).pack(side="right", padx=5)

    # 🔹 СПРАВОЧНИК ПРИБОРОВ УЧЁТА
    def _manage_meters(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("📟 Справочник приборов учёта")
        dlg.geometry("950x500")
        dlg.grab_set()
        dlg.transient(self)

        cols = ("id", "address", "type", "serial", "riser", "install_date")
        tree = ttk.Treeview(dlg, columns=cols, show="headings", selectmode="browse")
        cfg = {
            "id": ("ID", 40), "address": ("Адрес", 200), "type": ("Тип", 140),
            "serial": ("Серийный №", 120), "riser": ("Стояк", 100), "install_date": ("Дата установки", 110)
        }
        for c, (t, w) in cfg.items():
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="center" if c in ("id", "type") else "w")
        tree.pack(fill="both", expand=True, padx=20, pady=(20, 10))

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)

        TYPE_DISPLAY = {
            "electricity": "⚡ Электричество", 
            "cold_water": "💧 Холодная вода", 
            "hot_water": "🔥 Горячая вода",
            "heat": "🌡️ Отопление",
            "gas": "🔥 Газ"
        }

        def refresh_table():
            for i in tree.get_children(): tree.delete(i)
            for m in db.get_all_meters():
                tree.insert("", "end", values=(
                    m["id"], m["address_name"], TYPE_DISPLAY.get(m["type"], m["type"]),
                    m["serial_number"], m.get("riser_number") or "—", m.get("installation_date") or "—"
                ))
        refresh_table()

        def open_form(meter_id=None):
            form = ctk.CTkToplevel(dlg)
            form.title("➕ Новый ПУ" if not meter_id else "✏️ Редактирование ПУ")
            form.geometry("500x300")
            form.grab_set()
            form.transient(dlg)

            data = next((m for m in db.get_all_meters() if m["id"] == meter_id), None) if meter_id else None
            addresses = db.get_all_addresses()

            v_addr = tk.StringVar()
            v_type = tk.StringVar()
            v_serial = tk.StringVar()
            v_riser = tk.StringVar()

            if data:
                v_addr.set(data["address_name"])
                v_type.set(TYPE_DISPLAY.get(data["type"], data["type"]))
                v_serial.set(data["serial_number"])
                v_riser.set(str(data.get("riser_number") or ""))
            else:
                v_type.set(TYPE_DISPLAY["electricity"])

            row = 0
            ctk.CTkLabel(form, text="Адрес: *").grid(row=row, column=0, padx=10, pady=8, sticky="w")
            ctk.CTkComboBox(form, values=[a["name"] for a in addresses], variable=v_addr).grid(row=row, column=1, padx=10, pady=8, sticky="ew")

            row += 1
            ctk.CTkLabel(form, text="Тип ПУ: *").grid(row=row, column=0, padx=10, pady=8, sticky="w")
            type_cb = ctk.CTkComboBox(form, values=list(TYPE_DISPLAY.values()), variable=v_type)
            type_cb.grid(row=row, column=1, padx=10, pady=8, sticky="ew")

            row += 1
            ctk.CTkLabel(form, text="Серийный номер: *").grid(row=row, column=0, padx=10, pady=8, sticky="w")
            ctk.CTkEntry(form, textvariable=v_serial).grid(row=row, column=1, padx=10, pady=8, sticky="ew")

            row += 1
            riser_row = row
            lbl_riser = ctk.CTkLabel(form, text="Стояк:")
            entry_riser = ctk.CTkEntry(form, textvariable=v_riser)

            def toggle_riser(*_):
                current = v_type.get().strip()
                is_water = current in (TYPE_DISPLAY["cold_water"], TYPE_DISPLAY["hot_water"])
                if is_water:
                    lbl_riser.grid(row=riser_row, column=0, padx=10, pady=8, sticky="w")
                    entry_riser.grid(row=riser_row, column=1, padx=10, pady=8, sticky="ew")
                else:
                    lbl_riser.grid_remove()
                    entry_riser.grid_remove()

            v_type.trace_add("write", toggle_riser)
            type_cb.bind("<<ComboboxSelected>>", toggle_riser)
            toggle_riser()

            row += 1
            ctk.CTkLabel(form, text="Дата установки:").grid(row=row, column=0, padx=10, pady=8, sticky="w")
            date_field = CTkDateField(form, placeholder="ГГГГ-ММ-ДД")
            date_field.grid(row=row, column=1, padx=10, pady=8, sticky="ew")
            if data and data.get("installation_date"):
                date_field.set_date(data["installation_date"])

            form.grid_columnconfigure(1, weight=1)

            def save():
                addr_name = v_addr.get().strip()
                type_ru = v_type.get().strip()
                serial = v_serial.get().strip()
                if not addr_name or not type_ru or not serial:
                    return messagebox.showerror("Ошибка", "Поля Адрес, Тип и Серийный номер обязательны")

                addr_id = next((a["id"] for a in addresses if a["name"] == addr_name), None)
                if not addr_id: return messagebox.showerror("Ошибка", "Адрес не найден")
                type_key = next((k for k, v in TYPE_DISPLAY.items() if v == type_ru), type_ru)

                riser_val = v_riser.get().strip()
                riser = riser_val if riser_val else None  
                install_date = date_field.get_date() or None

                try:
                    if meter_id: db.update_meter(meter_id, addr_id, type_key, serial, riser, install_date)
                    else: db.add_meter(addr_id, type_key, serial, riser, install_date)
                    form.destroy()
                    refresh_table()
                except Exception as e:
                    messagebox.showerror("Ошибка", str(e))

            row += 1
            ctk.CTkButton(form, text="💾 Сохранить", command=save).grid(row=row, column=0, columnspan=2, pady=15)

        ctk.CTkButton(btn_frame, text="➕ Добавить", command=lambda: open_form(), width=120).pack(side="left", padx=5)
        def edit_action():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите прибор")
            open_form(tree.item(sel[0])["values"][0])
        ctk.CTkButton(btn_frame, text="✏️ Изменить", command=edit_action, width=120).pack(side="left", padx=5)
        def delete_action():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите прибор")
            m_id = tree.item(sel[0])["values"][0]
            if messagebox.askyesno("Подтверждение", "Удалить этот прибор?\n⚠️ Связанные показания будут удалены каскадно."):
                db.delete_meter(m_id)
                refresh_table()
        ctk.CTkButton(btn_frame, text="🗑️ Удалить", fg_color="#dc3545", hover_color="#c82333", command=delete_action, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="❌ Закрыть", command=dlg.destroy, width=100).pack(side="right", padx=5)

    # 🔹 СПРАВКА И О ПРОГРАММЕ
    def _show_about(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("О программе")
        dlg.geometry("400x280")
        dlg.grab_set()
        dlg.transient(self)
        dlg.resizable(False, False)

        ctk.CTkLabel(dlg, text="🏢 Utility Tracker", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 5))
        ctk.CTkLabel(dlg, text="Версия ПО: 1.0.0", font=ctk.CTkFont(size=13, weight="bold")).pack()
        ctk.CTkLabel(dlg, text="Автоматизированный учёт коммунальных платежей,\nпоказаний приборов учёта и формирования счетов.", 
                     font=ctk.CTkFont(size=11), justify="center").pack(pady=10)
        ctk.CTkLabel(dlg, text="© 2026 Все права защищены.", font=ctk.CTkFont(size=10), text_color="gray").pack(pady=5)
        ctk.CTkButton(dlg, text="Закрыть", command=dlg.destroy, width=120).pack(pady=15)

    def _show_help(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Помощь по использованию")
        dlg.geometry("480x380")
        dlg.grab_set()
        dlg.transient(self)
        
        ctk.CTkLabel(dlg, text="📖 Краткая инструкция", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
        help_text = (
            "1️⃣  Справочники → добавьте адреса, типы платежей и приборы учёта.\n"
            "2️⃣  Передать показания → выберите адрес, дату и введите текущие значения.\n"
            "3️⃣  Создать счёт → система автоматически подтянет непривязанные показания.\n"
            "4️⃣  Оплатить → выделите счёт в таблице и нажмите ✅ Оплатить.\n"
            "5️⃣  Фильтрация → используйте выпадающие списки в шапке для отбора по месяцу/адресу.\n"
            "\n💡 Совет: поле «Стояк» доступно только для счётчиков ХВС/ГВС."
        )
        text_box = ctk.CTkTextbox(dlg, height=200, wrap="word")
        text_box.pack(fill="both", expand=True, padx=20, pady=10)
        text_box.insert("1.0", help_text)
        text_box.configure(state="disabled")
        ctk.CTkButton(dlg, text="Закрыть", command=dlg.destroy, width=120).pack(pady=10)

    # 🔹 ЭКСПОРТ/ИМПОРТ СПРАВОЧНИКОВ
    def _export_data(self):
        filepath = filedialog.asksaveasfilename(
            title="Экспорт справочников",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")],
            defaultextension=".json",
            initialfile="export_references.json"
        )
        if not filepath: return
        try:
            db.export_references(filepath)
            messagebox.showinfo("Экспорт", "✅ Справочники успешно сохранены.")
            self.status_bar.configure(text="📤 Экспорт завершён")
        except Exception as e:
            messagebox.showerror("Ошибка экспорта", str(e))

    def _import_data(self):
        if not messagebox.askyesno("Импорт данных", "⚠️ Это действие ЗАМЕНИТ текущие справочники данными из файла.\nПродолжить?"):
            return
        filepath = filedialog.askopenfilename(
            title="Импорт справочников",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")]
        )
        if not filepath: return
        try:
            db.import_references(filepath)
            self.addresses = db.get_all_addresses()
            self.address_cb.configure(values=["📍 Все адреса"] + [a["name"] for a in self.addresses])
            self.load_invoices()
            messagebox.showinfo("Импорт", "✅ Справочники успешно обновлены.")
            self.status_bar.configure(text="📥 Импорт завершён успешно")
        except Exception as e:
            messagebox.showerror("Ошибка импорта", str(e))

    def _open_settings(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("⚙️ Настройки программы")
        dlg.geometry("550x480")
        dlg.grab_set()
        dlg.transient(self)
        dlg.resizable(False, False)

        # 🔹 Контейнер вкладок
        tabview = ctk.CTkTabview(dlg, width=500, height=380)
        tabview.pack(fill="both", expand=True, padx=15, pady=15)

        # 🔹 Создаём 3 пустые вкладки
        tab_general = tabview.add("🔧 Общие")
        tab_meters = tabview.add("📟 Приборы учёта")
        tab_reports = tabview.add("📊 Отчёты и Расчёты")

        # 🔹 Заглушки контента (временно)
        ctk.CTkLabel(tab_general, text="Здесь будут общие настройки приложения\n(тема, валюта, единицы измерения и т.д.)", 
                     font=ctk.CTkFont(size=13), justify="center").pack(pady=80, expand=True)
        ctk.CTkLabel(tab_meters, text="Здесь будут настройки счётчиков\n(тарифные зоны, интервалы поверки, типы ПУ)", 
                     font=ctk.CTkFont(size=13), justify="center").pack(pady=80, expand=True)
        ctk.CTkLabel(tab_reports, text="Здесь будут настройки отчётов\n(форматы экспорта, шаблоны квитанций, графики)", 
                     font=ctk.CTkFont(size=13), justify="center").pack(pady=80, expand=True)

if __name__ == "__main__":
    PaymentTracker().mainloop()