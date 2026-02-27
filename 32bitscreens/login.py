"""
LANFXplorer – Login / Create Profile Page (Tkinter)
Replica of the Flutter LoginPage screen.
Connected to the Flask backend via api_client.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import math
import threading
import sys

from themes import c, set_theme, is_dark, DARK, LIGHT
from landing_page import TroubleshootOverlay

# ── Fallback for running standalone (uses project root for .env) ──────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Lanfxplorer")


# ═════════════════════════════════════════════════════════════════════════════
# Folder-with-person icon  (canvas-drawn)
# ═════════════════════════════════════════════════════════════════════════════

class FolderPersonIcon(tk.Canvas):
    def __init__(self, master, size=72, **kw):
        super().__init__(master, width=size, height=size,
                         highlightthickness=0, bd=0, **kw)
        self._size = size
        self.bind("<Configure>", lambda e: self._draw())
        self.after(10, self._draw)

    def _draw(self):
        self.delete("all")
        s  = self._size
        fg = c("icon_fg")
        bg = c("bg")

        # Folder body
        self.create_rectangle(s*.10, s*.28, s*.40, s*.35,
                              fill=fg, outline="")
        pts = self._rrect(s*.08, s*.33, s*.92, s*.82, s*.06)
        self.create_polygon(pts, fill=fg, outline="", smooth=True)

        # Person silhouette (cutout)
        hr = s * .13
        hx, hy = s*.50, s*.50
        self.create_oval(hx-hr, hy-hr, hx+hr, hy+hr, fill=bg, outline="")
        sr = s * .20
        self.create_arc(hx-sr, hy+s*.04, hx+sr, hy+s*.04+sr*2,
                        start=0, extent=180, fill=bg, outline="", style="chord")

    def _rrect(self, x1, y1, x2, y2, r):
        return [
            x1+r, y1,   x2-r, y1,
            x2,   y1,   x2,   y1+r,
            x2,   y2-r, x2,   y2,
            x2-r, y2,   x1+r, y2,
            x1,   y2,   x1,   y2-r,
            x1,   y1+r, x1,   y1,
        ]

    def set_bg(self, bg):
        self.config(bg=bg)
        self._draw()


# ═════════════════════════════════════════════════════════════════════════════
# Styled input field
# ═════════════════════════════════════════════════════════════════════════════

class InputField(tk.Frame):
    """Outlined field matching the Flutter TextFormField look."""
    def __init__(self, master, label="", icon="", right_cmd=None,
                 right_icon="", password=False, readonly=False,
                 default="", **kw):
        super().__init__(master, bg=c("bg"), **kw)
        self._label     = label
        self._icon_txt  = icon
        self._password  = password
        self._show_pw   = False
        self._readonly  = readonly
        self._right_cmd = right_cmd
        self._right_icon= right_icon
        self._error_msg = None
        self._focused   = False
        self._var       = tk.StringVar(value=default)
        self._build()

    def _build(self):
        self._border = tk.Frame(self, bg=c("field_border"),
                                highlightthickness=0)
        self._border.pack(fill="x")

        inner = tk.Frame(self._border, bg=c("field_bg"))
        inner.pack(fill="x", padx=1, pady=1)
        self._inner = inner

        row = tk.Frame(inner, bg=c("field_bg"))
        row.pack(fill="x")

        if self._icon_txt:
            self._icon_lbl = tk.Label(row, text=self._icon_txt,
                                      font=("Segoe UI", 11),
                                      bg=c("field_bg"), fg=c("subtext"),
                                      padx=10)
            self._icon_lbl.pack(side="left")

        self._entry = tk.Entry(row,
                               textvariable=self._var,
                               font=("Segoe UI", 11),
                               bg=c("field_bg"), fg=c("text"),
                               insertbackground=c("text"),
                               relief="flat", bd=0,
                               highlightthickness=0,
                               state="readonly" if self._readonly else "normal",
                               readonlybackground=c("field_bg"),
                               show="●" if self._password else "")
        self._entry.pack(side="left", fill="x", expand=True, ipady=11)

        if self._right_icon:
            self._right_btn = tk.Button(row,
                                        text=self._right_icon,
                                        font=("Segoe UI", 11),
                                        bg=c("field_bg"), fg=c("subtext"),
                                        activebackground=c("field_bg"),
                                        activeforeground=c("text"),
                                        relief="flat", bd=0,
                                        padx=8, pady=0,
                                        cursor="hand2",
                                        command=self._right_cmd or self._toggle_pw)
            self._right_btn.pack(side="right")

        self._float_lbl = tk.Label(self, text=f" {self._label} ",
                                   font=("Segoe UI", 8),
                                   bg=c("bg"), fg=c("subtext"))
        self._float_lbl.place(x=12, y=-8)

        self._entry.bind("<FocusIn>",  self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)
        if self._readonly and self._right_cmd:
            self._entry.bind("<Button-1>", lambda e: self._right_cmd())

    def _on_focus_in(self, e=None):
        self._focused = True
        self._border.config(bg=c("field_focus"))
        self._float_lbl.config(fg=c("field_focus"))

    def _on_focus_out(self, e=None):
        self._focused = False
        clr = c("field_error") if self._error_msg else c("field_border")
        self._border.config(bg=clr)
        self._float_lbl.config(fg=c("subtext") if not self._error_msg else c("field_error"))

    def _toggle_pw(self):
        self._show_pw = not self._show_pw
        self._entry.config(show="" if self._show_pw else "●")
        if hasattr(self, "_right_btn"):
            self._right_btn.config(fg=c("accent") if self._show_pw else c("subtext"))

    def get(self):
        return self._var.get()

    def set(self, val):
        self._var.set(val)

    def set_error(self, msg):
        self._error_msg = msg
        self._border.config(bg=c("field_error") if msg else c("field_border"))

    def clear_error(self):
        self.set_error(None)

    def focus(self):
        self._entry.focus_set()

    def refresh_theme(self):
        self.config(bg=c("bg"))
        self._border.config(bg=c("field_border"))
        self._inner.config(bg=c("field_bg"))
        for child in self._inner.winfo_children():
            try: child.config(bg=c("field_bg"))
            except: pass
        self._float_lbl.config(bg=c("bg"), fg=c("subtext"))
        self._entry.config(bg=c("field_bg"), fg=c("text"),
                           insertbackground=c("text"),
                           readonlybackground=c("field_bg"))


# ═════════════════════════════════════════════════════════════════════════════
# Error banner
# ═════════════════════════════════════════════════════════════════════════════

class ErrorBanner(tk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master, bg=c("error_bg"),
                         highlightbackground=c("error_border"),
                         highlightthickness=1, **kw)
        row = tk.Frame(self, bg=c("error_bg"))
        row.pack(fill="x", padx=10, pady=8)
        self._icon = tk.Label(row, text="⚠", font=("Segoe UI", 12),
                              bg=c("error_bg"), fg=c("error"))
        self._icon.pack(side="left", padx=(0, 8))
        self._lbl = tk.Label(row, text="", font=("Segoe UI", 9),
                             bg=c("error_bg"), fg=c("text"),
                             anchor="w", justify="left", wraplength=340)
        self._lbl.pack(side="left", fill="x", expand=True)

    def show(self, msg):
        self._lbl.config(text=msg)
        self.pack(fill="x", pady=(6, 0))

    def hide(self):
        self.pack_forget()


# ═════════════════════════════════════════════════════════════════════════════
# Login Page
# ═════════════════════════════════════════════════════════════════════════════

class LoginPage(tk.Frame):
    """
    Full Login/Create-Profile page.
    Accepts navigator and api references for integration.
    """
    def __init__(self, master, navigator=None, api=None, **kw):
        super().__init__(master, bg=c("bg"), **kw)
        self._nav        = navigator
        self._api        = api
        self._is_loading = False
        self._is_checking = True
        self._build()
        # Check for existing credentials after widget is mapped
        self.after(200, self._check_existing_credentials)

    # ── credential check (mirrors Flutter _checkExistingCredentials) ──────
    def _check_existing_credentials(self):
        """If password already exists, auto-navigate to landing page."""
        if not self._api:
            self._is_checking = False
            self._show_form()
            return

        def _bg():
            has_pw = self._api.check_password()
            self.after(0, lambda: self._on_cred_result(has_pw))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_cred_result(self, has_password):
        self._is_checking = False
        if has_password and self._nav:
            self._nav.go("landing")
        else:
            self._show_form()

    def _show_form(self):
        """Show the form – hide loading spinner."""
        if hasattr(self, "_loading_frame"):
            self._loading_frame.destroy()
        if hasattr(self, "_form_canvas"):
            self._form_canvas.pack(side="left", fill="both", expand=True)
            if hasattr(self, "_form_vsb"):
                self._form_vsb.pack(side="right", fill="y")

    # ── build ─────────────────────────────────────────────────────────────
    def _build(self):
        # Loading screen (shown while checking creds)
        self._loading_frame = tk.Frame(self, bg=c("bg"))
        self._loading_frame.pack(fill="both", expand=True)
        fi = FolderPersonIcon(self._loading_frame, size=72, bg=c("bg"))
        fi.pack(expand=True)

        # Form (hidden until creds check completes)
        self._form_canvas = tk.Canvas(self, bg=c("bg"), highlightthickness=0)
        self._form_vsb = ttk.Scrollbar(self, orient="vertical",
                                        command=self._form_canvas.yview)
        self._form_canvas.configure(yscrollcommand=self._form_vsb.set)

        self._col = tk.Frame(self._form_canvas, bg=c("bg"))
        self._col_id = self._form_canvas.create_window(
            (0, 0), window=self._col, anchor="nw")

        self._col.bind("<Configure>", self._on_col_cfg)
        self._form_canvas.bind("<Configure>", self._on_canvas_cfg)
        self._form_canvas.bind_all("<MouseWheel>", self._on_mw)
        self._form_canvas.bind_all("<Button-4>",   self._on_mw)
        self._form_canvas.bind_all("<Button-5>",   self._on_mw)

        self._build_form()

    def _build_form(self):
        col = self._col
        W   = 400

        # ── Logo ──
        self._icon = FolderPersonIcon(col, size=72, bg=c("bg"))
        self._icon.pack(pady=(48, 0))

        # ── Title ──
        tk.Label(col, text="P2P File Share",
                 font=("Segoe UI", 22, "bold"),
                 bg=c("bg"), fg=c("text")).pack(pady=(14, 2))
        tk.Label(col, text="Create your profile to get started",
                 font=("Segoe UI", 10),
                 bg=c("bg"), fg=c("subtext")).pack()

        tk.Frame(col, bg=c("bg"), height=28).pack()

        # ── Fields ──
        fields_outer = tk.Frame(col, bg=c("bg"))
        fields_outer.pack()

        self._f_user = InputField(fields_outer, label="Set Username",
                                  icon="👤", width=W)
        self._f_user.pack(fill="x", pady=(0, 10))

        self._f_pw = InputField(fields_outer, label="Set Password",
                                icon="🔒", password=True,
                                right_icon="👁", width=W)
        self._f_pw.pack(fill="x", pady=(0, 10))

        self._f_cpw = InputField(fields_outer, label="Confirm Password",
                                 icon="🔒", password=True,
                                 right_icon="👁", width=W)
        self._f_cpw.pack(fill="x", pady=(0, 10))

        self._f_dir = InputField(fields_outer,
                                 label="Select Default Directory",
                                 icon="📁", right_icon="📂",
                                 readonly=True,
                                 right_cmd=self._browse_dir,
                                 default=DEFAULT_DIR, width=W)
        self._f_dir.pack(fill="x")

        self._err_banner = ErrorBanner(fields_outer)

        tk.Frame(col, bg=c("bg"), height=22).pack()

        # ── Create Profile ──
        self._create_btn = tk.Button(col,
                                     text="Create Profile",
                                     command=self._create_profile,
                                     font=("Segoe UI", 11, "bold"),
                                     bg=c("accent"), fg=c("accent_fg"),
                                     activebackground="#2255bb",
                                     activeforeground="#ffffff",
                                     relief="flat", bd=0,
                                     pady=13, cursor="hand2", width=38)
        self._create_btn.pack(fill="x", padx=0, pady=(0, 8))

        # ── Use Default Values ──
        self._default_btn = tk.Button(col,
                                      text="Use Default Values",
                                      command=self._use_defaults,
                                      font=("Segoe UI", 10),
                                      bg=c("field_bg"),
                                      fg=c("btn_outline_fg"),
                                      activebackground=c("field_border"),
                                      activeforeground=c("text"),
                                      relief="flat", bd=0,
                                      pady=12, cursor="hand2",
                                      highlightbackground=c("btn_outline"),
                                      highlightthickness=1, width=38)
        self._default_btn.pack(fill="x", pady=(0, 0))

        # ── Troubleshoot divider ──
        tk.Frame(col, bg=c("bg"), height=22).pack()

        div_row = tk.Frame(col, bg=c("bg"))
        div_row.pack(fill="x")
        tk.Frame(div_row, bg=c("divider"), height=1).pack(
            side="left", fill="x", expand=True, pady=8)
        tk.Label(div_row, text="  Troubleshoot  ",
                 font=("Segoe UI", 8),
                 bg=c("bg"), fg=c("subtext")).pack(side="left")
        tk.Frame(div_row, bg=c("divider"), height=1).pack(
            side="left", fill="x", expand=True, pady=8)

        tk.Frame(col, bg=c("bg"), height=10).pack()

        # ── Reset Environment ──
        self._reset_btn = tk.Button(col,
                                    text="↺  Reset Environment",
                                    command=self._reset_env,
                                    font=("Segoe UI", 10),
                                    bg=c("bg"), fg=c("error"),
                                    activebackground=c("error_bg"),
                                    activeforeground=c("error"),
                                    relief="flat", bd=0,
                                    pady=12, cursor="hand2",
                                    highlightbackground=c("error"),
                                    highlightthickness=1, width=38)
        self._reset_btn.pack(fill="x")

        tk.Frame(col, bg=c("bg"), height=8).pack()

        # ── Troubleshoot Connection ──
        self._troubleshoot_btn = tk.Button(col,
                                    text="🔧  Troubleshoot Connection",
                                    command=self._show_troubleshoot,
                                    font=("Segoe UI", 10),
                                    bg=c("bg"), fg=c("accent"),
                                    activebackground=c("field_bg"),
                                    activeforeground=c("accent"),
                                    relief="flat", bd=0,
                                    pady=12, cursor="hand2",
                                    highlightbackground=c("accent"),
                                    highlightthickness=1, width=38)
        self._troubleshoot_btn.pack(fill="x")

        tk.Frame(col, bg=c("bg"), height=40).pack()

        self.after(50, self._reflow)

    # ── scroll / layout helpers ───────────────────────────────────────────
    def _on_col_cfg(self, event):
        self._form_canvas.configure(scrollregion=self._form_canvas.bbox("all"))

    def _on_canvas_cfg(self, event):
        self._reflow()

    def _reflow(self, *_):
        cw = self._form_canvas.winfo_width()
        col_w = max(400, min(460, cw - 40))
        x = max(0, (cw - col_w) // 2)
        self._form_canvas.itemconfig(self._col_id, width=col_w)
        self._form_canvas.coords(self._col_id, x, 0)

    def _on_mw(self, event):
        if event.num == 4:
            self._form_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._form_canvas.yview_scroll(1, "units")
        elif hasattr(event, "delta"):
            self._form_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    # ── actions ───────────────────────────────────────────────────────────
    def _browse_dir(self):
        path = filedialog.askdirectory(
            initialdir=os.path.expanduser("~"),
            title="Select Default Directory")
        if path:
            lanfx_root = os.path.join(os.path.expanduser("~"), "Lanfxplorer")
            if path == lanfx_root or path.startswith(lanfx_root + os.sep):
                self._f_dir.set(path)
                self._f_dir.clear_error()
                self._err_banner.hide()
            else:
                msg = (f"Access denied! You can only select directories "
                       f"within:\n{lanfx_root}\n\n"
                       f"Please create this folder if it doesn't exist.")
                self._f_dir.set_error(msg)
                self._err_banner.show(msg)

    def _validate(self):
        ok = True
        self._f_user.clear_error()
        self._f_pw.clear_error()
        self._f_cpw.clear_error()
        self._f_dir.clear_error()

        if not self._f_user.get().strip():
            self._f_user.set_error("Required")
            ok = False

        pw = self._f_pw.get()
        if not pw:
            self._f_pw.set_error("Required")
            ok = False
        elif len(pw) < 4:
            self._f_pw.set_error("At least 4 characters")
            ok = False

        if self._f_cpw.get() != pw:
            self._f_cpw.set_error("Passwords do not match")
            ok = False

        if not self._f_dir.get():
            self._f_dir.set_error("Required")
            ok = False

        return ok

    def _create_profile(self):
        if not self._validate():
            return
        self._set_loading(True)

        username = self._f_user.get().strip()
        password = self._f_pw.get()
        outdir   = self._f_dir.get()

        def _bg():
            try:
                # 1. Write to .env
                self._write_env(username, password, outdir)
                # 2. Store password in OS keyring
                if self._api:
                    self._api.set_password(password)
                self.after(0, self._on_created)
            except Exception as e:
                self.after(0, lambda: self._on_error(str(e)))

        threading.Thread(target=_bg, daemon=True).start()

    def _write_env(self, username, password, outdir):
        """Update USER, PASSWORD, OUTDIR in the project .env file."""
        env_path = os.path.join(_PROJECT_ROOT, ".env")
        lines = []
        if os.path.isfile(env_path):
            with open(env_path, "r") as f:
                lines = f.read().splitlines()

        found_pw = found_out = found_user = False
        new_lines = []
        for line in lines:
            if line.startswith("PASSWORD="):
                new_lines.append(f"PASSWORD={password}")
                found_pw = True
            elif line.startswith("OUTDIR="):
                new_lines.append(f"OUTDIR={outdir}")
                found_out = True
            elif line.startswith("USER="):
                new_lines.append(f"USER={username}")
                found_user = True
            else:
                new_lines.append(line)

        if not found_pw:   new_lines.append(f"PASSWORD={password}")
        if not found_out:  new_lines.append(f"OUTDIR={outdir}")
        if not found_user: new_lines.append(f"USER={username}")

        with open(env_path, "w") as f:
            f.write("\n".join(new_lines) + "\n")

    def _on_created(self):
        self._set_loading(False)
        self._toast("Profile created! Navigating to home…", ok=True)
        if self._nav:
            self.after(600, lambda: self._nav.go("landing"))

    def _on_error(self, msg):
        self._set_loading(False)
        self._err_banner.show(f"Error: {msg}")

    def _use_defaults(self):
        user = os.environ.get("USER", os.environ.get("USERNAME", "user"))
        self._f_user.set(user)
        self._f_pw.set("password")
        self._f_cpw.set("password")
        self._f_dir.set(DEFAULT_DIR)
        self._err_banner.hide()
        self._create_profile()

    def _reset_env(self):
        confirmed = messagebox.askyesno(
            "Reset Environment",
            "This will delete all certificates and clear network "
            "configurations.\n\nThe app will restart with a fresh setup.",
            icon="warning")
        if not confirmed:
            return

        if self._api:
            def _bg():
                ok = self._api.reset_environment()
                self.after(0, lambda: self._on_reset_done(ok))
            self._set_loading(True)
            threading.Thread(target=_bg, daemon=True).start()
        else:
            self._toast("Environment reset (stub).")

    def _on_reset_done(self, ok):
        self._set_loading(False)
        if ok:
            self._toast("Environment reset. Restarting\u2026")
            self.after(800, lambda: sys.exit(0))
        else:
            self._err_banner.show("Reset failed. Please try again.")

    def _show_troubleshoot(self):
        TroubleshootOverlay(self)

    def _set_loading(self, loading):
        self._is_loading = loading
        state = "disabled" if loading else "normal"
        txt   = "Creating…" if loading else "Create Profile"
        self._create_btn.config(state=state, text=txt)
        self._default_btn.config(state=state)
        self._reset_btn.config(state=state)

    def _toast(self, msg, ok=False):
        root = self.winfo_toplevel()
        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=c("field_bg"))
        color = c("accent") if ok else c("subtext")
        tk.Label(win, text=msg,
                 font=("Segoe UI", 10),
                 bg=c("field_bg"), fg=color,
                 padx=20, pady=12).pack()
        rx = root.winfo_rootx() + root.winfo_width()  // 2 - 160
        ry = root.winfo_rooty() + root.winfo_height() - 80
        win.geometry(f"+{rx}+{ry}")
        win.after(1800, win.destroy)

    def refresh_theme(self):
        self.config(bg=c("bg"))
        if hasattr(self, "_form_canvas"):
            self._form_canvas.config(bg=c("bg"))
        self._col.config(bg=c("bg"))
        self._icon.set_bg(c("bg"))
        for w in self._col.winfo_children():
            try: w.config(bg=c("bg"))
            except: pass
        self._f_user.refresh_theme()
        self._f_pw.refresh_theme()
        self._f_cpw.refresh_theme()
        self._f_dir.refresh_theme()
        self._create_btn.config(bg=c("accent"), fg=c("accent_fg"))
        self._default_btn.config(bg=c("field_bg"), fg=c("btn_outline_fg"),
                                  highlightbackground=c("btn_outline"))
        self._reset_btn.config(bg=c("bg"), fg=c("error"),
                                highlightbackground=c("error"),
                                activebackground=c("error_bg"))