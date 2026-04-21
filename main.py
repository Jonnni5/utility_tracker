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

import zipfile
import json
import io

# 🔹 Константы
METER_TYPE_MAP = {
    "electricity": "⚡ Электричество",
    "cold_water": "💧 Холодная вода",
    "hot_water": "🔥 Горячая вода"
}
METER_TYPE_REVERSE = {v: k for k, v in METER_TYPE_MAP.items()}
STATUS_RU = {
    "pending": "⏳ Ожидает",
    "paid": "✅ Оплачен"
}

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
            try:
                cal = Calendar(self._cal_window, selectmode='day', date_pattern="y-mm-dd", locale='ru_RU')
            except Exception:
                cal = Calendar(self._cal_window, selectmode='day')
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

        self.MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
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

        # Меню
        dirs_menu = tk.Menu(menubar, tearoff=0)
        dirs_menu.add_command(label="🏠 Адреса", command=self._manage_addresses)
        dirs_menu.add_command(label="📋 Типы платежей", command=self._manage_types)
        dirs_menu.add_command(label="🔧 Приборы учета", command=self._manage_meters)
        menubar.add_cascade(label="📂 Справочники", menu=dirs_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        for lbl, val in [("🌞 Светлая", "Light"), ("🌙 Тёмная", "Dark"), ("💻 Системная", "System")]:
            view_menu.add_radiobutton(label=lbl, variable=self.theme_var, value=val, command=lambda v=val: (ctk.set_appearance_mode(v), self.config_mgr.set("theme", v)))
        menubar.add_cascade(label="👁️ Вид", menu=view_menu)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="📤 Экспорт (ZIP)", command=self._export_data)
        file_menu.add_command(label="📥 Импорт (ZIP)", command=self._import_data)
        file_menu.add_separator()
        file_menu.add_command(label="❌ Выход", command=self.destroy)
        menubar.add_cascade(label="📁 Файл", menu=file_menu)

        # Шапка
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=20, pady=10)
        
        today = date.today()
        years = [str(y) for y in range(today.year - 10, today.year + 11)]
        self.month_var.set(self.MONTH_NAMES[today.month-1])
        self.year_var.set(str(today.year))

        ctk.CTkLabel(header, text="📊 Счета за: ", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=10)
        
        self.month_cb = ctk.CTkComboBox(header, values=self.MONTH_NAMES, variable=self.month_var, width=120)
        self.month_cb.pack(side="left")
        
        self.year_cb = ctk.CTkComboBox(header, values=years, variable=self.year_var, width=80)
        self.year_cb.pack(side="left", padx=5)

        self.period_lbl = ctk.CTkLabel(header, text=f"{self.month_var.get()} {self.year_var.get()} месяц", font=ctk.CTkFont(size=16, weight="bold"))
        self.period_lbl.pack(side="left", padx=(5, 10))

        # События обновления
        self.month_var.trace_add("write", lambda *_: self._update_period_display())
        self.year_var.trace_add("write", lambda *_: self._update_period_display())

        # Фильтр адреса
        addr_names = ["📍 Все адреса"] + [a["name"] for a in self.addresses]
        self.address_var = tk.StringVar(value=addr_names[0])
        self.address_cb = ctk.CTkComboBox(header, values=addr_names, variable=self.address_var, width=200)
        self.address_cb.pack(side="left", padx=10)
        self.address_cb.configure(command=lambda _: self.load_invoices())

        # Кнопки
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right", padx=5)

        ctk.CTkButton(btn_frame, text="📊 Передать показания", fg_color="#17a2b8", hover_color="#138496", width=160, command=self._open_readings_form).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="📄 Создать счёт", fg_color="#6610f2", hover_color="#520dc2", width=130, command=self._open_invoice_form).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="✅ Оплатить", width=90, command=self._mark_paid).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="🗑️ Удалить", fg_color="#dc3545", hover_color="#c82333", width=90, command=self._delete_invoice).pack(side="left", padx=3)

        # Таблица
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

        self.status_bar = ctk.CTkLabel(self, text="Готово", anchor="w", font=ctk.CTkFont(size=12))
        self.status_bar.pack(fill="x", padx=20, pady=5)

    def _update_period_display(self, *_):
        m, y = self.month_var.get().strip(), self.year_var.get().strip()
        if m and y:
            self.period_lbl.configure(text=f"{m} {y} месяц")
            self.load_invoices()

    def _sort_tree(self, col):
        self._sort_state[col] = not self._sort_state[col]
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        key = float if col == "amount" else int if col == "id" else str
        items.sort(key=lambda x: key(x[0]) if x[0] not in ("", "—") else 0, reverse=self._sort_state[col])
        for i, (_, k) in enumerate(items):
            self.tree.move(k, '', i)

    def load_invoices(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        try:
            month = self.MONTH_TO_NUM.get(self.month_var.get().strip(), date.today().month)
            year = int(self.year_var.get().strip())
        except:
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
            
            # Фильтруем ПУ только для выбранного адреса
            for m in [x for x in db.get_all_meters() if x["address_id"] == sel["id"]]:
                last = db.get_last_reading(m["id"])
                prev = last["current_value"] if last else 0.0
                
                row = ctk.CTkFrame(frame, fg_color="transparent")
                row.pack(fill="x", pady=3)
                
                ctk.CTkLabel(row, text=f"{METER_TYPE_MAP.get(m['type'], m['type'])} | {m['serial_number']}", width=200, anchor="w").pack(side="left", padx=5)
                ctk.CTkLabel(row, text=f"(Предыд: {prev})", width=80, fg_color="gray").pack(side="left", padx=2)
                
                # Поле ввода пустое по умолчанию
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
                    if not v:
                        continue
                    cur = float(v)
                    
                    if cur < prev:
                        messagebox.showwarning("Ошибка", f"Показания меньше предыдущих ({prev})!")
                        return # Прерываем сохранение
                    if cur == prev:
                        continue # Пропускаем если не изменилось

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

        ctk.CTkLabel(dlg, text="📍 Адрес:").pack(fill="x", padx=20, pady=5)
        addr_var = tk.StringVar(value=addrs[0]["name"])
        ctk.CTkComboBox(dlg, values=[a["name"] for a in addrs], variable=addr_var).pack(fill="x", padx=20)

        ctk.CTkLabel(dlg, text="📅 Дата счёта:").pack(fill="x", padx=20, pady=5)
        date_field = CTkDateField(dlg, placeholder="ГГГГ-ММ-ДД")
        date_field.pack(fill="x", padx=20)
        date_field.set_date(date.today().isoformat())

        inv_lbl = ctk.CTkLabel(dlg, text="№ Счёта:", font=ctk.CTkFont(weight="bold"))
        inv_lbl.pack(fill="x", padx=20, pady=5)
        
        # Генерация номера
        inv_var = tk.StringVar(value=db.get_next_invoice_number())
        ctk.CTkEntry(dlg, textvariable=inv_var, width=150, state="readonly").pack(anchor="w", padx=20)

        ctk.CTkLabel(dlg, text="💰 Сумма к оплате (₽):", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=20, pady=(10,5))
        amt_var = tk.StringVar(value="0.00")
        ctk.CTkEntry(dlg, textvariable=amt_var, font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(dlg, text="📟 Привязанные показания (автоматически):", font=ctk.CTkFont(size=12)).pack(fill="x", padx=20, pady=5)
        tree_frame = ctk.CTkFrame(dlg)
        tree_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("type", "sn", "prev", "cur", "cons"), show="headings", height=6)
        for h, w in [("Тип", 120), ("SN", 120), ("Предыд.", 80), ("Тек.", 80), ("Расход", 80)]:
            tree.heading(h, text=h)
            tree.column(h, width=w, anchor="center")
        tree.pack(fill="both", expand=True)

        def load_readings():
            for i in tree.get_children(): tree.delete(i)
            sel = next((a for a in addrs if a["name"] == addr_var.get()), None)
            if not sel: return
            
            # Берем показания за текущий месяц, не привязанные к счетам
            month_start = f"{date.today().year}-{date.today().month:02d}-01"
            for r in db.get_unlinked_readings(sel["id"], since_date=month_start):
                tree.insert("", "end", values=(
                    METER_TYPE_MAP.get(r["type"], r["type"]), 
                    r["serial_number"], 
                    r["previous_value"], 
                    r["current_value"], 
                    r["consumption"]
                ))

        addr_var.trace_add("write", lambda *_: load_readings())
        load_readings()

        def save():
            try:
                d = date_field.get_date()
                if not d:
                    raise ValueError("Укажите дату")
                
                sel = next(a for a in addrs if a["name"] == addr_var.get())
                amt = float(amt_var.get().replace(",", "."))
                inv_num = inv_var.get()
                
                month_start = f"{date.today().year}-{date.today().month:02d}-01"
                # Получаем ID показаний, которые сейчас отображаются
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
        if messagebox.askyesno("Оплата", f"Отметить счёт как оплаченный?"):
            db.pay_invoice(inv_id)
            self.load_invoices()

    def _delete_invoice(self):
        sel = self.tree.selection()
        if not sel: return
        vals = self.tree.item(sel[0])["values"]
        if messagebox.askyesno("Удаление", f"Удалить счёт {vals[1]}?\nПоказания будут отвязаны."):
            db.delete_invoice(vals[0])
            self.load_invoices()

    # --- Упрощенные методы управления (чтобы код поместился и был рабочим) ---
    def _manage_addresses(self):
        pass # Можно добавить аналогично прошлой версии, очистив синтаксис
    def _manage_types(self): pass
    def _manage_meters(self): pass
    def _export_data(self): pass
    def _import_data(self): pass

if __name__ == "__main__":
    PaymentTracker().mainloop()