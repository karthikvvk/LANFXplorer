"""
LANFXplorer – Landing Page (Tkinter)
Replica of the Flutter LandingPage screen.
Connected to the Flask backend via api_client.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import math
import os
import sys
import subprocess
import threading

from themes import c, set_theme, is_dark, DARK, LIGHT

_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── .env loader (lightweight) ────────────────────────────────────────────────
def _load_env():
    """Read .env from project root into a dict."""
    env = {}
    env_path = os.path.join(_PROJECT_ROOT, ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip().strip("'\"")
    return env


def _write_env_key(key, value):
    """Set a single key in .env (add or update)."""
    env_path = os.path.join(_PROJECT_ROOT, ".env")
    lines = []
    if os.path.isfile(env_path):
        with open(env_path) as f:
            lines = f.read().splitlines()
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    with open(env_path, "w") as f:
        f.write("\n".join(new_lines) + "\n")


def _remove_env_key(key):
    """Remove a key from .env."""
    env_path = os.path.join(_PROJECT_ROOT, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path) as f:
        lines = f.read().splitlines()
    with open(env_path, "w") as f:
        f.write("\n".join(l for l in lines if not l.startswith(f"{key}=")) + "\n")


# ═════════════════════════════════════════════════════════════════════════════
# Laptop icon drawn on a Canvas
# ═════════════════════════════════════════════════════════════════════════════

class LaptopIcon(tk.Canvas):
    """Vector-drawn laptop icon, similar to Icons.laptop_mac."""
    def __init__(self, master, size=52, fg=None, bg=None, **kw):
        self._size = size
        self._fg   = fg or c("icon_fg")
        self._bg_c = bg or c("card_bg")
        super().__init__(master, width=size, height=size,
                         bg=self._bg_c, highlightthickness=0, bd=0, **kw)
        self.bind("<Configure>", self._draw)
        self.after(10, self._draw)

    def _draw(self, event=None):
        self.delete("all")
        s  = self._size
        m  = s * 0.08
        sx1, sy1 = m,       m
        sx2, sy2 = s - m,   s * 0.68
        r = s * 0.06
        self._rounded_rect(sx1, sy1, sx2, sy2, r, outline=self._fg,
                           width=max(1, int(s*0.045)))
        p = s * 0.06
        self._rounded_rect(sx1+p, sy1+p, sx2-p, sy2-p*0.5,
                           r*0.5, fill=self._fg, outline="")
        bx1, by1 = m * 0.3,  s * 0.70
        bx2, by2 = s - m*0.3, s * 0.78
        self.create_rectangle(bx1, by1, bx2, by2, fill=self._fg, outline="")
        bw = s * 0.40
        cx = s / 2
        pts = [cx-bw*0.6, by2, cx-bw, s-m*0.4,
               cx+bw,     s-m*0.4, cx+bw*0.6, by2]
        self.create_polygon(pts, fill=self._fg, outline="")
        nr = s * 0.025
        nx, ny = s/2, sy2 - s*0.04
        self.create_oval(nx-nr, ny-nr, nx+nr, ny+nr,
                         fill=self._bg_c, outline="")

    def _rounded_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [
            x1+r, y1,   x2-r, y1,
            x2,   y1,   x2,   y1+r,
            x2,   y2-r, x2,   y2,
            x2-r, y2,   x1+r, y2,
            x1,   y2,   x1,   y2-r,
            x1,   y1+r, x1,   y1,
        ]
        return self.create_polygon(pts, smooth=True, **kw)

    def set_colors(self, fg, bg):
        self._fg   = fg
        self._bg_c = bg
        self.config(bg=bg)
        self._draw()


# ═════════════════════════════════════════════════════════════════════════════
# Machine Card
# ═════════════════════════════════════════════════════════════════════════════

class MachineCard(tk.Frame):
    """Rounded card with laptop icon, username, IP, status."""
    CARD_W = 230
    CARD_H = 230

    def __init__(self, master, machine: dict, on_tap=None, **kw):
        super().__init__(master,
                         bg=c("card_bg"),
                         width=self.CARD_W, height=self.CARD_H,
                         cursor="hand2", **kw)
        self.pack_propagate(False)
        self._machine = machine
        self._on_tap  = on_tap
        self._build()
        self._bind_hover(self)

    def _build(self):
        self._canvas = tk.Canvas(self, bg=c("bg"),
                                 highlightthickness=0, bd=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.bind("<Configure>", self._draw_card)
        self._canvas.bind("<Button-1>",
                          lambda e: self._on_tap and self._on_tap(self._machine))
        self.after(20, self._draw_card)

        self._inner = tk.Frame(self._canvas, bg=c("card_bg"))
        self._canvas.create_window(self.CARD_W//2, self.CARD_H//2,
                                   window=self._inner, anchor="center")

        self._icon = LaptopIcon(self._inner, size=68,
                                fg=c("icon_fg"), bg=c("card_bg"))
        self._icon.pack(pady=(0, 10))

        self._name_lbl = tk.Label(self._inner,
                                  text=self._machine.get("username", ""),
                                  font=("Segoe UI", 11, "bold"),
                                  bg=c("card_bg"), fg=c("text"))
        self._name_lbl.pack()

        self._ip_lbl = tk.Label(self._inner,
                                text=self._machine.get("ip", ""),
                                font=("Segoe UI", 9),
                                bg=c("card_bg"), fg=c("subtext"))
        self._ip_lbl.pack()

        status = self._machine.get("status", "Online")
        status_color = c("online") if status == "Online" else c("offline")
        self._status_lbl = tk.Label(self._inner,
                                    text=status,
                                    font=("Segoe UI", 9),
                                    bg=c("card_bg"), fg=status_color)
        self._status_lbl.pack(pady=(4, 0))

        self._bind_hover(self._canvas)
        self._bind_hover(self._inner)
        for child in self._inner.winfo_children():
            self._bind_hover(child)

    def _bind_hover(self, widget):
        widget.bind("<Enter>",    lambda e: self._on_enter())
        widget.bind("<Leave>",    lambda e: self._on_leave())
        widget.bind("<Button-1>",
                    lambda e: self._on_tap and self._on_tap(self._machine))

    def _draw_card(self, event=None):
        self._canvas.delete("border")
        w = self._canvas.winfo_width()  or self.CARD_W
        h = self._canvas.winfo_height() or self.CARD_H
        r = 14
        self._draw_rounded_rect(2, 2, w-2, h-2, r,
                                fill=c("card_bg"),
                                outline=self._border_color(),
                                width=1, tag="border")

    def _border_color(self):
        return (self._hover_border
                if hasattr(self, "_hover_border") else c("card_border"))

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, tag="", **kw):
        pts = [
            x1+r, y1,   x2-r, y1,
            x2,   y1,   x2,   y1+r,
            x2,   y2-r, x2,   y2,
            x2-r, y2,   x1+r, y2,
            x1,   y2,   x1,   y2-r,
            x1,   y1+r, x1,   y1,
        ]
        return self._canvas.create_polygon(pts, smooth=True,
                                           tags=(tag,), **kw)

    def _on_enter(self):
        self._hover_border = c("accent")
        self._draw_card()
        self.config(bg=c("card_hover"))
        self._inner.config(bg=c("card_hover"))
        self._icon.set_colors(c("icon_fg"), c("card_hover"))
        for child in self._inner.winfo_children():
            try: child.config(bg=c("card_hover"))
            except: pass

    def _on_leave(self):
        self._hover_border = c("card_border")
        self._draw_card()
        self.config(bg=c("card_bg"))
        self._inner.config(bg=c("card_bg"))
        self._icon.set_colors(c("icon_fg"), c("card_bg"))
        for child in self._inner.winfo_children():
            try: child.config(bg=c("card_bg"))
            except: pass

    def refresh_theme(self):
        self._hover_border = c("card_border")
        self._canvas.config(bg=c("bg"))
        self._draw_card()
        self.config(bg=c("card_bg"))
        self._inner.config(bg=c("card_bg"))
        self._icon.set_colors(c("icon_fg"), c("card_bg"))
        self._name_lbl.config(bg=c("card_bg"), fg=c("text"))
        self._ip_lbl.config(bg=c("card_bg"), fg=c("subtext"))
        status = self._machine.get("status", "Online")
        self._status_lbl.config(
            bg=c("card_bg"),
            fg=c("online") if status == "Online" else c("offline"))


# ═════════════════════════════════════════════════════════════════════════════
# Scanning animation overlay
# ═════════════════════════════════════════════════════════════════════════════

class ScanningOverlay(tk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master, bg=c("bg"), **kw)
        self._dot_phase = 0
        self._running   = False
        self._build()

    def _build(self):
        inner = tk.Frame(self, bg=c("bg"))
        inner.place(relx=0.5, rely=0.45, anchor="center")

        self._dots_canvas = tk.Canvas(inner, width=48, height=48,
                                      bg=c("bg"), highlightthickness=0)
        self._dots_canvas.pack()

        self._spin_lbl = tk.Label(inner,
                                  text="Scanning for devices…",
                                  font=("Segoe UI", 13),
                                  bg=c("bg"), fg=c("subtext"))
        self._spin_lbl.pack(pady=(16, 0))

    def start(self):
        self._running = True
        self._tick()

    def stop(self):
        self._running = False

    def _tick(self):
        if not self._running:
            return
        self._dot_phase = (self._dot_phase + 1) % 60
        self._draw_spinner()
        self.after(30, self._tick)

    def _draw_spinner(self):
        cv = self._dots_canvas
        cv.delete("all")
        cx, cy, r = 24, 24, 16
        n = 8
        for i in range(n):
            angle = math.radians(360 / n * i - self._dot_phase * 6)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            alpha = 1.0 - (i / n) * 0.85
            clr = self._alpha_color(c("scan_dot"), alpha)
            dr = 3.5
            cv.create_oval(x-dr, y-dr, x+dr, y+dr, fill=clr, outline="")

    @staticmethod
    def _alpha_color(hex_color, alpha):
        bg = (0x18, 0x18, 0x1a)
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        r2 = int(r * alpha + bg[0] * (1 - alpha))
        g2 = int(g * alpha + bg[1] * (1 - alpha))
        b2 = int(b * alpha + bg[2] * (1 - alpha))
        return f"#{r2:02x}{g2:02x}{b2:02x}"

    def refresh_theme(self):
        self.config(bg=c("bg"))
        self._spin_lbl.config(bg=c("bg"), fg=c("subtext"))
        self._dots_canvas.config(bg=c("bg"))


# ═════════════════════════════════════════════════════════════════════════════
# Empty state
# ═════════════════════════════════════════════════════════════════════════════

class EmptyState(tk.Frame):
    def __init__(self, master, on_rescan, on_troubleshoot=None, **kw):
        super().__init__(master, bg=c("bg"), **kw)
        self._on_rescan = on_rescan
        self._on_troubleshoot = on_troubleshoot
        self._build()

    def _build(self):
        inner = tk.Frame(self, bg=c("bg"))
        inner.place(relx=0.5, rely=0.4, anchor="center")

        tk.Label(inner, text="⊡", font=("Segoe UI", 48),
                 bg=c("bg"), fg=c("subtext")).pack()

        # ── "No devices found" + Troubleshoot button on the same row ──
        row = tk.Frame(inner, bg=c("bg"))
        row.pack(pady=(12, 4))

        tk.Label(row, text="No devices found",
                 font=("Segoe UI", 15, "bold"),
                 bg=c("bg"), fg=c("text")).pack(side="left")

        if self._on_troubleshoot:
            tk.Button(row, text="🔧 Troubleshoot",
                      command=self._on_troubleshoot,
                      bg=c("bg"), fg=c("subtext"),
                      activebackground=c("card_hover"),
                      activeforeground=c("text"),
                      relief="flat", bd=0,
                      padx=8, pady=0,
                      font=("Segoe UI", 9),
                      cursor="hand2").pack(side="left", padx=(10, 0))

        tk.Label(inner,
                 text="Make sure other devices are\nconnected to the same network",
                 font=("Segoe UI", 10),
                 bg=c("bg"), fg=c("subtext"),
                 justify="center").pack()

        btn = tk.Button(inner, text="⟳  Scan Again",
                        command=self._on_rescan,
                        bg=c("bg"), fg=c("accent"),
                        activebackground=c("card_hover"),
                        activeforeground=c("accent"),
                        relief="solid", bd=1,
                        highlightbackground=c("accent"),
                        highlightthickness=1,
                        padx=14, pady=7,
                        font=("Segoe UI", 10),
                        cursor="hand2")
        btn.pack(pady=(20, 0))


# ═════════════════════════════════════════════════════════════════════════════
# Machine Grid
# ═════════════════════════════════════════════════════════════════════════════

class MachineGrid(tk.Frame):
    """Responsive grid of MachineCards inside a scrollable canvas."""
    PAD  = 20
    GAP  = 16
    CARD_W = MachineCard.CARD_W
    CARD_H = MachineCard.CARD_H

    def __init__(self, master, machines, on_select=None, **kw):
        super().__init__(master, bg=c("bg"), **kw)
        self._machines   = machines
        self._on_select  = on_select
        self._cards      = []
        self._build()

    def _build(self):
        self._canvas = tk.Canvas(self, bg=c("bg"),
                                 highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(self, orient="vertical",
                            command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)

        self._canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._inner = tk.Frame(self._canvas, bg=c("bg"))
        self._win_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>", self._on_inner_cfg)
        self._canvas.bind("<Configure>", self._on_canvas_cfg)

        self._canvas.bind_all("<MouseWheel>",     self._on_mousewheel)
        self._canvas.bind_all("<Button-4>",       self._on_mousewheel)
        self._canvas.bind_all("<Button-5>",       self._on_mousewheel)

        self._place_cards()

    def _place_cards(self):
        for card in self._cards:
            card.destroy()
        self._cards.clear()

        self._canvas.update_idletasks()
        avail = self._canvas.winfo_width() or 900
        cols = max(1, (avail - self.PAD) // (self.CARD_W + self.GAP))

        for i, machine in enumerate(self._machines):
            row = i // cols
            col_idx = i % cols
            x = self.PAD + col_idx * (self.CARD_W + self.GAP)
            y = self.PAD + row * (self.CARD_H + self.GAP)

            card = MachineCard(self._inner, machine=machine,
                               on_tap=self._on_select)
            card.place(x=x, y=y, width=self.CARD_W, height=self.CARD_H)
            self._cards.append(card)

        if self._machines:
            rows = math.ceil(len(self._machines) / cols)
            inner_h = self.PAD + rows * (self.CARD_H + self.GAP)
            inner_w = self.PAD + cols * (self.CARD_W + self.GAP)
            self._inner.config(width=inner_w, height=inner_h)

    def _on_inner_cfg(self, event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_cfg(self, event):
        self._canvas.itemconfig(self._win_id, width=event.width)
        self._place_cards()

    def _on_mousewheel(self, event):
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def refresh_theme(self):
        self.config(bg=c("bg"))
        self._canvas.config(bg=c("bg"))
        self._inner.config(bg=c("bg"))
        for card in self._cards:
            card.refresh_theme()


# ═════════════════════════════════════════════════════════════════════════════
# Header
# ═════════════════════════════════════════════════════════════════════════════

class LandingHeader(tk.Frame):
    def __init__(self, master, app_ref, current_user="", current_ip="", **kw):
        super().__init__(master, bg=c("header"), **kw)
        self._app = app_ref
        self._username = current_user
        self._ip = current_ip
        self._build()

    def _build(self):
        # ── Computer icon ──
        icon_canvas = tk.Canvas(self, width=36, height=36,
                                bg=c("header"), highlightthickness=0)
        icon_canvas.pack(side="left", padx=(14, 0), pady=8)
        self._draw_monitor(icon_canvas)

        # ── Labels ──
        info = tk.Frame(self, bg=c("header"))
        info.pack(side="left", padx=10, pady=6)

        tk.Label(info, text="Current Machine",
                 font=("Segoe UI", 8),
                 bg=c("header"), fg=c("subtext"),
                 anchor="w").pack(fill="x")
        self._user_lbl = tk.Label(info, text=self._username,
                 font=("Segoe UI", 11, "bold"),
                 bg=c("header"), fg=c("text"),
                 anchor="w")
        self._user_lbl.pack(fill="x")
        self._ip_lbl = tk.Label(info, text=self._ip,
                 font=("Segoe UI", 9),
                 bg=c("header"), fg=c("subtext"),
                 anchor="w")
        self._ip_lbl.pack(fill="x")

        # ── Right buttons ──
        right = tk.Frame(self, bg=c("header"))
        right.pack(side="right", padx=14)

        self._theme_btn = self._icon_btn(right, "☀", self._toggle_theme,
                                         tooltip="Toggle theme")
        self._theme_btn.pack(side="right", padx=2)

        self._logout_btn = self._icon_btn(right, "⇥", self._logout,
                                          fg=c("error"), tooltip="Sign Out")
        self._logout_btn.pack(side="right", padx=2)

        self._troubleshoot_btn = self._icon_btn(right, "🔧", self._troubleshoot,
                                                tooltip="Troubleshoot")
        self._troubleshoot_btn.pack(side="right", padx=2)

        self._refresh_btn = self._icon_btn(right, "⟳", self._refresh,
                                           tooltip="Scan Network")
        self._refresh_btn.pack(side="right", padx=2)

    def _icon_btn(self, parent, text, command, fg=None, tooltip=None):
        btn = tk.Button(parent, text=text,
                        font=("Segoe UI", 14),
                        bg=c("header"),
                        fg=fg or c("btn_fg"),
                        activebackground=c("header"),
                        activeforeground=c("btn_hover_fg"),
                        relief="flat", bd=0,
                        padx=6, pady=4,
                        cursor="hand2",
                        command=command)
        if tooltip:
            self._add_tooltip(btn, tooltip)
        return btn

    def _add_tooltip(self, widget, text):
        tip = None
        def enter(e):
            nonlocal tip
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tip = tk.Toplevel(widget)
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)
            tip.geometry(f"+{x}+{y}")
            tk.Label(tip, text=text, font=("Segoe UI", 9),
                     bg=c("card_bg"), fg=c("text"),
                     padx=8, pady=4,
                     relief="flat").pack()
        def leave(e):
            nonlocal tip
            if tip:
                tip.destroy()
                tip = None
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _draw_monitor(self, canvas):
        canvas.delete("all")
        fg = c("icon_fg")
        bg = c("header")
        canvas.create_rectangle(2, 2, 34, 26, outline=fg, width=2, fill=bg)
        canvas.create_rectangle(14, 26, 22, 32, fill=fg, outline="")
        canvas.create_rectangle(8, 32, 28, 34, fill=fg, outline="")

    def _toggle_theme(self):
        self._app.toggle_theme()

    def _logout(self):
        self._app.confirm_logout()

    def _troubleshoot(self):
        self._app.show_troubleshoot()

    def _refresh(self):
        self._app.start_scan()

    def refresh_theme(self):
        self.config(bg=c("header"))
        for child in self.winfo_children():
            try: child.config(bg=c("header"))
            except: pass


# ═════════════════════════════════════════════════════════════════════════════
# Connection Dialog
# ═════════════════════════════════════════════════════════════════════════════

class ConnectionDialog(tk.Toplevel):
    """
    Modal dialog for handshake authentication.
    Calls api.handshake() on confirm.
    """
    W, H = 390, 370

    def __init__(self, master, machine, api=None, on_success=None, **kw):
        super().__init__(master, **kw)
        self.title("Connect to Device")
        self.configure(bg=c("card_bg"))
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self._machine    = machine
        self._api        = api
        self._on_success = on_success
        self._show_pw    = False
        self._build()
        self._center()
        # grab_set after window is visible (use after to ensure mapped)
        self.after(50, self._safe_grab)

    def _build(self):
        BG  = c("card_bg")
        HDR = c("panel_top")

        # ── Title bar ──
        title_bar = tk.Frame(self, bg=HDR, height=52)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        net_cv = tk.Canvas(title_bar, width=28, height=28,
                           bg=HDR, highlightthickness=0)
        net_cv.pack(side="left", padx=(18, 0), pady=12)
        self._draw_network_icon(net_cv, c("accent"))

        tk.Label(title_bar,
                 text="Connect to Device",
                 font=("Segoe UI", 12, "bold"),
                 bg=HDR, fg=c("text")).pack(side="left", padx=10)

        close_btn = tk.Button(title_bar, text="✕",
                              font=("Segoe UI", 11),
                              bg=HDR, fg=c("subtext"),
                              activebackground=c("error"),
                              activeforeground="#ffffff",
                              relief="flat", bd=0,
                              padx=10, pady=8,
                              cursor="hand2",
                              command=self.destroy)
        close_btn.pack(side="right")

        # ── Info card ──
        info_outer = tk.Frame(self, bg=BG, padx=20, pady=0)
        info_outer.pack(fill="x", pady=(14, 0))

        info_card = tk.Frame(info_outer,
                             bg=c("header"),
                             padx=14, pady=12)
        info_card.pack(fill="x")

        rows = [
            ("👤", "Username:",   self._machine.get("username", ""),  True),
            ("🖧",  "IP Address:", self._machine.get("ip", ""),        False),
            ("🖥",  "OS:",         self._machine.get("os", "Linux").upper(), False),
        ]
        for icon, label, value, bold_val in rows:
            row = tk.Frame(info_card, bg=c("header"))
            row.pack(fill="x", pady=2)
            tk.Label(row, text=icon,
                     font=("Segoe UI", 10),
                     bg=c("header"), fg=c("subtext"),
                     width=2).pack(side="left")
            tk.Label(row, text=label,
                     font=("Segoe UI", 9),
                     bg=c("header"), fg=c("subtext")).pack(side="left", padx=(4, 6))
            tk.Label(row, text=value,
                     font=("Segoe UI", 9, "bold" if bold_val else "normal"),
                     bg=c("header"), fg=c("text")).pack(side="left")

        # ── Password field ──
        pw_outer = tk.Frame(self, bg=BG, padx=20)
        pw_outer.pack(fill="x", pady=(18, 0))

        lbl_frame = tk.Frame(pw_outer, bg=BG)
        lbl_frame.pack(fill="x")
        tk.Label(lbl_frame, text=" Password ",
                 font=("Segoe UI", 8),
                 bg=BG, fg=c("subtext")).pack(side="left", padx=10)
        tk.Frame(lbl_frame, bg=c("divider"), height=1).pack(
            side="left", fill="x", expand=True)

        field_frame = tk.Frame(pw_outer,
                               bg=c("header"),
                               highlightbackground=c("divider"),
                               highlightthickness=1)
        field_frame.pack(fill="x")

        lock_cv = tk.Canvas(field_frame, width=22, height=22,
                            bg=c("header"), highlightthickness=0)
        lock_cv.pack(side="left", padx=(10, 4), pady=10)
        self._draw_lock(lock_cv, c("subtext"))

        self._pw_var = tk.StringVar()
        self._pw_entry = tk.Entry(field_frame,
                                  textvariable=self._pw_var,
                                  show="●",
                                  font=("Segoe UI", 12),
                                  bg=c("header"), fg=c("text"),
                                  insertbackground=c("text"),
                                  relief="flat", bd=0,
                                  highlightthickness=0)
        self._pw_entry.pack(side="left", fill="x", expand=True, ipady=10)
        self._pw_entry.focus_set()
        self._pw_entry.bind("<Return>", lambda e: self._confirm())

        self._pw_entry.bind("<FocusIn>",
            lambda e: field_frame.config(highlightbackground=c("accent")))
        self._pw_entry.bind("<FocusOut>",
            lambda e: field_frame.config(highlightbackground=c("divider")))

        self._eye_btn = tk.Button(field_frame,
                                  text="👁",
                                  font=("Segoe UI", 11),
                                  bg=c("header"), fg=c("subtext"),
                                  activebackground=c("header"),
                                  activeforeground=c("text"),
                                  relief="flat", bd=0,
                                  padx=8, pady=8,
                                  cursor="hand2",
                                  command=self._toggle_pw)
        self._eye_btn.pack(side="right")

        # ── Error label ──
        self._error_lbl = tk.Label(self, text="", font=("Segoe UI", 9),
                                   bg=BG, fg=c("error"))
        self._error_lbl.pack(fill="x", padx=20, pady=(6, 0))

        # ── Footer buttons ──
        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", padx=20, pady=(12, 22))

        tk.Button(footer, text="Cancel",
                  command=self.destroy,
                  font=("Segoe UI", 10),
                  bg=BG, fg=c("subtext"),
                  activebackground=c("card_hover"),
                  activeforeground=c("text"),
                  relief="flat", bd=0,
                  padx=12, pady=7,
                  cursor="hand2").pack(side="right", padx=(8, 0))

        self._connect_btn = tk.Button(footer,
                                text="→  Connect",
                                command=self._confirm,
                                font=("Segoe UI", 10, "bold"),
                                bg=c("accent"), fg="#ffffff",
                                activebackground="#2255bb",
                                activeforeground="#ffffff",
                                relief="flat", bd=0,
                                padx=18, pady=7,
                                cursor="hand2")
        self._connect_btn.pack(side="right")

    # ── canvas helpers ──
    @staticmethod
    def _draw_network_icon(cv, color):
        cv.delete("all")
        cv.create_oval(10, 10, 18, 18, fill=color, outline="")
        spokes = [(4, 4, 6, 6), (22, 4, 24, 6), (13, 22, 15, 24)]
        endpoints = [(0, 0, 8, 8), (18, 0, 26, 8), (9, 18, 19, 28)]
        for (lx2, ly2, rx2, ry2), (ox1, oy1, ox2, oy2) in zip(spokes, endpoints):
            cx_s = (lx2 + rx2) / 2
            cy_s = (ly2 + ry2) / 2
            cv.create_line(14, 14, cx_s, cy_s, fill=color, width=2)
            cv.create_oval(ox1, oy1, ox2, oy2, fill=color, outline="")

    @staticmethod
    def _draw_lock(cv, color):
        cv.delete("all")
        cv.create_arc(4, 1, 18, 14, start=0, extent=180,
                      outline=color, width=2, style="arc")
        cv.create_rectangle(2, 11, 20, 22, fill=color, outline="")
        cv.create_oval(9, 13, 13, 17, fill="#1a1a1c", outline="")
        cv.create_rectangle(10, 15, 12, 20, fill="#1a1a1c", outline="")

    # ── interaction ──
    def _toggle_pw(self):
        self._show_pw = not self._show_pw
        self._pw_entry.config(show="" if self._show_pw else "●")
        self._eye_btn.config(fg=c("accent") if self._show_pw else c("subtext"))

    def _confirm(self):
        password = self._pw_var.get()
        if not password:
            self._error_lbl.config(text="Password is required")
            return
        self._error_lbl.config(text="")
        self._connect_btn.config(state="disabled", text="Connecting…")

        if self._api:
            ip = self._machine.get("ip", "")

            def _bg():
                result = self._api.handshake(ip, password)
                self.after(0, lambda: self._on_handshake_result(result))

            threading.Thread(target=_bg, daemon=True).start()
        else:
            # No API — just succeed
            self._on_handshake_result({"success": True})

    def _on_handshake_result(self, result):
        if result.get("success"):
            if self._on_success:
                self._on_success(self._machine)
            self.destroy()
        else:
            error = result.get("error", "Authentication failed")
            self._error_lbl.config(text=error)
            self._connect_btn.config(state="normal", text="→  Connect")

    def _safe_grab(self):
        """Attempt grab_set after the window is mapped. Ignore errors."""
        try:
            self.grab_set()
        except tk.TclError:
            pass  # window may not be viewable on some WMs

    def _center(self):
        self.update_idletasks()
        root = self.master
        while root.master:
            root = root.master
        rx = root.winfo_rootx() + root.winfo_width()  // 2 - self.W // 2
        ry = root.winfo_rooty() + root.winfo_height() // 2 - self.H // 2
        self.geometry(f"{self.W}x{self.H}+{rx}+{ry}")


# ═════════════════════════════════════════════════════════════════════════════
# Troubleshoot Overlay
# ═════════════════════════════════════════════════════════════════════════════

class TroubleshootOverlay(tk.Toplevel):
    """Modal dialog with troubleshooting steps and a FIX Firewall button."""
    W, H = 520, 560

    STEPS = [
        ("1", "🗑  Clear Cache",
         "Close the app completely, delete any cached data\n"
         "(browser cache, app data), and relaunch."),
        ("2", "📡  Check Network Connection",
         "Verify your Wi-Fi or Ethernet cable is connected\n"
         "and active. Try pinging your gateway."),
        ("3", "🌐  Verify Correct Network",
         "Ensure both devices are on the same LAN / subnet.\n"
         "Wrong network can cause CA certificate mismatches."),
        ("4", "🔑  Check Certificates & Keys",
         "Confirm the certs/ directory exists and contains\n"
         "valid CA cert, client cert, and key files."),
        ("5", "🛡  Fix Firewall Rules (requires sudo)",
         "Your system firewall may be blocking required ports.\n"
         "Click the button below to add allow-rules."),
    ]

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.title("Troubleshoot")
        self.configure(bg=c("card_bg"))
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self._build()
        self._center()
        self.after(50, self._safe_grab)

    def _build(self):
        BG = c("card_bg")
        HDR = c("panel_top")

        # ── Title bar ──
        title_bar = tk.Frame(self, bg=HDR, height=52)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        tk.Label(title_bar, text="🔧", font=("Segoe UI", 16),
                 bg=HDR, fg=c("accent")).pack(side="left", padx=(18, 6), pady=12)
        tk.Label(title_bar, text="Troubleshoot",
                 font=("Segoe UI", 12, "bold"),
                 bg=HDR, fg=c("text")).pack(side="left", padx=4)

        close_btn = tk.Button(title_bar, text="✕",
                              font=("Segoe UI", 11),
                              bg=HDR, fg=c("subtext"),
                              activebackground=c("error"),
                              activeforeground="#ffffff",
                              relief="flat", bd=0,
                              padx=10, pady=8,
                              cursor="hand2",
                              command=self.destroy)
        close_btn.pack(side="right")

        # ── Intro text ──
        tk.Label(self,
                 text="If the app isn't connecting, try these steps:",
                 font=("Segoe UI", 9),
                 bg=BG, fg=c("subtext"),
                 anchor="w").pack(fill="x", padx=20, pady=(14, 8))

        # ── Steps ──
        for num, title, desc in self.STEPS:
            step_frame = tk.Frame(self, bg=BG)
            step_frame.pack(fill="x", padx=20, pady=4)

            # Number badge
            badge = tk.Label(step_frame, text=num,
                             font=("Segoe UI", 9, "bold"),
                             bg=c("accent"), fg="#ffffff",
                             width=2, height=1)
            badge.pack(side="left", padx=(0, 8), anchor="n")

            info = tk.Frame(step_frame, bg=BG)
            info.pack(side="left", fill="x", expand=True)

            tk.Label(info, text=title,
                     font=("Segoe UI", 9, "bold"),
                     bg=BG, fg=c("text"),
                     anchor="w").pack(fill="x")
            tk.Label(info, text=desc,
                     font=("Segoe UI", 8),
                     bg=BG, fg=c("subtext"),
                     anchor="w", justify="left").pack(fill="x")

        # ── Result area ──
        self._result_frame = tk.Frame(self, bg=BG)
        self._result_frame.pack(fill="x", padx=20, pady=(8, 0))
        self._result_lbl = tk.Label(self._result_frame, text="",
                                    font=("Segoe UI", 9),
                                    bg=BG, fg=c("subtext"),
                                    wraplength=460, justify="left")
        self._result_lbl.pack(fill="x")

        # ── Footer ──
        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", padx=20, pady=(12, 20))

        tk.Label(footer, text="Step 5 requires sudo privileges",
                 font=("Segoe UI", 8),
                 bg=BG, fg=c("subtext")).pack(side="left")

        self._fix_btn = tk.Button(
            footer, text="🛠  FIX Firewall",
            font=("Segoe UI", 10, "bold"),
            bg=c("accent"), fg="#ffffff",
            activebackground="#2255bb",
            activeforeground="#ffffff",
            relief="flat", bd=0,
            padx=16, pady=6,
            cursor="hand2",
            command=self._fix_firewall)
        self._fix_btn.pack(side="right")

    def _fix_firewall(self):
        self._fix_btn.config(state="disabled", text="Fixing…")
        self._result_lbl.config(text="", fg=c("subtext"))

        def _bg():
            try:
                import shutil
                fw_script = os.path.join(_PROJECT_ROOT, "firewall_manager.py")
                python = sys.executable or "python3"

                if os.name == "nt":
                    cmd = [python, fw_script, "--install"]
                elif shutil.which("pkexec"):
                    cmd = ["pkexec", python, fw_script, "--install"]
                else:
                    cmd = ["sudo", python, fw_script, "--install"]

                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=30)
                output = (result.stdout or "") + (result.stderr or "")
                success = result.returncode == 0
                self.after(0, lambda: self._on_fix_done(success, output.strip()))
            except subprocess.TimeoutExpired:
                self.after(0, lambda: self._on_fix_done(
                    False, "Timed out. Run manually: sudo python3 firewall_manager.py --install"))
            except Exception as e:
                self.after(0, lambda: self._on_fix_done(False, str(e)))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_fix_done(self, success, message):
        self._fix_btn.config(state="normal", text="🛠  FIX Firewall")
        if success:
            self._result_lbl.config(
                text=f"✓ {message or 'Firewall rules applied.'}",
                fg=c("online"))
        else:
            self._result_lbl.config(
                text=f"✗ {message or 'Failed.'}",
                fg=c("error"))

    def _safe_grab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _center(self):
        self.update_idletasks()
        root = self.master
        while root.master:
            root = root.master
        rx = root.winfo_rootx() + root.winfo_width()  // 2 - self.W // 2
        ry = root.winfo_rooty() + root.winfo_height() // 2 - self.H // 2
        self.geometry(f"{self.W}x{self.H}+{rx}+{ry}")


# ═════════════════════════════════════════════════════════════════════════════
# Landing Page
# ═════════════════════════════════════════════════════════════════════════════

class LandingPage(tk.Frame):
    """
    Full landing page frame.
    Manages three body states: scanning, empty, grid.
    Connected to backend via api_client.
    """
    def __init__(self, master, navigator=None, api=None, **kw):
        super().__init__(master, bg=c("bg"), **kw)
        self._nav     = navigator
        self._api     = api
        self._state   = "scanning"
        self._build()
        self.after(100, lambda: self.start_scan())

    def _build(self):
        # Load current user info from .env
        env = _load_env()
        username = env.get("USER", "Loading…")
        ip = env.get("HOST", "")

        # Header
        self._header = LandingHeader(self, app_ref=self,
                                     current_user=username,
                                     current_ip=ip)
        self._header.pack(fill="x")

        # Thin divider
        self._divider = tk.Frame(self, bg=c("header_border"), height=1)
        self._divider.pack(fill="x")

        # Body container
        self._body = tk.Frame(self, bg=c("bg"))
        self._body.pack(fill="both", expand=True)

        # Scanning overlay
        self._scanning = ScanningOverlay(self._body)
        self._empty    = None
        self._grid     = None

    def _clear_body(self):
        for child in self._body.winfo_children():
            child.place_forget()
            child.pack_forget()

    def _show_scanning(self):
        self._clear_body()
        self._scanning.config(bg=c("bg"))
        self._scanning.pack(fill="both", expand=True)
        self._scanning.start()

    def _show_grid(self, machines):
        self._scanning.stop()
        self._clear_body()
        if self._grid:
            self._grid.destroy()
        self._grid = MachineGrid(self._body, machines=machines,
                                 on_select=self._on_machine_tap)
        self._grid.pack(fill="both", expand=True)

    def _show_empty(self):
        self._scanning.stop()
        self._clear_body()
        if self._empty:
            self._empty.destroy()
        self._empty = EmptyState(self._body,
                                  on_rescan=self.start_scan,
                                  on_troubleshoot=self.show_troubleshoot)
        self._empty.pack(fill="both", expand=True)

    # ── Public interface ──
    def start_scan(self):
        self._show_scanning()
        # Always silently apply firewall rules in the background before scanning
        threading.Thread(target=self._auto_fix_firewall, daemon=True).start()
        if self._api:
            def _bg():
                machines = self._api.scan_network()
                self.after(0, lambda: self._finish_scan(machines))
            threading.Thread(target=_bg, daemon=True).start()
        else:
            self.after(1800, lambda: self._finish_scan([]))

    @staticmethod
    def _auto_fix_firewall():
        """Silently attempt to apply firewall rules every scan."""
        try:
            import shutil
            fw_script = os.path.join(_PROJECT_ROOT, "firewall_manager.py")
            if not os.path.isfile(fw_script):
                return
            python = sys.executable or "python3"
            if os.name == "nt":
                cmd = [python, fw_script, "--install"]
            elif shutil.which("pkexec"):
                cmd = ["pkexec", python, fw_script, "--install"]
            else:
                cmd = ["sudo", "-n", python, fw_script, "--install"]
            subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except Exception:
            pass  # Silent – user can still manually fix via header button

    def _finish_scan(self, machines=None):
        if machines is None:
            machines = []

        # Normalise to dicts with username/ip/os/status keys
        normalised = []
        for m in machines:
            if isinstance(m, dict):
                normalised.append({
                    "username": m.get("username", m.get("user", "")),
                    "ip": m.get("ip", m.get("host", "")),
                    "os": m.get("os", m.get("system", "Linux")),
                    "status": m.get("status", "Online"),
                })
        if normalised:
            self._show_grid(normalised)
        else:
            self._show_empty()

    def _on_machine_tap(self, machine):
        try:
            ConnectionDialog(self, machine=machine,
                             api=self._api,
                             on_success=self._connect)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Connection Error",
                                 f"Could not open connection dialog:\n{e}")

    def _connect(self, machine):
        """Handshake succeeded – update .env and navigate to explorer."""
        ip = machine.get("ip", "")
        _write_env_key("DEST_HOST", f"'{ip}'")

        if self._nav:
            self._nav.go("explorer", machine=machine)
        else:
            self._toast(f"Connected to {machine.get('username', '')}  ✓")

    def _toast(self, msg):
        root = self.winfo_toplevel()
        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=c("card_bg"))
        tk.Label(win, text=msg,
                 font=("Segoe UI", 11),
                 bg=c("card_bg"), fg=c("online"),
                 padx=20, pady=14).pack()
        rx = root.winfo_rootx() + root.winfo_width()  // 2 - 130
        ry = root.winfo_rooty() + root.winfo_height() // 2 - 30
        win.geometry(f"+{rx}+{ry}")
        win.after(1600, win.destroy)

    # ── App-level callbacks for header buttons ──
    def show_troubleshoot(self):
        TroubleshootOverlay(self)

    def toggle_theme(self):
        if self._nav:
            self._nav.toggle_theme()

    def confirm_logout(self):
        win = tk.Toplevel(self.winfo_toplevel())
        win.title("Sign Out")
        win.resizable(False, False)
        win.configure(bg=c("card_bg"))
        win.transient(self.winfo_toplevel())
        win.grab_set()

        tk.Label(win, text="Sign Out",
                 font=("Segoe UI", 12, "bold"),
                 bg=c("card_bg"), fg=c("text")).pack(padx=24, pady=(20, 6))
        tk.Label(win,
                 text="Are you sure you want to sign out?\n"
                      "You will need to enter your credentials again.",
                 font=("Segoe UI", 10),
                 bg=c("card_bg"), fg=c("subtext"),
                 justify="center").pack(padx=24)

        row = tk.Frame(win, bg=c("card_bg"))
        row.pack(padx=24, pady=(16, 20), fill="x")

        tk.Button(row, text="Cancel", command=win.destroy,
                  bg=c("header"), fg=c("subtext"),
                  activebackground=c("card_hover"),
                  relief="flat", padx=14, pady=6,
                  font=("Segoe UI", 10), cursor="hand2").pack(side="left")

        def do_logout():
            win.destroy()
            _remove_env_key("PASSWORD")
            if self._nav:
                self._nav.go("login")

        tk.Button(row, text="Sign Out", command=do_logout,
                  bg=c("error"), fg="#ffffff",
                  activebackground="#bb1111",
                  relief="flat", padx=14, pady=6,
                  font=("Segoe UI", 10, "bold"),
                  cursor="hand2").pack(side="right")

        win.update_idletasks()
        w, h = 360, 200
        root = self.winfo_toplevel()
        rx = root.winfo_rootx() + root.winfo_width()  // 2 - w // 2
        ry = root.winfo_rooty() + root.winfo_height() // 2 - h // 2
        win.geometry(f"{w}x{h}+{rx}+{ry}")

    def refresh_theme(self):
        self.config(bg=c("bg"))
        self._divider.config(bg=c("header_border"))
        self._body.config(bg=c("bg"))
        self._header.refresh_theme()
        self._scanning.refresh_theme()
        if self._grid:
            self._grid.refresh_theme()