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
    "hot_water": "🔥 Горячая вода"
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
        self.geometry("1250x750")
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

        # 🔹 Шапка
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=20, pady=10)

        today = date.today()
        years = [str(y) for y in range(today.year - 10, today.year + 11)]
        self.month_var.set(self.MONTH_NAMES[today.month-1])
        self.year_var.set(str(today.year))

        ctk.CTkLabel(header, text="📊 Счета за: ", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=10, pady=10)
        
        self.month_cb = ctk.CTkComboBox(header, values=self.MONTH_NAMES, variable=self.month_var, width=120)
        self.month_cb.pack(side="left", padx=2, pady=10)
        
        self.year_cb = ctk.CTkComboBox(header, values=years, variable=self.year_var, width=80)
        self.year_cb.pack(side="left", padx=5, pady=10)

        # Прямая привязка к загрузке таблицы (без дублирующих меток)
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

        ctk.CTkLabel(dlg, text="📍 Адрес:").pack(fill="x", padx=20, pady=5)
        addr_var = tk.StringVar(value=addrs[0]["name"])
        ctk.CTkComboBox(dlg, values=[a["name"] for a in addrs], variable=addr_var).pack(fill="x", padx=20)

        ctk.CTkLabel(dlg, text="📅 Дата передачи:").pack(fill="x", padx=20, pady=5)
        date_field = CTkDateField(dlg, placeholder="ГГГГ-ММ-ДД")
        date_field.pack(fill="x", padx=20)
        date_field.set_date(date.today().isoformat())

        ctk.CTkLabel(dlg, text="📟 Показания (пустые поля):", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=20, pady=(15,5))
        
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
                if not d:
                    raise ValueError("Укажите дату")
                
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

    # 🔹 ФОРМА СОЗДАНИЯ СЧЁТА
    def _open_invoice_form(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("📄 Создание счёта")
        dlg.geometry("700x650")
        dlg.grab_set()

        addrs = db.get_all_addresses()
        if not addrs: return

        ctk.CTkLabel(dlg, text="📍 Адрес: ").pack(fill="x", padx=20, pady=5)
        addr_var = tk.StringVar(value=addrs[0]["name"])
        ctk.CTkComboBox(dlg, values=[a["name"] for a in addrs], variable=addr_var).pack(fill="x", padx=20)

        ctk.CTkLabel(dlg, text="📅 Дата счёта: ").pack(fill="x", padx=20, pady=5)
        date_field = CTkDateField(dlg, placeholder="ГГГГ-ММ-ДД")
        date_field.pack(fill="x", padx=20)
        date_field.set_date(date.today().isoformat())

        ctk.CTkLabel(dlg, text="№ Счёта: ", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=20, pady=5)
        inv_var = tk.StringVar(value=db.get_next_invoice_number())
        ctk.CTkEntry(dlg, textvariable=inv_var, width=150, state="readonly").pack(anchor="w", padx=20)

        ctk.CTkLabel(dlg, text="💰 Сумма к оплате (₽): ", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=20, pady=(10,5))
        amt_var = tk.StringVar(value="0.00")
        ctk.CTkEntry(dlg, textvariable=amt_var, font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(dlg, text="📟 Привязанные показания: ", font=ctk.CTkFont(size=12)).pack(fill="x", padx=20, pady=5)
        tree_frame = ctk.CTkFrame(dlg)
        tree_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        # ✅ ИСПРАВЛЕНИЕ: Явные ID колонок
        cols = ("type", "sn", "prev", "cur", "cons")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=6)
        
        col_cfg = [
            ("type", "Тип", 120), ("sn", "SN", 120), ("prev", "Предыд.", 80), 
            ("cur", "Тек.", 80), ("cons", "Расход", 80)
        ]
        for col_id, col_name, w in col_cfg:
            tree.heading(col_id, text=col_name)
            tree.column(col_id, width=w, anchor="center")
            
        tree.pack(fill="both", expand=True)

        def load_readings():
            for i in tree.get_children(): tree.delete(i)
            sel = next((a for a in addrs if a["name"] == addr_var.get()), None)
            if not sel: return
            month_start = f"{date.today().year}-{date.today().month:02d}-01"
            for r in db.get_unlinked_readings(sel["id"], since_date=month_start):
                tree.insert("", "end", values=(
                    METER_TYPE_MAP.get(r["type"], r["type"]), r["serial_number"], 
                    r["previous_value"], r["current_value"], r["consumption"]
                ))

        addr_var.trace_add("write", lambda *_: load_readings())
        load_readings()

        def save():
            try:
                d = date_field.get_date()
                if not d: raise ValueError("Укажите дату")
                
                sel = next(a for a in addrs if a["name"] == addr_var.get())
                amt = float(amt_var.get().replace(",", "."))
                inv_num = inv_var.get()
                month_start = f"{date.today().year}-{date.today().month:02d}-01"
                reading_ids = [r["id"] for r in db.get_unlinked_readings(sel["id"], since_date=month_start)]
                
                db.create_invoice(sel["id"], inv_num, d, amt, reading_ids=reading_ids)
                dlg.destroy()
                self.load_invoices()
                self.status_bar.configure(text=f"✅ Счёт {inv_num} создан")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

        ctk.CTkButton(dlg, text="💾 Создать счёт", command=save, fg_color="#6610f2").pack(pady=10)

    def _mark_paid(self):
        sel = self.tree.selection()
        if not sel: return
        inv_id = self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Оплата", "Отметить счёт как оплаченный?"):
            db.pay_invoice(inv_id)
            self.load_invoices()

    def _delete_invoice(self):
        sel = self.tree.selection()
        if not sel: return
        vals = self.tree.item(sel[0])["values"]
        if messagebox.askyesno("Удаление", f"Удалить счёт {vals[1]}?\nПоказания будут отвязаны."):
            db.delete_invoice(vals[0])
            self.load_invoices()

    # 🔹 Заглушки для меню (реализуйте аналогично прошлой версии или оставьте как есть)
    def _manage_addresses(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("🏠 Справочник адресов")
        dlg.geometry("950x580")
        dlg.grab_set()
        dlg.transient(self)

        # 🔹 Таблица адресов
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

        # 🔹 Панель кнопок
        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)

        def refresh_table():
            for i in tree.get_children(): tree.delete(i)
            for addr in db.get_all_addresses():
                tree.insert("", "end", values=(
                    addr["id"], addr["name"], addr.get("full_address") or "—",
                    f"{addr['total_area']:.1f}", addr.get("rooms_count", 1), addr.get("account_number") or "—"
                ))
            # Синхронизация с главным окном
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
                    if addr_id:
                        db.update_address(addr_id, *args)
                    else:
                        db.add_address(*args)
                    form.destroy()
                    refresh_table()
                except Exception as e:
                    messagebox.showerror("Ошибка ввода", str(e))

            ctk.CTkButton(form, text="💾 Сохранить", command=save).grid(row=len(fields)+3, column=0, columnspan=2, pady=15)

        def add_action(): open_form()
        def edit_action():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите адрес")
            open_form(tree.item(sel[0])["values"][0])
            
        def delete_action():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите адрес")
            addr_id = tree.item(sel[0])["values"][0]
            if messagebox.askyesno("Подтверждение", "Удалить этот адрес?\nСвязанные платежи и счета будут удалены."):
                db.delete_address(addr_id)
                refresh_table()

        ctk.CTkButton(btn_frame, text="➕ Добавить", command=add_action, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="✏️ Изменить", command=edit_action, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="🗑️ Удалить", fg_color="#dc3545", hover_color="#c82333", command=delete_action, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="❌ Закрыть", command=dlg.destroy, width=100).pack(side="right", padx=5)
        
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

            types = db.get_all_payment_types()
            data = next((t for t in types if t["id"] == type_id), None) if type_id else None

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
                    if type_id:
                        db.update_payment_type(type_id, name, desc, is_rec)
                    else:
                        db.add_payment_type(name, desc, is_rec)
                    form.destroy()
                    refresh_table()
                except Exception as e:
                    messagebox.showerror("Ошибка сохранения", str(e))

            ctk.CTkButton(form, text="💾 Сохранить", command=save).grid(row=3, column=0, columnspan=2, pady=15)

        def add_action(): open_form()
        def edit_action():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите тип платежа")
            open_form(tree.item(sel[0])["values"][0])
            
        def delete_action():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите тип платежа")
            t_id = tree.item(sel[0])["values"][0]
            if messagebox.askyesno("Подтверждение", "Удалить этот тип?\n⚠️ Все связанные платежи будут удалены каскадно."):
                db.delete_payment_type(t_id)
                refresh_table()

        ctk.CTkButton(btn_frame, text="➕ Добавить", command=add_action, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="✏️ Изменить", command=edit_action, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="🗑️ Удалить", fg_color="#dc3545", hover_color="#c82333", command=delete_action, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="❌ Закрыть", command=dlg.destroy, width=100).pack(side="right", padx=5)

    def _manage_meters(self): messagebox.showinfo("Справочник", "Менеджер приборов")
    def _export_data(self): messagebox.showinfo("Экспорт", "Экспорт в ZIP")
    def _import_data(self): messagebox.showinfo("Импорт", "Импорт из ZIP")

if __name__ == "__main__":
    PaymentTracker().mainloop()