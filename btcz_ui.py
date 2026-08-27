import csv
import calendar
import json
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tkinter import filedialog, scrolledtext

import customtkinter as ctk
import requests
from PIL import Image, ImageTk

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "btcz_data"
DATA_DIR.mkdir(exist_ok=True)

ADDRESSES_FILE = DATA_DIR / "addresses.json"
LOGO_PNG = DATA_DIR / "btcz_logo.png"
LOGO_ICO = DATA_DIR / "btcz_logo.ico"

LOGO_URLS = [
    "https://cryptologos.cc/logos/bitcoinz-btcz-logo.png",
    "https://icons.iconarchive.com/icons/cjdowner/cryptocurrency-flat/256/BitcoinZ-BTCZ-icon.png",
]

LIMIT_RECENT = 200
LIMIT_FULL = 100
MINING_THRESHOLD = 20

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


def load_addresses():
    if ADDRESSES_FILE.exists():
        try:
            data = json.loads(ADDRESSES_FILE.read_text(encoding="utf-8"))
            return data.get("addresses", [])
        except Exception:
            return []
    return []


def save_addresses(addresses):
    unique = []
    for addr in addresses:
        addr = addr.strip()
        if addr and addr not in unique:
            unique.append(addr)
    ADDRESSES_FILE.write_text(
        json.dumps({"addresses", unique}, indent=2) if False else json.dumps({"addresses": unique}, indent=2),
        encoding="utf-8",
    )
    return unique


def remember_address(address):
    addresses = load_addresses()
    address = address.strip()
    if address in addresses:
        addresses.remove(address)
    addresses.insert(0, address)
    return save_addresses(addresses)


def remove_address(address):
    addresses = load_addresses()
    address = address.strip()
    if address in addresses:
        addresses.remove(address)
    return save_addresses(addresses)


def ensure_logo():
    if not LOGO_PNG.exists():
        for url in LOGO_URLS:
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                if resp.content:
                    LOGO_PNG.write_bytes(resp.content)
                    break
            except Exception:
                continue

    if LOGO_PNG.exists() and not LOGO_ICO.exists():
        try:
            img = Image.open(LOGO_PNG).convert("RGBA")
            img.save(
                LOGO_ICO,
                format="ICO",
                sizes=[(16, 16), (32, 32), (48, 48), (64, 64)],
            )
        except Exception:
            pass


def fetch_transactions(address, is_single_day, log):
    if is_single_day:
        log("Loading latest transactions (fast mode)...")
        url = f"https://explorer.getbtcz.com/api/addresses/{address}/transactions?limit={LIMIT_RECENT}&offset=0"
        try:
            resp = requests.get(url, timeout=15)
            txs = resp.json().get("transactions", [])
            log(f"Loaded {len(txs)} transactions.\n", "ok")
            return txs
        except Exception as e:
            log(f"Fast mode error: {e}", "err")
            log("Switching to full history mode...\n", "warn")

    log("Loading full transaction history...")
    all_txs = []
    offset = 0

    while True:
        url = f"https://explorer.getbtcz.com/api/addresses/{address}/transactions?limit={LIMIT_FULL}&offset={offset}"
        try:
            resp = requests.get(url, timeout=20)
            data = resp.json()
            txs = data.get("transactions", [])
            all_txs.extend(txs)
            log(f"   -> {len(all_txs)} transactions loaded...")

            if len(txs) < LIMIT_FULL:
                break
            offset += LIMIT_FULL
        except Exception as e:
            log(f"Error: {e}", "err")
            break

    log(f"Loaded {len(all_txs)} transactions in total.\n", "ok")
    return all_txs


def analyze_range(address, start_str, end_str, show_details, log):
    fmt = "%d/%m/%Y" if "/" in start_str else "%Y-%m-%d"
    start = datetime.strptime(start_str, fmt).replace(tzinfo=timezone.utc)
    end = datetime.strptime(end_str, fmt).replace(tzinfo=timezone.utc)

    if end < start:
        log("End date is before start date.", "err")
        return []

    is_single_day = start == end
    log(f"Analyzing {start_str} to {end_str}...\n", "info") 

    txs = fetch_transactions(address, is_single_day, log)

    total_period = 0.0
    mining_total = 0
    daily_results = []

    current = start
    while current <= end:
        date_str = current.strftime("%d/%m/%Y")
        start_ts = int(current.timestamp())
        end_ts = start_ts + 86400

        daily_total = 0.0
        daily_mining = 0

        for tx in txs:
            if start_ts <= tx.get("time", 0) < end_ts:
                value = float(tx.get("value", 0) or 0)
                daily_total += value
                if value > MINING_THRESHOLD:
                    daily_mining += 1
                    if show_details:
                        log(f"MINING  {date_str}  +{value:.8f} BTCZ", "mine")

        if daily_total > 0 or daily_mining > 0:
            daily_results.append((date_str, daily_total, daily_mining))
            total_period += daily_total
            mining_total += daily_mining

        current += timedelta(days=1)

    log("=" * 70, "title")
    log(f"RESULT  {start_str}  ->  {end_str}", "ok")
    log("=" * 70, "title")

    if not daily_results:
        log("No incoming transactions found for this period.", "warn")
    else:
        for date, total, mining in daily_results:
            log(
                f"{date}  ->  {total:12.8f} BTCZ   ({mining:2d} mining rewards)",
                "ok" if mining else "info",
            )

    log("-" * 70, "title")
    log(f"PERIOD TOTAL           : {total_period:.8f} BTCZ", "ok")
    log(f"Total mining rewards   : {mining_total} transactions", "mine")
    log("=" * 70, "title")
    return daily_results


class DatePicker(ctk.CTkToplevel):
    def __init__(self, master, target_entry):
        super().__init__(master)
        self.target_entry = target_entry
        self.title("Select date")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        today = datetime.now()
        current = target_entry.get().strip()
        try:
            selected = datetime.strptime(current, "%d/%m/%Y")
        except Exception:
            selected = today

        self.year = selected.year
        self.month = selected.month

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkButton(self.header, text="<", width=36, command=self.prev_month).pack(side="left")
        self.title_lbl = ctk.CTkLabel(self.header, text="", font=ctk.CTkFont(size=15, weight="bold"))
        self.title_lbl.pack(side="left", expand=True)
        ctk.CTkButton(self.header, text=">", width=36, command=self.next_month).pack(side="right")

        self.grid_frame = ctk.CTkFrame(self)
        self.grid_frame.pack(padx=12, pady=(0, 12))

        self.draw()
        self.after(50, self.center)

    def center(self):
        self.update_idletasks()
        x = self.master.winfo_rootx() + 80
        y = self.master.winfo_rooty() + 120
        self.geometry(f"+{x}+{y}")

    def prev_month(self):
        if self.month == 1:
            self.month = 12
            self.year -= 1
        else:
            self.month -= 1
        self.draw()

    def next_month(self):
        if self.month == 12:
            self.month = 1
            self.year += 1
        else:
            self.month += 1
        self.draw()

    def draw(self):
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        self.title_lbl.configure(text=datetime(self.year, self.month, 1).strftime("%B %Y"))

        days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        for col, day in enumerate(days):
            ctk.CTkLabel(self.grid_frame, text=day, width=36).grid(row=0, column=col, padx=2, pady=2)

        month_days = calendar.Calendar(firstweekday=0).monthdayscalendar(self.year, self.month)
        for row, week in enumerate(month_days, start=1):
            for col, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(self.grid_frame, text="", width=36).grid(row=row, column=col, padx=2, pady=2)
                    continue
                date_str = f"{day:02d}/{self.month:02d}/{self.year}"
                ctk.CTkButton(
                    self.grid_frame,
                    text=str(day),
                    width=36,
                    command=lambda value=date_str: self.choose(value),
                ).grid(row=row, column=col, padx=2, pady=2)

    def choose(self, value):
        self.target_entry.delete(0, "end")
        self.target_entry.insert(0, value)
        self.destroy()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("BTCZ Mining Tracker")
        self.geometry("980x740")
        self.minsize(860, 660)

        ensure_logo()
        self.set_window_icon()

        self.last_results = []
        self.addresses = load_addresses()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(16, 6), sticky="ew")

        if LOGO_PNG.exists():
            logo_img = Image.open(LOGO_PNG).convert("RGBA")
            logo_img = logo_img.resize((42, 42), Image.Resampling.LANCZOS)
            self.logo_ctk = ctk.CTkImage(light_image=logo_img, dark_image=logo_img, size=(42, 42))
            ctk.CTkLabel(header, image=self.logo_ctk, text="").pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            header,
            text="BTCZ Mining Tracker",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(side="left")

        form = ctk.CTkFrame(self, corner_radius=16)
        form.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        form.grid_columnconfigure(1, weight=1)
        form.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(form, text="Address").grid(row=0, column=0, padx=14, pady=(14, 6), sticky="w")

        address_wrap = ctk.CTkFrame(form, fg_color="transparent")
        address_wrap.grid(row=0, column=1, columnspan=3, padx=14, pady=(14, 6), sticky="ew")
        address_wrap.grid_columnconfigure(0, weight=1)

        self.address = ctk.CTkComboBox(
            address_wrap,
            values=self.addresses or [""],
            height=36,
        )
        self.address.set("")
        self.address.grid(row=0, column=0, sticky="ew")

        self.remove_btn = ctk.CTkButton(
            address_wrap,
            text="Remove",
            width=90,
            height=36,
            fg_color="#8B1E1E",
            hover_color="#A82828",
            command=self.remove_selected_address,
        )
        self.remove_btn.grid(row=0, column=1, padx=(8, 0))

        hint = ctk.CTkLabel(
            form,
            text="Enter a transparent BTCZ address (t1...)",
            text_color="#9aa0a6",
        )
        hint.grid(row=1, column=1, columnspan=3, padx=14, pady=(0, 6), sticky="w")

        ctk.CTkLabel(form, text="Start date").grid(row=2, column=0, padx=14, pady=6, sticky="w")
        start_wrap = ctk.CTkFrame(form, fg_color="transparent")
        start_wrap.grid(row=2, column=1, padx=14, pady=6, sticky="ew")
        start_wrap.grid_columnconfigure(0, weight=1)
        self.start = ctk.CTkEntry(start_wrap, placeholder_text="DD/MM/YYYY", height=36)
        self.start.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(start_wrap, text="📅", width=42, command=lambda: DatePicker(self, self.start)).grid(
            row=0, column=1, padx=(8, 0)
        )

        ctk.CTkLabel(form, text="End date").grid(row=2, column=2, padx=14, pady=6, sticky="w")
        end_wrap = ctk.CTkFrame(form, fg_color="transparent")
        end_wrap.grid(row=2, column=3, padx=14, pady=6, sticky="ew")
        end_wrap.grid_columnconfigure(0, weight=1)
        self.end = ctk.CTkEntry(end_wrap, placeholder_text="Same as start = 1 day", height=36)
        self.end.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(end_wrap, text="📅", width=42, command=lambda: DatePicker(self, self.end)).grid(
            row=0, column=1, padx=(8, 0)
        )

        self.details = ctk.CTkSwitch(form, text="Show transaction details")
        self.details.grid(row=3, column=0, columnspan=2, padx=14, pady=(8, 14), sticky="w")

        buttons = ctk.CTkFrame(form, fg_color="transparent")
        buttons.grid(row=3, column=3, padx=14, pady=(8, 14), sticky="e")

        self.export_btn = ctk.CTkButton(
            buttons, text="Export CSV", height=40, fg_color="#2b2b2b", command=self.export_csv
        )
        self.export_btn.pack(side="left", padx=(0, 8))

        self.btn = ctk.CTkButton(buttons, text="Analyze", height=40, command=self.run_analysis)
        self.btn.pack(side="left")

        self.output = scrolledtext.ScrolledText(
            self,
            wrap="word",
            bg="#111111",
            fg="#e8e8e8",
            insertbackground="white",
            font=("Consolas", 11),
            relief="flat",
            borderwidth=0,
        )
        self.output.grid(row=2, column=0, padx=20, pady=(8, 8), sticky="nsew")
        self.output.tag_config("ok", foreground="#3DDC97")
        self.output.tag_config("err", foreground="#FF6B6B")
        self.output.tag_config("warn", foreground="#F4C430")
        self.output.tag_config("info", foreground="#7EC8E3")
        self.output.tag_config("mine", foreground="#FFD166")
        self.output.tag_config("title", foreground="#C084FC")

        self.status = ctk.CTkLabel(self, text="Ready", anchor="w")
        self.status.grid(row=3, column=0, padx=22, pady=(0, 14), sticky="ew")

    def set_window_icon(self):
        try:
            if LOGO_ICO.exists():
                self.iconbitmap(str(LOGO_ICO))
            elif LOGO_PNG.exists():
                img = Image.open(LOGO_PNG)
                self._icon = ImageTk.PhotoImage(img)
                self.iconphoto(True, self._icon)
        except Exception:
            pass

    def refresh_address_box(self, selected=""):
        self.address.configure(values=self.addresses or [""])
        self.address.set(selected)

    def remove_selected_address(self):
        address = self.address.get().strip()
        if not address:
            self.log("No address selected.", "warn")
            return

        if address not in load_addresses():
            self.address.set("")
            self.log("This address was not saved in history.", "warn")
            return

        self.addresses = remove_address(address)
        self.refresh_address_box("")
        self.log(f"Address removed from history: {address}", "ok")
        self.status.configure(text="Address removed")

    def log(self, text, tag="info"):
        self.output.insert("end", text + "\n", tag)
        self.output.see("end")
        self.update_idletasks()

    def run_analysis(self):
        address = self.address.get().strip()
        start = self.start.get().strip()
        end = self.end.get().strip() or start
        show_details = self.details.get() == 1

        if not address:
            self.log("Please enter a BTCZ transparent address (t1...).", "err")
            return
        if not start:
            self.log("Please select a start date.", "err")
            return

        self.addresses = remember_address(address)
        self.refresh_address_box(address)

        self.output.delete("1.0", "end")
        self.last_results = []
        self.btn.configure(state="disabled", text="Analyzing...")
        self.status.configure(text="Analyzing...")

        def worker():
            try:
                self.last_results = analyze_range(address, start, end, show_details, self.log)
                self.status.configure(text="Done")
            except ValueError:
                self.log("Invalid date format. Use DD/MM/YYYY.", "err")
                self.status.configure(text="Date error")
            except Exception as e:
                self.log(f"Error: {e}", "err")
                self.status.configure(text="Error")
            finally:
                self.btn.configure(state="normal", text="Analyze")

        threading.Thread(target=worker, daemon=True).start()

    def export_csv(self):
        if not self.last_results:
            self.log("Nothing to export yet. Run an analysis first.", "warn")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="btcz_mining_report.csv",
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Received BTCZ", "Mining rewards"])
            total = 0.0
            mining = 0
            for date, amount, rewards in self.last_results:
                writer.writerow([date, f"{amount:.8f}", rewards])
                total += amount
                mining += rewards
            writer.writerow([])
            writer.writerow(["TOTAL", f"{total:.8f}", mining])

        self.log(f"CSV exported: {path}", "ok")


if __name__ == "__main__":
    app = App()
    app.mainloop()