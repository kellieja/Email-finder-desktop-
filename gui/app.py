"""EmailFinder desktop GUI — a clean, modern interface built on CustomTkinter.

Two tabs:
    * Single  — type a name + company domain, get the best email + score.
    * Bulk    — upload a CSV, watch live progress, export results.

Network work runs on background threads so the window never freezes; results
are marshalled back to the UI thread through a thread-safe queue.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from emailfinder import EmailFinder, __version__
from emailfinder.bulk import BulkInput, process, read_inputs, write_results
from emailfinder.models import Result

APP_TITLE = "EmailFinder"

# --- palette -----------------------------------------------------------------
ACCENT = "#2563eb"          # blue-600
ACCENT_HOVER = "#1d4ed8"    # blue-700
BG = "#f4f5f7"
CARD = "#ffffff"
TEXT_MUTED = "#6b7280"
OK_GREEN = "#16a34a"
WARN_AMBER = "#d97706"
BAD_RED = "#dc2626"

FONT = "Segoe UI"           # ships on Windows; CTk falls back gracefully


def _confidence_color(score: int) -> str:
    if score >= 75:
        return OK_GREEN
    if score >= 50:
        return ACCENT
    if score >= 25:
        return WARN_AMBER
    return BAD_RED


def _confidence_label(score: int) -> str:
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    if score >= 25:
        return "Low"
    return "Very low"


def _style_treeview() -> None:
    """Make the (still-ttk) data table blend with the modern theme."""
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "Modern.Treeview",
        background=CARD,
        fieldbackground=CARD,
        foreground="#1f2937",
        rowheight=30,
        borderwidth=0,
        font=(FONT, 10),
    )
    style.configure(
        "Modern.Treeview.Heading",
        background="#eef0f3",
        foreground="#374151",
        relief="flat",
        font=(FONT, 10, "bold"),
        padding=6,
    )
    style.map("Modern.Treeview.Heading", background=[("active", "#e2e6ea")])
    style.map("Modern.Treeview", background=[("selected", "#dbeafe")],
              foreground=[("selected", "#1e3a8a")])


class EmailFinderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} — find & verify business emails")
        self.geometry("1000x700")
        self.minsize(820, 560)
        self.configure(fg_color=BG)

        # Background-thread -> UI-thread message queue.
        self._events: "queue.Queue[tuple]" = queue.Queue()
        self._bulk_thread: threading.Thread | None = None
        self._single_thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._bulk_results: list[Result] = []
        self._bulk_inputs: list[BulkInput] = []

        _style_treeview()
        self._build_header()
        self._build_tabs()

        self.after(100, self._drain_events)

    # ------------------------------------------------------------------ header
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 4))

        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(fill="x")
        ctk.CTkLabel(
            title_row, text="📧  EmailFinder",
            font=ctk.CTkFont(family=FONT, size=24, weight="bold"),
            text_color="#111827",
        ).pack(side="left")
        ctk.CTkLabel(
            title_row, text=f"v{__version__}",
            font=ctk.CTkFont(family=FONT, size=12),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(8, 0), pady=(8, 0))

        ctk.CTkLabel(
            header,
            text="Find a person's most likely work email from their name and company — no SMTP, no API keys.",
            font=ctk.CTkFont(family=FONT, size=13),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 10))

        # Options row.
        opts = ctk.CTkFrame(header, fg_color="transparent")
        opts.pack(fill="x")
        self.deep_verify = tk.BooleanVar(value=True)
        self.scrape_site = tk.BooleanVar(value=True)
        ctk.CTkSwitch(
            opts, text="Deep verify (Gravatar + GitHub)",
            variable=self.deep_verify, progress_color=ACCENT,
            font=ctk.CTkFont(family=FONT, size=12),
        ).pack(side="left")
        ctk.CTkSwitch(
            opts, text="Scrape company website",
            variable=self.scrape_site, progress_color=ACCENT,
            font=ctk.CTkFont(family=FONT, size=12),
        ).pack(side="left", padx=(20, 0))

    def _make_finder(self) -> EmailFinder:
        return EmailFinder(
            deep_verify=self.deep_verify.get(),
            scrape_site=self.scrape_site.get(),
        )

    # -------------------------------------------------------------------- tabs
    def _build_tabs(self) -> None:
        self.tabs = ctk.CTkTabview(
            self, fg_color=CARD, segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            corner_radius=14,
        )
        self.tabs.pack(fill="both", expand=True, padx=24, pady=(8, 24))
        self.tabs.add("Single lookup")
        self.tabs.add("Bulk upload")
        self._build_single_tab(self.tabs.tab("Single lookup"))
        self._build_bulk_tab(self.tabs.tab("Bulk upload"))

    # ------------------------------------------------------------------ single
    def _build_single_tab(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)

        form = ctk.CTkFrame(tab, fg_color="transparent")
        form.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        self.name_var = tk.StringVar()
        self.domain_var = tk.StringVar()
        name_entry = ctk.CTkEntry(
            form, textvariable=self.name_var, height=42,
            placeholder_text="Full name  (e.g. Ada Lovelace)",
            font=ctk.CTkFont(family=FONT, size=14), corner_radius=10,
        )
        domain_entry = ctk.CTkEntry(
            form, textvariable=self.domain_var, height=42,
            placeholder_text="Company domain  (e.g. example.com)",
            font=ctk.CTkFont(family=FONT, size=14), corner_radius=10,
        )
        name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        domain_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        self.find_btn = ctk.CTkButton(
            form, text="Find email", height=42, width=140,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
            command=self._on_find,
        )
        self.find_btn.grid(row=0, column=2, padx=(12, 0))
        name_entry.bind("<Return>", lambda _e: self._on_find())
        domain_entry.bind("<Return>", lambda _e: self._on_find())

        # Result card.
        self.result_card = ctk.CTkFrame(tab, fg_color="#f8fafc", corner_radius=12)
        self.result_card.grid(row=1, column=0, sticky="ew", padx=16, pady=12)
        self.result_card.grid_columnconfigure(0, weight=1)

        self.single_status = ctk.CTkLabel(
            self.result_card, text="Enter a name and company domain, then click Find email.",
            font=ctk.CTkFont(family=FONT, size=13), text_color=TEXT_MUTED,
        )
        self.single_status.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 0))

        email_row = ctk.CTkFrame(self.result_card, fg_color="transparent")
        email_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(2, 14))
        self.best_email_lbl = ctk.CTkLabel(
            email_row, text="", font=ctk.CTkFont(family=FONT, size=22, weight="bold"),
            text_color="#111827",
        )
        self.best_email_lbl.pack(side="left")
        self.badge = ctk.CTkLabel(
            email_row, text="", width=110, height=30, corner_radius=15,
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            text_color="#ffffff",
        )
        self.copy_btn = ctk.CTkButton(
            email_row, text="Copy", width=64, height=30, corner_radius=8,
            fg_color="#e5e7eb", hover_color="#d1d5db", text_color="#111827",
            font=ctk.CTkFont(family=FONT, size=12),
            command=self._copy_best,
        )

        # Candidate table.
        table_wrap = ctk.CTkFrame(tab, fg_color="transparent")
        table_wrap.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 16))
        tab.grid_rowconfigure(2, weight=1)
        self.single_tree = self._make_tree(
            table_wrap,
            cols=("email", "confidence", "pattern", "source", "signals"),
            widths=(250, 100, 100, 90, 320),
        )

    def _copy_best(self) -> None:
        email = self.best_email_lbl.cget("text")
        if email:
            self.clipboard_clear()
            self.clipboard_append(email)

    def _on_find(self) -> None:
        if self._single_thread and self._single_thread.is_alive():
            return
        name = self.name_var.get().strip()
        domain = self.domain_var.get().strip()
        if not name or not domain:
            messagebox.showinfo(APP_TITLE, "Enter both a name and a company domain.")
            return
        self.find_btn.configure(state="disabled", text="Searching…")
        self.single_status.configure(text="Searching… checking DNS, website, and verification signals.")
        self.best_email_lbl.configure(text="")
        self.badge.pack_forget()
        self.copy_btn.pack_forget()
        self.single_tree.delete(*self.single_tree.get_children())

        finder = self._make_finder()

        def worker():
            try:
                result = finder.find(name, domain)
                self._events.put(("single_done", result))
            except Exception as exc:
                self._events.put(("single_error", str(exc)))

        self._single_thread = threading.Thread(target=worker, daemon=True)
        self._single_thread.start()

    def _render_single(self, result: Result) -> None:
        self.find_btn.configure(state="normal", text="Find email")
        if result.error:
            self.single_status.configure(text=f"⚠  {result.error}")
            return
        if not result.candidates:
            self.single_status.configure(text="No candidates found for that name/domain.")
            return
        best = result.best
        self.single_status.configure(text=f"Best match  ·  {len(result.candidates)} candidate(s) found")
        self.best_email_lbl.configure(text=best.email)
        color = _confidence_color(best.score)
        self.badge.configure(text=f"{best.score}%  {_confidence_label(best.score)}", fg_color=color)
        self.badge.pack(side="left", padx=(14, 0))
        self.copy_btn.pack(side="left", padx=(10, 0))

        for cand in result.candidates:
            self.single_tree.insert(
                "", "end",
                values=(cand.email, f"{cand.score}%", cand.pattern,
                        cand.source, "; ".join(cand.signals)),
            )

    # -------------------------------------------------------------------- bulk
    def _build_bulk_tab(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)

        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))

        def mkbtn(text, cmd, primary=False, state="normal"):
            return ctk.CTkButton(
                bar, text=text, command=cmd, height=40, corner_radius=10,
                state=state,
                fg_color=ACCENT if primary else "#e5e7eb",
                hover_color=ACCENT_HOVER if primary else "#d1d5db",
                text_color="#ffffff" if primary else "#111827",
                font=ctk.CTkFont(family=FONT, size=13, weight="bold" if primary else "normal"),
            )

        self.load_btn = mkbtn("📂  Load CSV", self._on_load_csv)
        self.load_btn.pack(side="left")
        self.run_btn = mkbtn("▶  Run", self._on_run_bulk, primary=True, state="disabled")
        self.run_btn.pack(side="left", padx=8)
        self.stop_btn = mkbtn("■  Stop", self._on_stop_bulk, state="disabled")
        self.stop_btn.pack(side="left")
        self.export_btn = mkbtn("💾  Export results", self._on_export, state="disabled")
        self.export_btn.pack(side="right")

        ctk.CTkLabel(
            tab,
            text="Upload a CSV with a header row containing a name column and a "
                 "domain/company column — they're detected automatically.",
            font=ctk.CTkFont(family=FONT, size=12), text_color=TEXT_MUTED,
            anchor="w", justify="left",
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 8))

        prog = ctk.CTkFrame(tab, fg_color="transparent")
        prog.grid(row=2, column=0, sticky="ew", padx=16)
        prog.grid_columnconfigure(0, weight=1)
        self.bulk_progress = ctk.CTkProgressBar(prog, height=10, corner_radius=6,
                                                progress_color=ACCENT)
        self.bulk_progress.set(0)
        self.bulk_progress.grid(row=0, column=0, sticky="ew")
        self.bulk_status = ctk.CTkLabel(
            prog, text="No file loaded.", font=ctk.CTkFont(family=FONT, size=12),
            text_color=TEXT_MUTED,
        )
        self.bulk_status.grid(row=1, column=0, sticky="w", pady=(6, 8))

        table_wrap = ctk.CTkFrame(tab, fg_color="transparent")
        table_wrap.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.bulk_tree = self._make_tree(
            table_wrap,
            cols=("name", "domain", "best_email", "confidence", "pattern", "signals"),
            widths=(150, 150, 240, 100, 100, 260),
        )

    def _make_tree(self, parent, cols, widths) -> ttk.Treeview:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        tree = ttk.Treeview(parent, columns=cols, show="headings",
                            style="Modern.Treeview")
        for col, width in zip(cols, widths):
            tree.heading(col, text=col.replace("_", " ").title())
            tree.column(col, width=width, anchor="w")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        return tree

    def _on_load_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose a CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._bulk_inputs = read_inputs(path)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not read CSV:\n{exc}")
            return
        self.bulk_tree.delete(*self.bulk_tree.get_children())
        self._bulk_results = []
        self.export_btn.configure(state="disabled")
        n = len(self._bulk_inputs)
        if n == 0:
            self.bulk_status.configure(text="That file had no usable rows.")
            self.run_btn.configure(state="disabled")
            return
        self.bulk_status.configure(
            text=f"Loaded {n} row(s) from {os.path.basename(path)}. Ready to run."
        )
        self.bulk_progress.set(0)
        self.run_btn.configure(state="normal")

    def _on_run_bulk(self) -> None:
        if self._bulk_thread and self._bulk_thread.is_alive():
            return
        if not self._bulk_inputs:
            return
        self._stop_flag.clear()
        self._bulk_results = []
        self.bulk_tree.delete(*self.bulk_tree.get_children())
        self.bulk_progress.set(0)
        self.run_btn.configure(state="disabled")
        self.load_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        finder = self._make_finder()
        inputs = list(self._bulk_inputs)

        def progress(done: int, total: int, result: Result) -> None:
            self._events.put(("bulk_row", done, total, result))

        def worker():
            process(inputs, finder, progress=progress,
                    should_stop=self._stop_flag.is_set)
            self._events.put(("bulk_done",))

        self._bulk_thread = threading.Thread(target=worker, daemon=True)
        self._bulk_thread.start()

    def _on_stop_bulk(self) -> None:
        self._stop_flag.set()
        self.bulk_status.configure(text="Stopping…")

    def _on_export(self) -> None:
        if not self._bulk_results:
            return
        path = filedialog.asksaveasfilename(
            title="Save results as", defaultextension=".csv",
            initialfile="email_results.csv", filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        try:
            write_results(path, self._bulk_results)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not write file:\n{exc}")
            return
        messagebox.showinfo(APP_TITLE, f"Saved {len(self._bulk_results)} rows to:\n{path}")

    def _append_bulk_row(self, result: Result) -> None:
        self._bulk_results.append(result)
        best = result.best
        self.bulk_tree.insert(
            "", "end",
            values=(
                result.name, result.domain,
                result.best_email or (result.error or "—"),
                f"{result.best_score}%" if best else "",
                best.pattern if best else "",
                "; ".join(best.signals) if best else "",
            ),
        )
        self.bulk_tree.yview_moveto(1.0)

    # ------------------------------------------------------------- UI pump
    def _drain_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                kind = event[0]
                if kind == "single_done":
                    self._render_single(event[1])
                elif kind == "single_error":
                    self.find_btn.configure(state="normal", text="Find email")
                    self.single_status.configure(text=f"⚠  {event[1]}")
                elif kind == "bulk_row":
                    _, done, total, result = event
                    self.bulk_progress.set(done / total if total else 0)
                    self.bulk_status.configure(text=f"Processing {done}/{total}…")
                    self._append_bulk_row(result)
                elif kind == "bulk_done":
                    self._finish_bulk()
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _finish_bulk(self) -> None:
        self.run_btn.configure(state="normal")
        self.load_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        done = len(self._bulk_results)
        if done:
            self.export_btn.configure(state="normal")
        stopped = self._stop_flag.is_set()
        self.bulk_status.configure(
            text=f"{'Stopped' if stopped else 'Finished'} — {done} row(s) processed. "
                 f"Click Export results to save."
        )


def main() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = EmailFinderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
