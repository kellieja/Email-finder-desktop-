"""EmailFinder desktop GUI (Tkinter, standard-library only).

Two tabs:
    * Single  — type a name + company domain, get the best email + score.
    * Bulk    — upload a CSV, watch progress, export results.

Network work runs on background threads so the window never freezes; results
are marshalled back to the UI thread through a thread-safe queue.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from emailfinder import EmailFinder, __version__
from emailfinder.bulk import BulkInput, process, read_inputs, write_results
from emailfinder.models import Result

APP_TITLE = "EmailFinder Desktop"


def _confidence_label(score: int) -> str:
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    if score >= 25:
        return "Low"
    return "Very low"


class EmailFinderApp(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        self.master = master
        self.pack(fill="both", expand=True)

        # Background-thread -> UI-thread message queue.
        self._events: "queue.Queue[tuple]" = queue.Queue()
        self._bulk_thread: threading.Thread | None = None
        self._single_thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._bulk_results: list[Result] = []

        self._build_options_bar()
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, pady=(10, 0))
        self._build_single_tab(notebook)
        self._build_bulk_tab(notebook)

        self.after(100, self._drain_events)

    # ------------------------------------------------------------------ setup
    def _make_finder(self) -> EmailFinder:
        return EmailFinder(
            deep_verify=self.deep_verify.get(),
            scrape_site=self.scrape_site.get(),
        )

    def _build_options_bar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        self.deep_verify = tk.BooleanVar(value=True)
        self.scrape_site = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bar, text="Verify with Gravatar + GitHub (slower, better)",
            variable=self.deep_verify,
        ).pack(side="left")
        ttk.Checkbutton(
            bar, text="Scrape company website", variable=self.scrape_site,
        ).pack(side="left", padx=(16, 0))

    # ---------------------------------------------------------------- single
    def _build_single_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text="  Single lookup  ")

        form = ttk.Frame(tab)
        form.pack(fill="x")
        ttk.Label(form, text="Full name").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Label(form, text="Company domain").grid(row=1, column=0, sticky="w", pady=4)

        self.name_var = tk.StringVar()
        self.domain_var = tk.StringVar()
        name_entry = ttk.Entry(form, textvariable=self.name_var, width=40)
        domain_entry = ttk.Entry(form, textvariable=self.domain_var, width=40)
        name_entry.grid(row=0, column=1, sticky="we", padx=8)
        domain_entry.grid(row=1, column=1, sticky="we", padx=8)
        form.columnconfigure(1, weight=1)

        ttk.Label(
            form, text="e.g.  Ada Lovelace   +   example.com",
            foreground="#888",
        ).grid(row=2, column=1, sticky="w", padx=8)

        self.find_btn = ttk.Button(form, text="Find email", command=self._on_find)
        self.find_btn.grid(row=0, column=2, rowspan=2, padx=(8, 0))
        name_entry.bind("<Return>", lambda _e: self._on_find())
        domain_entry.bind("<Return>", lambda _e: self._on_find())

        # Result panel.
        self.single_status = ttk.Label(tab, text="", foreground="#555")
        self.single_status.pack(anchor="w", pady=(12, 4))

        self.best_var = tk.StringVar(value="")
        best = ttk.Label(tab, textvariable=self.best_var,
                         font=("TkDefaultFont", 14, "bold"))
        best.pack(anchor="w")
        self.best_meta = ttk.Label(tab, text="", foreground="#555")
        self.best_meta.pack(anchor="w", pady=(0, 8))

        cols = ("email", "confidence", "pattern", "source", "signals")
        self.single_tree = ttk.Treeview(tab, columns=cols, show="headings", height=8)
        for col, width in zip(cols, (240, 90, 90, 90, 320)):
            self.single_tree.heading(col, text=col.title())
            self.single_tree.column(col, width=width, anchor="w")
        self.single_tree.pack(fill="both", expand=True, pady=(4, 0))

    def _on_find(self) -> None:
        if self._single_thread and self._single_thread.is_alive():
            return
        name = self.name_var.get().strip()
        domain = self.domain_var.get().strip()
        if not name or not domain:
            messagebox.showinfo(APP_TITLE, "Enter both a name and a company domain.")
            return
        self.find_btn.config(state="disabled")
        self.single_status.config(text="Searching… (DNS, website, verification)")
        self.best_var.set("")
        self.best_meta.config(text="")
        self.single_tree.delete(*self.single_tree.get_children())

        finder = self._make_finder()

        def worker():
            try:
                result = finder.find(name, domain)
                self._events.put(("single_done", result))
            except Exception as exc:  # never let a thread die silently
                self._events.put(("single_error", str(exc)))

        self._single_thread = threading.Thread(target=worker, daemon=True)
        self._single_thread.start()

    def _render_single(self, result: Result) -> None:
        self.find_btn.config(state="normal")
        if result.error:
            self.single_status.config(text=f"⚠  {result.error}")
            return
        if not result.candidates:
            self.single_status.config(text="No candidates found.")
            return
        best = result.best
        self.single_status.config(text=f"Done — {len(result.candidates)} candidate(s).")
        self.best_var.set(best.email)
        self.best_meta.config(
            text=f"Confidence {best.score}% ({_confidence_label(best.score)})  ·  "
                 f"{', '.join(best.signals)}"
        )
        for cand in result.candidates:
            self.single_tree.insert(
                "", "end",
                values=(cand.email, f"{cand.score}%", cand.pattern,
                        cand.source, "; ".join(cand.signals)),
            )

    # ------------------------------------------------------------------ bulk
    def _build_bulk_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text="  Bulk upload  ")

        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.load_btn = ttk.Button(top, text="📂 Load CSV…", command=self._on_load_csv)
        self.load_btn.pack(side="left")
        self.run_btn = ttk.Button(top, text="▶ Run", command=self._on_run_bulk,
                                  state="disabled")
        self.run_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(top, text="■ Stop", command=self._on_stop_bulk,
                                   state="disabled")
        self.stop_btn.pack(side="left")
        self.export_btn = ttk.Button(top, text="💾 Export results…",
                                     command=self._on_export, state="disabled")
        self.export_btn.pack(side="right")

        ttk.Label(
            tab,
            text="CSV needs a header row with a name column and a domain/company "
                 "column. Columns are auto-detected.",
            foreground="#888",
        ).pack(anchor="w", pady=(6, 0))

        self.bulk_progress = ttk.Progressbar(tab, mode="determinate")
        self.bulk_progress.pack(fill="x", pady=(8, 2))
        self.bulk_status = ttk.Label(tab, text="No file loaded.", foreground="#555")
        self.bulk_status.pack(anchor="w")

        cols = ("name", "domain", "best_email", "confidence", "pattern", "signals")
        self.bulk_tree = ttk.Treeview(tab, columns=cols, show="headings")
        for col, width in zip(cols, (140, 150, 230, 90, 90, 260)):
            self.bulk_tree.heading(col, text=col.replace("_", " ").title())
            self.bulk_tree.column(col, width=width, anchor="w")
        yscroll = ttk.Scrollbar(tab, orient="vertical", command=self.bulk_tree.yview)
        self.bulk_tree.configure(yscrollcommand=yscroll.set)
        self.bulk_tree.pack(side="left", fill="both", expand=True, pady=(8, 0))
        yscroll.pack(side="right", fill="y", pady=(8, 0))

        self._bulk_inputs: list[BulkInput] = []

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
        self.export_btn.config(state="disabled")
        n = len(self._bulk_inputs)
        if n == 0:
            self.bulk_status.config(text="That file had no usable rows.")
            self.run_btn.config(state="disabled")
            return
        self.bulk_status.config(
            text=f"Loaded {n} row(s) from {os.path.basename(path)}. Ready to run."
        )
        self.bulk_progress.config(maximum=n, value=0)
        self.run_btn.config(state="normal")

    def _on_run_bulk(self) -> None:
        if self._bulk_thread and self._bulk_thread.is_alive():
            return
        if not self._bulk_inputs:
            return
        self._stop_flag.clear()
        self._bulk_results = []
        self.bulk_tree.delete(*self.bulk_tree.get_children())
        self.bulk_progress.config(value=0)
        self.run_btn.config(state="disabled")
        self.load_btn.config(state="disabled")
        self.export_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

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
        self.bulk_status.config(text="Stopping…")

    def _on_export(self) -> None:
        if not self._bulk_results:
            return
        path = filedialog.asksaveasfilename(
            title="Save results as",
            defaultextension=".csv",
            initialfile="email_results.csv",
            filetypes=[("CSV files", "*.csv")],
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
                    self.find_btn.config(state="normal")
                    self.single_status.config(text=f"⚠  {event[1]}")
                elif kind == "bulk_row":
                    _, done, total, result = event
                    self.bulk_progress.config(value=done)
                    self.bulk_status.config(text=f"Processing {done}/{total}…")
                    self._append_bulk_row(result)
                elif kind == "bulk_done":
                    self._finish_bulk()
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _finish_bulk(self) -> None:
        self.run_btn.config(state="normal")
        self.load_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        done = len(self._bulk_results)
        if done:
            self.export_btn.config(state="normal")
        stopped = self._stop_flag.is_set()
        self.bulk_status.config(
            text=f"{'Stopped' if stopped else 'Finished'} — {done} row(s) processed. "
                 f"Use Export to save."
        )


def main() -> None:
    root = tk.Tk()
    root.title(f"{APP_TITLE} v{__version__}")
    root.geometry("960x620")
    root.minsize(760, 480)
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    EmailFinderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
