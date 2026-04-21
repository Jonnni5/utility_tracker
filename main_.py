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
STATUS_RU = {"pending": "⏳ Ожидает", "overdue": "❌ Просрочен", "paid": "✅ Оплачен"}
STATUS_EN = {v: k for k, v in STATUS_RU.items()}

class CTkDateField(ctk.CTkFrame):
    """Компактное поле даты"""
    def __init__(self, master, date_pattern="yyyy-MM-dd", placeholder="ГГГГ-ММ-ДД", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.entry = ctk.CTkEntry(self, placeholder_text=placeholder)
        self.entry.pack(side="left", fill="x", expand=True)
        self.btn = ctk.CTkButton(self, text="📅", width=40, command=self._open_calendar)
        self.btn.pack(side="right", padx=(5, 0))
        self._cal_window = None

    def _open_calendar(self):
        if self._cal_window and self._cal_window.winfo_exists():
            self._cal_window.lift(); return
        self._cal_window = ctk.CTkToplevel(self)
        self._cal_window.title("Выберите дату")
        self._cal_window.geometry("260x290")
        self._cal_window.resizable(False, False)
        self._cal_window.transient(self.winfo_toplevel())
        self._cal_window.grab_set()
        self._cal_window.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height() + 5}")
        
        if Calendar:
            try: cal = Calendar(self._cal_window, selectmode='day', date_pattern=self.date_pattern, locale='ru_RU')
            except: cal = Calendar(self._cal_window, selectmode='day')
            cal.pack(pady=10, padx=10)
            ctk.CTkButton(self._cal_window, text="✅ Выбрать", command=lambda: self._set_date(cal.get_date())).pack(pady=5)
        else: ctk.CTkLabel(self._cal_window, text="⚠️ pip install tkcalendar").pack(pady=20)

    def _set_date(self, date_str):
        self.entry.delete(0, "end"); self.entry.insert(0, date_str)
        if self._cal_window and self._cal_window.winfo_exists(): self._cal_window.destroy()

    def get_date(self): return self.entry.get().strip()
    def set_date(self, date_str):
        if date_str: self.entry.delete(0, "end"); self.entry.insert(0, date_str)

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
        
        # ✅ ИСПРАВЛЕНО: Убран пробел в переменной
        self.addresses = db.get_all_addresses()
        self._sort_state = {}
        self.theme_var = tk.StringVar(value=self.config_mgr.get("theme", "System"))

        self._setup_ui()
        self.load_payments()

    def _setup_ui(self):
        menubar = tk.Menu(self); self.config(menu=menubar)
        dirs_menu = tk.Menu(menubar, tearoff=0)
        dirs_menu.add_command(label="🏠 Адреса", command=self._manage_addresses)
        dirs_menu.add_command(label="📋 Типы платежей", command=self._manage_types)
        dirs_menu.add_command(label="🔧 Приборы учета", command=self._manage_meters)
        dirs_menu.add_command(label="⚙️ Настройки услуг", command=self._manage_config)
        menubar.add_cascade(label="📂 Справочники", menu=dirs_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        for lbl, val in [("🌞 Светлая", "Light"), ("🌙 Тёмная", "Dark"), ("💻 Системная", "System")]:
            view_menu.add_radiobutton(label=lbl, variable=self.theme_var, value=val, command=self._change_theme)
        menubar.add_cascade(label="👁️ Вид", menu=view_menu)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="📤 Экспорт (CSV)", command=self._export_dictionaries)
        file_menu.add_command(label="📥 Импорт (CSV)", command=self._import_dictionaries)
        file_menu.add_separator()
        file_menu.add_command(label="🔄 Обновить", command=self.load_payments)
        file_menu.add_command(label="❌ Выход", command=self.destroy)
        menubar.add_cascade(label="📁 Файл", menu=file_menu)

        header = ctk.CTkFrame(self); header.pack(fill="x", padx=20, pady=10)
        today = date.today()
        month_options = [f"{m} {y}" for y in range(today.year-1, today.year+2) for m in self.MONTH_NAMES]
        self.month_var.set(f"{self.MONTH_NAMES[today.month-1]} {today.year}")

        ctk.CTkLabel(header, text="📊 Платежи за: ", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=10)
        self.month_cb = ctk.CTkComboBox(header, values=month_options, variable=self.month_var, width=160)
        self.month_cb.pack(side="left", padx=5)
        self.month_cb.configure(command=lambda _: self.load_payments())
        ctk.CTkLabel(header, text="месяц", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=(0, 10))

        addr_names = ["📍 Все адреса"] + [a["name"] for a in self.addresses]
        self.address_var = tk.StringVar(value=addr_names[0])
        self.address_cb = ctk.CTkComboBox(header, values=addr_names, variable=self.address_var, width=200)
        self.address_cb.pack(side="left", padx=10)
        self.address_cb.configure(command=lambda _: self.load_payments())

        btn_frame = ctk.CTkFrame(header, fg_color="transparent"); btn_frame.pack(side="right")
        self.btn_bill = ctk.CTkButton(btn_frame, text="📄 Счёт", fg_color="#6610f2", width=90, command=self._open_bill_form); self.btn_bill.pack(side="left", padx=3)
        self.btn_add = ctk.CTkButton(btn_frame, text="➕ Добавить", fg_color="#28a745", width=100, command=self._open_add_dialog); self.btn_add.pack(side="left", padx=3)
        self.btn_edit = ctk.CTkButton(btn_frame, text="✏️ Изменить", fg_color="#fd7e14", width=100, command=self._open_edit_dialog); self.btn_edit.pack(side="left", padx=3)
        self.btn_paid = ctk.CTkButton(btn_frame, text="✅ Оплатить", width=90, command=self._mark_as_paid); self.btn_paid.pack(side="left", padx=3)
        self.btn_delete = ctk.CTkButton(btn_frame, text="🗑️ Удалить", fg_color="#dc3545", width=90, command=self._delete_payment); self.btn_delete.pack(side="left", padx=3)
        self.btn_refresh = ctk.CTkButton(btn_frame, text="🔄", width=40, command=self.load_payments); self.btn_refresh.pack(side="left", padx=3)

        table_frame = ctk.CTkFrame(self); table_frame.pack(fill="both", expand=True, padx=20, pady=10)
        cols = ("id", "address", "type", "amount", "due", "paid", "status", "notes")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        cfg = {"id": ("ID", 50), "address": ("Адрес", 140), "type": ("Тип", 130), "amount": ("Сумма, ₽", 100), "due": ("Срок", 100), "paid": ("Дата оплаты", 110), "status": ("Статус", 100), "notes": ("Примечание", 250)}
        for c, (t, w) in cfg.items():
            self._sort_state[c] = False; self.tree.heading(c, text=t, command=lambda col=c: self._sort_treeview(col)); self.tree.column(c, width=w, anchor="center" if c != "address" else "w")
        
        self.tree.tag_configure("overdue", foreground="#e63946", background="#fde8e8")
        self.tree.tag_configure("paid", foreground="#2d6a4f", background="#e8f5e9")
        self.tree.tag_configure("pending", foreground="#212529")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set); self.tree.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")
        self.status_bar = ctk.CTkLabel(self, text="Готово к работе", anchor="w", font=ctk.CTkFont(size=12)); self.status_bar.pack(fill="x", padx=20, pady=5)

    def _change_theme(self):
        theme = self.theme_var.get(); ctk.set_appearance_mode(theme); self.config_mgr.set("theme", theme)

    def _sort_treeview(self, col):
        self._sort_state[col] = not self._sort_state[col]; reverse = self._sort_state[col]
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        key_type = int if col == "id" else float if col == "amount" else str
        items.sort(key=lambda x: key_type(x[0]) if x[0] not in ("", "—") else 0, reverse=reverse)
        for i, (_, k) in enumerate(items): self.tree.move(k, '', i)

    def load_payments(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        parts = self.month_var.get().split()
        month, year = (self.MONTH_TO_NUM.get(parts[0], date.today().month), int(parts[1])) if len(parts)==2 else (date.today().month, date.today().year)
        selected = self.address_var.get()
        addr_id = next((a["id"] for a in self.addresses if a["name"] == selected), None) if selected != "📍 Все адреса" else None

        for p in db.get_payments_by_month(year, month, addr_id):
            raw_status = p.get("status", "pending").strip().lower()
            tag = raw_status if raw_status in ("overdue", "paid", "pending") else "pending"
            self.tree.insert("", "end", values=(p["id"], p["address_name"], p["type_name"], f"{p['amount']:.2f}", p["due_date"], p["paid_date"] or "—", STATUS_RU.get(raw_status, raw_status), p["notes"] or ""), tags=(tag,))
        m_name = next((k for k, v in self.MONTH_TO_NUM.items() if v == month), str(month))
        self.status_bar.configure(text=f"Загружено: {len(self.tree.get_children())} записей | {m_name} {year} | {selected}")

    # --- Управление адресами (Исправлено) ---
    def _manage_addresses(self):
        dlg = ctk.CTkToplevel(self); dlg.title("Управление адресами"); dlg.geometry("1000x550"); dlg.grab_set()
        frame = ctk.CTkFrame(dlg); frame.pack(fill="both", expand=True, padx=10, pady=10)
        cols = ("id", "name", "account", "full", "mkd", "total_a", "actual_a", "rooms", "gas", "reg")
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        col_cfg = {"id": ("ID", 40), "name": ("Ярлык", 120), "account": ("Лиц. счёт", 90), "full": ("Адрес", 220), "mkd": ("МКД", 50), "total_a": ("Общ. м²", 70), "actual_a": ("Факт. м²", 70), "rooms": ("Комн.", 50), "gas": ("Газ", 50), "reg": ("Проп.", 50)}
        for c, (t, w) in col_cfg.items(): tree.heading(c, text=t); tree.column(c, width=w, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview); tree.configure(yscroll=scrollbar.set); scrollbar.pack(side="right", fill="y")

        def refresh():
            for i in tree.get_children(): tree.delete(i)
            for a in db.get_all_addresses():
                tree.insert("", "end", values=(a["id"], a["name"], a.get("account_number", ""), a.get("full_address", ""), "✅" if a.get("is_multi_apartment") else "❌", a.get("total_area", 0), a.get("actual_area", 0), a.get("rooms_count", 1), "✅" if a.get("is_gasified") else "❌", a.get("registered_count", 1)))
        refresh()

        def open_edit(existing=None):
            win = ctk.CTkToplevel(dlg); win.title("Редактирование" if existing else "Новый адрес"); win.geometry("480x650"); win.grab_set()
            n_var = tk.StringVar(value=existing["name"] if existing else "")
            f_var = tk.StringVar(value=existing.get("full_address", "") if existing else "")
            mkd_var = tk.BooleanVar(value=bool(existing.get("is_multi_apartment")) if existing else False)
            acc_var = tk.StringVar(value=existing.get("account_number", "") if existing else "")
            total_a_var = tk.StringVar(value=str(existing.get("total_area", 0)) if existing else "")
            actual_a_var = tk.StringVar(value=str(existing.get("actual_area", 0)) if existing else "")
            rooms_var = tk.StringVar(value=str(existing.get("rooms_count", 1)) if existing else "")
            reg_var = tk.StringVar(value=str(existing.get("registered_count", 1)) if existing else "")
            gas_var = tk.BooleanVar(value=bool(existing.get("is_gasified")) if existing else False)

            def pack_field(lbl, var, w=100):
                row = ctk.CTkFrame(win, fg_color="transparent"); row.pack(fill="x", padx=20, pady=4)
                ctk.CTkLabel(row, text=lbl, width=140, anchor="w").pack(side="left"); ctk.CTkEntry(row, textvariable=var, width=w).pack(side="left", padx=5)

            ctk.CTkLabel(win, text="📍 Название: ").pack(fill="x", padx=20, pady=5)
            ctk.CTkEntry(win, textvariable=n_var).pack(fill="x", padx=20)
            ctk.CTkLabel(win, text="🏠 Полный адрес: ").pack(fill="x", padx=20, pady=5)
            ctk.CTkEntry(win, textvariable=f_var).pack(fill="x", padx=20)
            ctk.CTkCheckBox(win, text="🏢 МКД", variable=mkd_var).pack(fill="x", padx=20)
            pack_field("💳 Лиц. счёт:", acc_var, 80)
            pack_field("Площадь общая:", total_a_var, 60)
            pack_field("Площадь факт.:", actual_a_var, 60)
            pack_field("Комнат:", rooms_var, 40)
            pack_field("Прописано:", reg_var, 40)
            ctk.CTkCheckBox(win, text="🔥 Газифицирован", variable=gas_var).pack(fill="x", padx=20)

            def save():
                name, full = n_var.get().strip(), f_var.get().strip()
                if not name: return messagebox.showwarning("Внимание", "Введите название")
                try:
                    t_a, act_a = float(total_a_var.get().replace(',','.') or 0), float(actual_a_var.get().replace(',','.') or 0)
                    r, rg = int(rooms_var.get() or 1), int(reg_var.get() or 1)
                except: return messagebox.showerror("Ошибка", "Проверьте числа")
                if existing: db.update_address(existing["id"], name, full, mkd_var.get(), t_a, act_a, r, gas_var.get(), acc_var.get(), rg)
                else: db.add_address(name, full, mkd_var.get(), t_a, act_a, r, gas_var.get(), acc_var.get(), rg)
                refresh(); self._sync_main_address_list(); win.destroy()
            ctk.CTkButton(win, text="💾 Сохранить", command=save, fg_color="#007bff").pack(pady=15)

        def add(): open_edit()
        def edit():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите строку")
            addr = next((a for a in db.get_all_addresses() if a["id"] == tree.item(sel[0])["values"][0]), None)
            if addr: open_edit(addr)
        def delete():
            sel = tree.selection()
            if not sel: return messagebox.showwarning("Внимание", "Выберите строку")
            vals = tree.item(sel[0])["values"]
            if messagebox.askyesno("Удаление", f"Удалить '{vals[1]}'?"):
                db.delete_address(vals[0]); refresh(); self._sync_main_address_list(); self.load_payments()

        btn_top = ctk.CTkFrame(dlg, fg_color="transparent"); btn_top.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(btn_top, text="➕ Добавить", command=add, width=120).pack(side="left", padx=5)
        ctk.CTkButton(btn_top, text="✏️ Изменить", command=edit, width=120, fg_color="#fd7e14").pack(side="left", padx=5)
        ctk.CTkButton(btn_top, text="🗑️ Удалить", command=delete, width=120, fg_color="#dc3545").pack(side="left", padx=5)
        ctk.CTkButton(btn_top, text="❌ Закрыть", command=dlg.destroy, width=120).pack(side="right", padx=5)

    def _sync_main_address_list(self):
        self.addresses = db.get_all_addresses()
        new_vals = ["📍 Все адреса"] + [a["name"] for a in self.addresses]
        self.address_cb.configure(values=new_vals)
        if self.address_var.get() not in new_vals: self.address_var.set(new_vals[0])

    def _manage_types(self):
        dlg = ctk.CTkToplevel(self); dlg.title("Типы платежей"); dlg.geometry("600x400"); dlg.grab_set()
        tree = ttk.Treeview(dlg, columns=("id", "name", "rec"), show="headings"); tree.heading("id", text="ID"); tree.heading("name", text="Название"); tree.heading("rec", text="Регул.")
        tree.pack(fill="both", expand=True)
        def refresh():
            for i in tree.get_children(): tree.delete(i)
            for t in db.get_all_payment_types(): tree.insert("", "end", values=(t["id"], t["name"], "✅" if t["is_recurring"] else "❌"))
        refresh()
        def add():
            win = ctk.CTkToplevel(dlg); win.geometry("300x250"); win.grab_set()
            n_var = tk.StringVar(); ctk.CTkEntry(win, textvariable=n_var).pack(pady=10)
            def save():
                if n_var.get().strip(): db.add_payment_type(n_var.get().strip()); refresh(); win.destroy()
            ctk.CTkButton(win, text="➕", command=save).pack()
        ctk.CTkButton(dlg, text="➕ Добавить", command=add).pack(pady=5)
        ctk.CTkButton(dlg, text="❌ Закрыть", command=dlg.destroy).pack()

    def _manage_meters(self):
        dlg = ctk.CTkToplevel(self); dlg.title("Приборы учета"); dlg.geometry("850x550"); dlg.grab_set()
        tree = ttk.Treeview(dlg, columns=("id", "addr", "type", "sn"), show="headings")
        for c, t in [("id","ID"), ("addr","Адрес"), ("type","Тип"), ("sn","Серийный №")]: tree.heading(c, text=t)
        tree.pack(fill="both", expand=True)
        def refresh():
            for i in tree.get_children(): tree.delete(i)
            for m in db.get_all_meters(): tree.insert("", "end", values=(m["id"], m["address_name"], METER_TYPE_MAP.get(m["type"], m["type"]), m["serial_number"]))
        refresh()
        def add():
            win = ctk.CTkToplevel(dlg); win.geometry("400x500"); win.grab_set()
            addrs = db.get_all_addresses()
            if not addrs: return messagebox.showwarning("Внимание", "Добавьте адрес")
            ctk.CTkLabel(win, text="Адрес:").pack()
            addr_var = tk.StringVar(value=addrs[0]["name"])
            ctk.CTkComboBox(win, values=[a["name"] for a in addrs], variable=addr_var).pack()
            ctk.CTkLabel(win, text="Тип:").pack()
            t_var = tk.StringVar(value="⚡ Электричество")
            ctk.CTkComboBox(win, values=list(METER_TYPE_MAP.values()), variable=t_var).pack()
            ctk.CTkLabel(win, text="Серийный номер:").pack()
            s_var = tk.StringVar(); ctk.CTkEntry(win, textvariable=s_var).pack()
            def save():
                aid = next(a["id"] for a in addrs if a["name"]==addr_var.get())
                if not s_var.get().strip(): return messagebox.showwarning("Внимание", "Введите номер")
                db.add_meter(aid, METER_TYPE_REVERSE.get(t_var.get()), s_var.get().strip())
                refresh(); win.destroy()
            ctk.CTkButton(win, text="💾", command=save).pack(pady=10)
        ctk.CTkButton(dlg, text="➕", command=add).pack()

    def _manage_config(self):
        dlg = ctk.CTkToplevel(self); dlg.title("Настройки"); dlg.geometry("400x500"); dlg.grab_set()
        residents_var = tk.IntVar(value=self.config_mgr.get("residents_count", 1))
        ctk.CTkLabel(dlg, text="👥 Проживающих:").pack(); ctk.CTkEntry(dlg, textvariable=residents_var).pack()
        risers_var = tk.IntVar(value=self.config_mgr.get("water_risers_count", 1))
        ctk.CTkLabel(dlg, text="🚿 Стояков:").pack(); ctk.CTkEntry(dlg, textvariable=risers_var).pack()
        elec_var = tk.StringVar(value="Двухтарифный" if self.config_mgr.get("electricity_mode","")=="day_night" else "Однотарифный")
        ctk.CTkLabel(dlg, text="⚡ Электричество:").pack(); ctk.CTkComboBox(dlg, values=["Однотарифный", "Двухтарифный"], variable=elec_var).pack()
        def save():
            self.config_mgr.set("residents_count", max(1, residents_var.get()))
            self.config_mgr.set("water_risers_count", max(1, risers_var.get()))
            self.config_mgr.set("electricity_mode", "day_night" if elec_var.get().startswith("Двух") else "single")
            messagebox.showinfo("Успех", "✅ Сохранено"); dlg.destroy()
        ctk.CTkButton(dlg, text="💾", command=save).pack(pady=15)

    # --- Экспорт/Импорт ---
    def _export_dictionaries(self):
        path = filedialog.asksaveasfilename(filetypes=[("CSV", "*.csv")])
        if not path: return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f); w.writerow(['type','name','full_address','account','is_mkd','area'])
                for a in db.get_all_addresses(): w.writerow(['address', a['name'], a.get('full_address',''), a.get('account_number',''), a.get('is_multi_apartment',0), a.get('total_area',0)])
                for t in db.get_all_payment_types(): w.writerow(['payment', t['name'], t.get('description',''), '', 0, ''])
            messagebox.showinfo("Успех", "Экспортировано")
        except Exception as e: messagebox.showerror("Ошибка", str(e))

    def _import_dictionaries(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not path: return
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                r = csv.DictReader(f)
                for row in r:
                    if row.get('type','').strip().lower() == 'address': db.add_address(row['name'], row.get('full_address',''), row.get('is_mkd','0')=='1')
                    elif row.get('type','').strip().lower() == 'payment': db.add_payment_type(row['name'], row.get('description',''))
            self._sync_main_address_list(); self.load_payments()
            messagebox.showinfo("Успех", "Импорт завершен")
        except Exception as e: messagebox.showerror("Ошибка", str(e))

    # --- Основные формы ---
    def _open_bill_form(self):
        dialog = ctk.CTkToplevel(self); dialog.title("📄 Ввод показаний / Счёт"); dialog.geometry("500x750"); dialog.grab_set()
        addrs = db.get_all_addresses()
        if not addrs: messagebox.showwarning("Внимание", "Добавьте адрес"); return
        addr_var = tk.StringVar(value=addrs[0]["name"])
        ctk.CTkLabel(dialog, text="📍 Адрес:").pack(fill="x", padx=20, pady=5)
        ctk.CTkComboBox(dialog, values=[a["name"] for a in addrs], variable=addr_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="📅 Дата:").pack(fill="x", padx=20, pady=5)
        date_field = CTkDateField(dialog); date_field.pack(fill="x", padx=20)
        date_field.set_date(date.today().isoformat())
        
        frame = ctk.CTkScrollableFrame(dialog, height=400); frame.pack(fill="both", expand=True, padx=20, pady=10)
        entries = {}
        
        def build():
            for w in frame.winfo_children(): w.destroy(); entries.clear()
            sel = next(a for a in addrs if a["name"]==addr_var.get())
            for m in [x for x in db.get_all_meters() if x["address_id"]==sel["id"]]:
                row = ctk.CTkFrame(frame, fg_color="transparent"); row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=f"{METER_TYPE_MAP.get(m['type'],'')} | {m['serial_number']}").pack(side="left")
                v = tk.StringVar(); ctk.CTkEntry(row, textvariable=v, width=80, placeholder_text="0.00").pack(side="left", padx=5)
                entries[m["id"]] = v

        addr_var.trace_add("write", lambda *_: build()); build()

        def save():
            try:
                due = date_field.get_date()
                if not due: raise ValueError("Выберите дату")
                sel = next(a for a in addrs if a["name"]==addr_var.get())
                count = 0
                for mid, var in entries.items():
                    val = var.get().strip().replace(",",".")
                    if val:
                        amount = float(val)
                        type_id = db.get_or_create_payment_type(f"Показания {mid}")
                        db.add_payment(sel["id"], type_id, amount, due)
                        count += 1
                dialog.destroy(); self.load_payments(); self.status_bar.configure(text=f"✅ Сохранено {count}")
            except Exception as e: messagebox.showerror("Ошибка", str(e))
        ctk.CTkButton(dialog, text="💾 Сохранить", command=save, fg_color="#6610f2").pack(pady=10)

    def _open_add_dialog(self):
        dialog = ctk.CTkToplevel(self); dialog.title("Новый платёж"); dialog.geometry("440x640"); dialog.grab_set()
        addrs, types = db.get_all_addresses(), db.get_all_payment_types()
        if not addrs or not types: messagebox.showerror("Ошибка", "Нет данных"); return
        a_var, t_var, amt_var, n_var = tk.StringVar(value=addrs[0]["name"]), tk.StringVar(value=types[0]["name"]), tk.StringVar(value="0.00"), tk.StringVar()
        ctk.CTkLabel(dialog, text="Адрес:").pack(); ctk.CTkComboBox(dialog, values=[a["name"] for a in addrs], variable=a_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="Тип:").pack(); ctk.CTkComboBox(dialog, values=[t["name"] for t in types], variable=t_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="Сумма:").pack(); ctk.CTkEntry(dialog, textvariable=amt_var).pack(fill="x", padx=20)
        df = CTkDateField(dialog); ctk.CTkLabel(dialog, text="Срок:").pack(); df.pack(fill="x", padx=20); df.set_date(date.today().isoformat())
        ctk.CTkLabel(dialog, text="Примечание:").pack(); ctk.CTkEntry(dialog, textvariable=n_var).pack(fill="x", padx=20)
        def save():
            try:
                aid = next(a["id"] for a in addrs if a["name"]==a_var.get()); tid = next(t["id"] for t in types if t["name"]==t_var.get())
                db.add_payment(aid, tid, float(amt_var.get().replace(",",".")), df.get_date(), n_var.get().strip())
                dialog.destroy(); self.load_payments()
            except Exception as e: messagebox.showerror("Ошибка", str(e))
        ctk.CTkButton(dialog, text="💾", command=save, fg_color="#007bff").pack(pady=15)

    def _open_edit_dialog(self):
        sel = self.tree.selection(); 
        if not sel: return
        vals = self.tree.item(sel[0])["values"]
        dialog = ctk.CTkToplevel(self); dialog.title(f"Редактирование {vals[0]}"); dialog.geometry("440x640"); dialog.grab_set()
        addrs, types = db.get_all_addresses(), db.get_all_payment_types()
        a_var, t_var, amt_var, n_var = tk.StringVar(value=vals[1]), tk.StringVar(value=vals[2]), tk.StringVar(value=vals[3]), tk.StringVar(value=vals[7] if vals[7]!="—" else "")
        ctk.CTkLabel(dialog, text="Адрес:").pack(); ctk.CTkComboBox(dialog, values=[a["name"] for a in addrs], variable=a_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="Тип:").pack(); ctk.CTkComboBox(dialog, values=[t["name"] for t in types], variable=t_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="Сумма:").pack(); ctk.CTkEntry(dialog, textvariable=amt_var).pack(fill="x", padx=20)
        df = CTkDateField(dialog); ctk.CTkLabel(dialog, text="Срок:").pack(); df.pack(fill="x", padx=20); df.set_date(vals[4])
        ctk.CTkLabel(dialog, text="Примечание:").pack(); ctk.CTkEntry(dialog, textvariable=n_var).pack(fill="x", padx=20)
        def save():
            try:
                aid = next(a["id"] for a in addrs if a["name"]==a_var.get()); tid = next(t["id"] for t in types if t["name"]==t_var.get())
                db.update_payment(vals[0], aid, tid, float(amt_var.get().replace(",",".")), df.get_date(), n_var.get().strip())
                dialog.destroy(); self.load_payments()
            except Exception as e: messagebox.showerror("Ошибка", str(e))
        ctk.CTkButton(dialog, text="💾", command=save, fg_color="#fd7e14").pack(pady=15)

    def _mark_as_paid(self):
        sel = self.tree.selection()
        if not sel: return
        pid = self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Оплата", "Отметить как оплаченный?"):
            db.mark_as_paid(pid); self.load_payments()

    def _delete_payment(self):
        sel = self.tree.selection()
        if not sel: return
        if messagebox.askyesno("Удалить", "Удалить запись?"):
            if db.delete_payment(self.tree.item(sel[0])["values"][0]): self.load_payments()

if __name__ == "__main__":
    PaymentTracker().mainloop()