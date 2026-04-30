#!/usr/bin/env python3
"""
LANFXplorer Installer GUI  — Windows Edition
Runs install.bat and streams output in real-time.
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import threading
import os
import sys
import re
from pathlib import Path

# ── Base directory (works both as .py and PyInstaller .exe) ───────────────────
# When frozen by PyInstaller, __file__ points to a temp _MEI* extraction folder.
# sys.executable always points to the actual .exe on disk.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

# ── Palette ────────────────────────────────────────────────────────────────────
BG          = "#0d1117"
BG2         = "#161b22"
BG3         = "#1c2330"
BORDER      = "#30363d"
ACCENT      = "#d45500"
ACCENT_DIM  = "#be5712"
RED         = "#d10404"
YELLOW      = "#f3970c"
WHITE       = "#e6edf3"
MUTED       = "#8b949e"
SUCCESS     = "#29db41"
FONT_MONO   = ("Courier New", 10)
FONT_UI     = ("Segoe UI", 10)
FONT_TITLE  = ("Segoe UI", 18, "bold")


# ── Steps matched exactly to install.bat echo lines ───────────────────────────
STEPS = [
    ("Checking Python",         r"Checking for system Python"),
    ("Installing Python",       r"(Python found|Downloading Python|Launching Python installer|Using Python|Installer closed)"),
    ("Upgrading pip",           r"(Installing Python dep|pip upgrade complete)"),
    ("Installing dependencies", r"(Dependencies installation complete|Verifying cryptography)"),
    ("Configuring firewall",    r"(Configuring Windows Firewall|Firewall rules configured|Firewall configuration)"),
    ("Creating shortcut",       r"(Creating desktop shortcut|Installation completed successfully|Launching LANFXplorer)"),
]


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LANFXplorer Installer")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(780, 580)
        self._center(900, 660)

        self._process = None
        self._running = False
        self._step_labels = []

        self._build_ui()

    # ── Layout ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG, pady=18)
        hdr.pack(fill="x", padx=30)

        dot = tk.Canvas(hdr, width=14, height=14, bg=BG, highlightthickness=0)
        dot.create_oval(0, 0, 14, 14, fill=ACCENT, outline="")
        dot.pack(side="left", padx=(0, 10), pady=4)

        tk.Label(hdr, text="LANFXplorer", font=FONT_TITLE,
                 fg=WHITE, bg=BG).pack(side="left")
        tk.Label(hdr, text=" — Installer", font=(FONT_UI[0], 14),
                 fg=MUTED, bg=BG).pack(side="left", pady=3)

        tk.Frame(self, height=1, bg=BORDER).pack(fill="x")

        # Body
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # Sidebar
        sidebar = tk.Frame(body, bg=BG2, width=220, padx=16, pady=20)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="INSTALL STEPS", font=(FONT_UI[0], 8, "bold"),
                 fg=MUTED, bg=BG2, anchor="w").pack(fill="x", pady=(0, 12))

        for i, (label, _) in enumerate(STEPS):
            row = tk.Frame(sidebar, bg=BG2)
            row.pack(fill="x", pady=3)

            icon = tk.Label(row, text="○", font=(FONT_UI[0], 11),
                            fg=BORDER, bg=BG2, width=2)
            icon.pack(side="left")
            lbl = tk.Label(row, text=label, font=(FONT_UI[0], 9),
                           fg=MUTED, bg=BG2, anchor="w", wraplength=160)
            lbl.pack(side="left", fill="x", expand=True)
            self._step_labels.append((icon, lbl))

        # Log panel
        log_frame = tk.Frame(body, bg=BG)
        log_frame.pack(side="left", fill="both", expand=True, padx=(1, 0))

        tk.Frame(log_frame, height=1, bg=BORDER).pack(fill="x")

        toolbar = tk.Frame(log_frame, bg=BG3, pady=6, padx=12)
        toolbar.pack(fill="x")
        tk.Label(toolbar, text="OUTPUT LOG", font=(FONT_UI[0], 8, "bold"),
                 fg=MUTED, bg=BG3).pack(side="left")
        self._status_dot = tk.Canvas(toolbar, width=10, height=10,
                                     bg=BG3, highlightthickness=0)
        self._status_dot.pack(side="right", padx=(0, 6))
        self._status_lbl = tk.Label(toolbar, text="Ready", font=(FONT_UI[0], 8),
                                    fg=MUTED, bg=BG3)
        self._status_lbl.pack(side="right")

        self._log = scrolledtext.ScrolledText(
            log_frame, bg=BG, fg=WHITE, font=FONT_MONO,
            insertbackground=ACCENT, relief="flat", bd=0,
            selectbackground=BG3, wrap="word", padx=14, pady=10,
            state="disabled"
        )
        self._log.pack(fill="both", expand=True)

        for tag, color in [("ok", SUCCESS), ("fail", RED), ("warn", YELLOW),
                            ("info", ACCENT), ("muted", MUTED)]:
            self._log.tag_config(tag, foreground=color)

        # Bottom bar
        tk.Frame(self, height=1, bg=BORDER).pack(fill="x")
        bar = tk.Frame(self, bg=BG2, pady=12, padx=20)
        bar.pack(fill="x")

        self._progress_canvas = tk.Canvas(bar, height=4, bg=BG3, highlightthickness=0)
        self._progress_canvas.pack(fill="x", pady=(0, 10))
        self._progress_canvas.bind("<Configure>", self._redraw_progress)
        self._progress_pct = 0.0

        btn_frame = tk.Frame(bar, bg=BG2)
        btn_frame.pack(fill="x")

        self._install_btn = tk.Button(
            btn_frame, text="▶  Start Installation",
            font=(FONT_UI[0], 10, "bold"),
            bg=ACCENT, fg="#000000", activebackground=ACCENT_DIM,
            activeforeground="#000000", relief="flat", cursor="hand2",
            padx=20, pady=8, command=self._start_install
        )
        self._install_btn.pack(side="left")

        self._cancel_btn = tk.Button(
            btn_frame, text="✕  Cancel",
            font=FONT_UI, bg=BG3, fg=MUTED,
            activebackground=BORDER, activeforeground=WHITE,
            relief="flat", cursor="hand2", padx=16, pady=8,
            command=self._cancel, state="disabled"
        )
        self._cancel_btn.pack(side="left", padx=(8, 0))

        tk.Label(btn_frame, text=f"Path: {BASE_DIR}",
                 font=(FONT_UI[0], 8), fg=MUTED, bg=BG2).pack(side="right")

    # ── Progress bar ────────────────────────────────────────────────────────────
    def _redraw_progress(self, event=None):
        c = self._progress_canvas
        c.delete("all")
        w = c.winfo_width()
        filled = int(w * self._progress_pct / 100)
        c.create_rectangle(0, 0, w, 4, fill=BG3, outline="")
        if filled > 0:
            c.create_rectangle(0, 0, filled, 4, fill=ACCENT, outline="")

    def _set_progress(self, pct: float):
        self._progress_pct = pct
        self._redraw_progress()

    # ── Logging ─────────────────────────────────────────────────────────────────
    def _log_line(self, line: str):
        line = strip_ansi(line).rstrip()
        if not line:
            return

        tag = "muted"
        if re.search(r"\[OK\]|completed successfully", line, re.I):
            tag = "ok"
        elif re.search(r"\[ERROR\]|FATAL", line, re.I):
            tag = "fail"
        elif re.search(r"\[WARNING\]|\[!\]|may not be installed", line, re.I):
            tag = "warn"
        elif re.search(r"\[+\]|={10,}|IMPORTANT", line):
            tag = "info"

        self._log.configure(state="normal")
        self._log.insert("end", line + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")

        # Advance step tracker
        for i, (_, pattern) in enumerate(STEPS):
            if re.search(pattern, line, re.I):
                self._mark_step(i, "running")
                if i > 0:
                    self._mark_step(i - 1, "done")
                self._set_progress((i / len(STEPS)) * 100)
                break

    def _mark_step(self, idx: int, state: str):
        if idx >= len(self._step_labels):
            return
        icon_lbl, text_lbl = self._step_labels[idx]
        if state == "done":
            icon_lbl.config(text="✓", fg=SUCCESS)
            text_lbl.config(fg=WHITE)
        elif state == "running":
            icon_lbl.config(text="►", fg=ACCENT)
            text_lbl.config(fg=ACCENT)
        elif state == "fail":
            icon_lbl.config(text="✗", fg=RED)
            text_lbl.config(fg=RED)

    def _set_status(self, text: str, color: str = MUTED):
        self._status_dot.delete("all")
        self._status_dot.create_oval(0, 0, 10, 10, fill=color, outline="")
        self._status_lbl.config(text=text, fg=color)

    # ── Install logic ────────────────────────────────────────────────────────────
    def _start_install(self):
        script = BASE_DIR / "install.bat"
        if not script.exists():
            messagebox.showerror(
                "Script not found",
                f"install.bat not found in:\n{script.parent}\n\n"
                "Place this GUI file in the same folder as install.bat."
            )
            return

        self._install_btn.config(state="disabled")
        self._cancel_btn.config(state="normal")
        self._running = True
        self._set_status("Installing…", ACCENT)

        threading.Thread(target=self._run_script,
                         args=(str(script),), daemon=True).start()

    def _run_script(self, script_path: str):
        try:
            # CREATE_NO_WINDOW: don't spawn a second visible console
            CREATE_NO_WINDOW = 0x08000000

            self._process = subprocess.Popen(
                ["cmd.exe", "/c", script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=str(Path(script_path).parent),
                creationflags=CREATE_NO_WINDOW,
            )

            for line in iter(self._process.stdout.readline, ""):
                if not self._running:
                    break
                self.after(0, self._log_line, line)

            self._process.stdout.close()
            ret = self._process.wait()
            self.after(0, self._on_finish, ret)

        except Exception as exc:
            self.after(0, self._log_line, f"[ERROR] GUI error: {exc}")
            self.after(0, self._on_finish, 1)

    def _on_finish(self, returncode: int):
        self._running = False
        self._install_btn.config(state="normal", text="↺  Re-run")
        self._cancel_btn.config(state="disabled")

        if returncode == 0:
            for i in range(len(STEPS)):
                self._mark_step(i, "done")
            self._set_progress(100)
            self._set_status("Complete", SUCCESS)
            self._log_line("\n[OK] Installation finished successfully!")
            messagebox.showinfo(
                "Done",
                "LANFXplorer installed successfully!\n\n"
                "A desktop shortcut has been created.\n"
                "LANFXplorer is now launching."
            )
        else:
            self._set_status(f"Failed (exit {returncode})", RED)
            self._log_line(f"\n[ERROR] Installation failed with exit code {returncode}.")
            for i, (icon, _) in enumerate(self._step_labels):
                if icon.cget("text") == "►":
                    self._mark_step(i, "fail")
                    break

    def _cancel(self):
        if self._process and self._running:
            self._running = False
            try:
                # Kill entire process tree (cmd.exe + child processes like installers)
                subprocess.call(
                    ["taskkill", "/F", "/T", "/PID", str(self._process.pid)],
                    creationflags=0x08000000
                )
            except Exception:
                pass
            self._set_status("Cancelled", YELLOW)
            self._log_line("\n[!] Installation cancelled by user.")
            self._install_btn.config(state="normal", text="▶  Start Installation")
            self._cancel_btn.config(state="disabled")

    # ── Helpers ──────────────────────────────────────────────────────────────────
    def _center(self, w: int, h: int):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")


if __name__ == "__main__":
    app = InstallerApp()
    app.mainloop()