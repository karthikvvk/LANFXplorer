"""
LANFXplorer – File Explorer Page (Tkinter)
Replica of the Flutter MainPage screen.
Connected to the Flask backend via api_client.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os
import math

from themes import c, set_theme, is_dark, DARK, LIGHT
from landing_page import TroubleshootOverlay

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env():
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


def _remove_env_key(key):
    env_path = os.path.join(_PROJECT_ROOT, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path) as f:
        lines = f.read().splitlines()
    with open(env_path, "w") as f:
        f.write("\n".join(l for l in lines if not l.startswith(f"{key}=")) + "\n")


# ═════════════════════════════════════════════════════════════════════════════
# Size formatter
# ═════════════════════════════════════════════════════════════════════════════

def _fmt_size(size):
    if size is None:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024.0:
            return f"{size:,.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


# ═════════════════════════════════════════════════════════════════════════════
# App Header
# ═════════════════════════════════════════════════════════════════════════════

class AppHeader(tk.Frame):
    """Top bar with logo, connection info, and action buttons."""
    def __init__(self, master, machine=None, on_send=None, on_fetch=None,
                 on_home=None, on_signout=None, on_theme=None,
                 on_troubleshoot=None, **kw):
        super().__init__(master, bg=c("header"), height=56, **kw)
        self.pack_propagate(False)
        self._machine   = machine or {}
        self._on_send   = on_send
        self._on_fetch  = on_fetch
        self._on_home   = on_home
        self._on_signout= on_signout
        self._on_theme  = on_theme
        self._on_troubleshoot = on_troubleshoot
        self._build()

    def _build(self):
        env = _load_env()
        local_user = env.get("USER", "")
        remote_user = self._machine.get("username", "Remote")

        # Left logo
        lbl = tk.Label(self, text="📁 LANFXplorer",
                       font=("Segoe UI", 14, "bold"),
                       bg=c("header"), fg=c("accent"))
        lbl.pack(side="left", padx=(14, 12))

        # Thin vert divider
        tk.Frame(self, bg=c("divider"), width=1).pack(
            side="left", fill="y", padx=4, pady=10)

        # Connection info
        info = tk.Frame(self, bg=c("header"))
        info.pack(side="left", padx=8)
        tk.Label(info,
                 text=f"{local_user}  ⇄  {remote_user}",
                 font=("Segoe UI", 10),
                 bg=c("header"), fg=c("text")).pack(side="left")
        tk.Label(info,
                 text=f"  ({self._machine.get('ip', '')})",
                 font=("Segoe UI", 9),
                 bg=c("header"), fg=c("subtext")).pack(side="left")

        # Right buttons
        right = tk.Frame(self, bg=c("header"))
        right.pack(side="right", padx=14)

        # Sign out
        self._signout_btn = tk.Button(
            right, text="⇥", font=("Segoe UI", 14),
            bg=c("signout_bg"), fg=c("signout_fg"),
            activebackground="#991111",
            relief="flat", bd=0, padx=8, pady=2,
            cursor="hand2",
            command=self._on_signout)
        self._signout_btn.pack(side="right", padx=2)

        # Theme toggle
        self._theme_btn = tk.Button(
            right, text="☀", font=("Segoe UI", 14),
            bg=c("header"), fg=c("btn_fg"),
            activebackground=c("header"),
            relief="flat", bd=0, padx=4, pady=2,
            cursor="hand2",
            command=self._on_theme)
        self._theme_btn.pack(side="right", padx=2)

        # Troubleshoot
        self._troubleshoot_btn = tk.Button(
            right, text="🔧", font=("Segoe UI", 14),
            bg=c("header"), fg=c("btn_fg"),
            activebackground=c("header"),
            relief="flat", bd=0, padx=4, pady=2,
            cursor="hand2",
            command=self._on_troubleshoot)
        self._troubleshoot_btn.pack(side="right", padx=2)

        # Home
        self._home_btn = tk.Button(
            right, text="⌂", font=("Segoe UI", 14),
            bg=c("header"), fg=c("btn_fg"),
            activebackground=c("header"),
            relief="flat", bd=0, padx=4, pady=2,
            cursor="hand2",
            command=self._on_home)
        self._home_btn.pack(side="right", padx=2)

        # Send
        self._send_btn = tk.Button(
            right, text="↑  Send", font=("Segoe UI", 10, "bold"),
            bg=c("accent"), fg="#ffffff",
            activebackground="#2255bb",
            relief="flat", bd=0, padx=12, pady=4,
            cursor="hand2",
            command=self._on_send)
        self._send_btn.pack(side="right", padx=(4, 8))

        # Fetch
        self._fetch_btn = tk.Button(
            right, text="↓  Fetch", font=("Segoe UI", 10),
            bg=c("btn"), fg=c("btn_fg"),
            activebackground=c("card_hover"),
            relief="flat", bd=0, padx=12, pady=4,
            cursor="hand2",
            command=self._on_fetch)
        self._fetch_btn.pack(side="right", padx=4)

    def refresh_theme(self):
        self.config(bg=c("header"))
        for child in self.winfo_children():
            try:
                child.config(bg=c("header"))
            except Exception:
                pass
        self._send_btn.config(bg=c("accent"), fg="#ffffff")
        self._fetch_btn.config(bg=c("btn"), fg=c("btn_fg"))
        self._signout_btn.config(bg=c("signout_bg"), fg=c("signout_fg"))


# ═════════════════════════════════════════════════════════════════════════════
# File Panel (local or remote)
# ═════════════════════════════════════════════════════════════════════════════

class FilePanel(tk.Frame):
    """One side of the dual-panel file explorer.
    Fetches directory listings from the backend."""
    def __init__(self, master, label="Local", api=None,
                 remote_host=None, initial_path=None, **kw):
        super().__init__(master, bg=c("panel"), **kw)
        self._api = api
        self._remote_host = remote_host
        self._label = label
        self._current_path = initial_path or ""
        self._items = []
        self._selected = set()
        self._build()

    def _build(self):
        # ── Top bar ──
        top = tk.Frame(self, bg=c("panel_top"), height=40)
        top.pack(fill="x")
        top.pack_propagate(False)
        self._top = top

        tk.Label(top, text=self._label,
                 font=("Segoe UI", 10, "bold"),
                 bg=c("panel_top"), fg=c("text")).pack(side="left", padx=12)

        # ── Action buttons: new file, new folder, delete ──
        self._del_btn = tk.Button(
            top, text="🗑", font=("Segoe UI", 10),
            bg=c("panel_top"), fg=c("error"),
            activebackground=c("panel_top"),
            relief="flat", bd=0, padx=6, cursor="hand2",
            command=self._delete_selected)
        self._del_btn.pack(side="right", padx=2)

        self._newfile_btn = tk.Button(
            top, text="📄+", font=("Segoe UI", 10),
            bg=c("panel_top"), fg=c("subtext"),
            activebackground=c("panel_top"),
            relief="flat", bd=0, padx=6, cursor="hand2",
            command=self._new_file)
        self._newfile_btn.pack(side="right", padx=2)

        self._newfolder_btn = tk.Button(
            top, text="📁+", font=("Segoe UI", 10),
            bg=c("panel_top"), fg=c("subtext"),
            activebackground=c("panel_top"),
            relief="flat", bd=0, padx=6, cursor="hand2",
            command=self._new_folder)
        self._newfolder_btn.pack(side="right", padx=2)

        # ── Breadcrumb / path bar ──
        self._path_frame = tk.Frame(self, bg=c("panel"), height=28)
        self._path_frame.pack(fill="x")
        self._path_frame.pack_propagate(False)

        self._path_lbl = tk.Label(self._path_frame, text="",
                                  font=("Segoe UI", 8),
                                  bg=c("panel"), fg=c("subtext"),
                                  anchor="w")
        self._path_lbl.pack(side="left", padx=10)

        # ── File tree (Treeview) ──
        style = ttk.Style()
        style.configure("File.Treeview",
                        background=c("panel"),
                        foreground=c("text"),
                        fieldbackground=c("panel"),
                        font=("Segoe UI", 10),
                        rowheight=28)
        style.configure("File.Treeview.Heading",
                        background=c("panel_top"),
                        foreground=c("subtext"),
                        font=("Segoe UI", 9, "bold"))
        style.map("File.Treeview",
                  background=[("selected", c("selected"))],
                  foreground=[("selected", c("text"))])

        tree_frame = tk.Frame(self, bg=c("panel"))
        tree_frame.pack(fill="both", expand=True)

        self._tree = ttk.Treeview(
            tree_frame,
            columns=("size", "modified"),
            show="tree headings",
            selectmode="extended",
            style="File.Treeview")

        self._tree.heading("#0", text="Name", anchor="w")
        self._tree.heading("size", text="Size", anchor="e")
        self._tree.heading("modified", text="Modified", anchor="w")

        self._tree.column("#0", width=220, minwidth=120)
        self._tree.column("size", width=80, minwidth=60, anchor="e")
        self._tree.column("modified", width=140, minwidth=80)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)

        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── Loading label ──
        self._loading_lbl = tk.Label(self, text="Loading…",
                                     font=("Segoe UI", 10),
                                     bg=c("panel"), fg=c("subtext"))

    def load_path(self, path):
        """Load a directory listing for the given path."""
        self._current_path = path
        self._path_lbl.config(text=path)
        self._tree.delete(*self._tree.get_children())
        self._selected.clear()
        self._loading_lbl.place(relx=0.5, rely=0.5, anchor="center")

        if self._api:
            def _bg():
                items = self._api.list_directory(path,
                    remote_host=self._remote_host)
                self.after(0, lambda: self._populate(items))
            threading.Thread(target=_bg, daemon=True).start()
        else:
            self.after(200, lambda: self._populate([]))

    def _populate(self, items):
        self._loading_lbl.place_forget()
        self._tree.delete(*self._tree.get_children())
        self._items = items or []

        # Sort: directories first, then alphabetical
        dirs  = sorted([f for f in self._items if f.get("is_directory")],
                       key=lambda f: f.get("name", "").lower())
        files = sorted([f for f in self._items if not f.get("is_directory")],
                       key=lambda f: f.get("name", "").lower())

        # Add parent directory entry if not at root
        if self._current_path and self._current_path != "/":
            self._tree.insert("", "end", iid="__parent__",
                              text="📁 ..",
                              values=("", ""))

        for f in dirs:
            self._tree.insert("", "end", iid=f.get("path", f["name"]),
                              text=f"📁 {f['name']}",
                              values=("", f.get("mtime", "")[:10]))

        for f in files:
            self._tree.insert("", "end", iid=f.get("path", f["name"]),
                              text=f"📄 {f['name']}",
                              values=(_fmt_size(f.get("size")),
                                      f.get("mtime", "")[:10]))

    def _on_double_click(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == "__parent__":
            parent = os.path.dirname(self._current_path)
            if parent:
                self.load_path(parent)
            return
        # Check if it's a directory
        for f in self._items:
            if f.get("path") == iid and f.get("is_directory"):
                self.load_path(f["path"])
                return

    def _on_select(self, event):
        self._selected = set(self._tree.selection()) - {"__parent__"}

    def get_selected_paths(self):
        return list(self._selected)

    def get_current_path(self):
        return self._current_path

    # ── file operations ──
    def _new_file(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("New File", "File name:",
                                      parent=self)
        if not name:
            return
        full_path = os.path.join(self._current_path, name)
        if self._api:
            def _bg():
                ok = self._api.create_file(full_path,
                         remote_host=self._remote_host)
                self.after(0, lambda: self._on_op_done(ok, "File created"))
            threading.Thread(target=_bg, daemon=True).start()

    def _new_folder(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("New Folder", "Folder name:",
                                      parent=self)
        if not name:
            return
        full_path = os.path.join(self._current_path, name)
        if self._api:
            def _bg():
                ok = self._api.create_folder(full_path,
                         remote_host=self._remote_host)
                self.after(0, lambda: self._on_op_done(ok, "Folder created"))
            threading.Thread(target=_bg, daemon=True).start()

    def _delete_selected(self):
        paths = self.get_selected_paths()
        if not paths:
            return
        confirmed = messagebox.askyesno(
            "Delete",
            f"Delete {len(paths)} item(s)?\nThis cannot be undone.")
        if not confirmed:
            return

        if self._api:
            def _bg():
                for p in paths:
                    self._api.delete_item(p, remote_host=self._remote_host)
                self.after(0, lambda: self._on_op_done(True, "Deleted"))
            threading.Thread(target=_bg, daemon=True).start()

    def _on_op_done(self, ok, msg):
        if ok:
            self.load_path(self._current_path)  # Refresh

    def refresh_theme(self):
        self.config(bg=c("panel"))
        self._top.config(bg=c("panel_top"))
        self._path_frame.config(bg=c("panel"))
        self._path_lbl.config(bg=c("panel"), fg=c("subtext"))
        self._loading_lbl.config(bg=c("panel"), fg=c("subtext"))

        style = ttk.Style()
        style.configure("File.Treeview",
                        background=c("panel"),
                        foreground=c("text"),
                        fieldbackground=c("panel"))
        style.configure("File.Treeview.Heading",
                        background=c("panel_top"),
                        foreground=c("subtext"))
        style.map("File.Treeview",
                  background=[("selected", c("selected"))],
                  foreground=[("selected", c("text"))])


# ═════════════════════════════════════════════════════════════════════════════
# Transfer Panel
# ═════════════════════════════════════════════════════════════════════════════

class TransferPanel(tk.Frame):
    """Bottom panel showing real transfer progress."""
    PANEL_H = 160

    def __init__(self, master, api=None, **kw):
        super().__init__(master, bg=c("transfer_bg"), height=self.PANEL_H, **kw)
        self.pack_propagate(False)
        self._api = api
        self._transfers = {}  # task_id → {label, bar, status, ...}
        self._build()

    def _build(self):
        top = tk.Frame(self, bg=c("transfer_bg"))
        top.pack(fill="x", padx=14, pady=(10, 4))

        tk.Label(top, text="Transfers",
                 font=("Segoe UI", 10, "bold"),
                 bg=c("transfer_bg"), fg=c("text")).pack(side="left")

        self._count_lbl = tk.Label(top, text="",
                                   font=("Segoe UI", 9),
                                   bg=c("transfer_bg"), fg=c("subtext"))
        self._count_lbl.pack(side="right")

        # Scrollable canvas for transfer items
        self._canvas = tk.Canvas(self, bg=c("transfer_bg"),
                                 highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        self._inner = tk.Frame(self._canvas, bg=c("transfer_bg"))
        self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))

        # Empty state
        self._empty_lbl = tk.Label(self._inner,
                                   text="No active transfers",
                                   font=("Segoe UI", 9),
                                   bg=c("transfer_bg"), fg=c("subtext"))
        self._empty_lbl.pack(pady=20)

    def add_transfer(self, task_id, direction, file_desc=""):
        """Add a transfer entry and start polling for progress."""
        self._empty_lbl.pack_forget()

        row = tk.Frame(self._inner, bg=c("transfer_bg"))
        row.pack(fill="x", pady=2)

        arrow = "↑" if direction == "send" else "↓"
        label = tk.Label(row, text=f"{arrow}  {file_desc or task_id[:8]}",
                         font=("Segoe UI", 9),
                         bg=c("transfer_bg"), fg=c("text"),
                         anchor="w")
        label.pack(fill="x")

        bar_bg = tk.Frame(row, bg=c("progress_bg"), height=6)
        bar_bg.pack(fill="x", pady=(2, 0))

        bar_fill = tk.Frame(bar_bg, bg=c("progress_fill"), height=6)
        bar_fill.place(relx=0, rely=0, relwidth=0, relheight=1)

        status = tk.Label(row, text="Starting…",
                          font=("Segoe UI", 8),
                          bg=c("transfer_bg"), fg=c("subtext"),
                          anchor="w")
        status.pack(fill="x")

        self._transfers[task_id] = {
            "row": row,
            "label": label,
            "bar_fill": bar_fill,
            "status": status,
            "done": False,
        }

        self._update_count()

        # Start polling
        self._poll_transfer(task_id)

    def _poll_transfer(self, task_id):
        info = self._transfers.get(task_id)
        if not info or info["done"]:
            return
        if not self._api:
            return

        def _bg():
            result = self._api.get_transfer_status(task_id)
            self.after(0, lambda: self._update_transfer(task_id, result))

        threading.Thread(target=_bg, daemon=True).start()

    def _update_transfer(self, task_id, result):
        info = self._transfers.get(task_id)
        if not info:
            return

        if result is None:
            info["status"].config(text="Checking…")
            self.after(2000, lambda: self._poll_transfer(task_id))
            return

        status = result.get("status", "unknown")
        progress = result.get("progress", 0)

        info["bar_fill"].place(relx=0, rely=0,
                                relwidth=max(0.01, min(1.0, progress)),
                                relheight=1)

        if status == "completed":
            info["status"].config(text="✓  Completed", fg=c("online"))
            info["bar_fill"].config(bg=c("online"))
            info["done"] = True
            self._update_count()
        elif status == "failed":
            error = result.get("error", "Transfer failed")
            info["status"].config(text=f"✕  {error}", fg=c("error"))
            info["bar_fill"].config(bg=c("error"))
            info["done"] = True
            self._update_count()
        else:
            pct = int(progress * 100)
            current = result.get("current_file", "")
            if current:
                fname = os.path.basename(current)
                info["status"].config(text=f"{pct}%  {fname}")
            else:
                info["status"].config(text=f"{pct}%")
            self.after(1500, lambda: self._poll_transfer(task_id))

    def _update_count(self):
        active = sum(1 for t in self._transfers.values() if not t["done"])
        total = len(self._transfers)
        self._count_lbl.config(text=f"{active} active / {total} total")

    def refresh_theme(self):
        self.config(bg=c("transfer_bg"))
        self._canvas.config(bg=c("transfer_bg"))
        self._inner.config(bg=c("transfer_bg"))
        self._count_lbl.config(bg=c("transfer_bg"), fg=c("subtext"))
        for info in self._transfers.values():
            info["row"].config(bg=c("transfer_bg"))
            info["label"].config(bg=c("transfer_bg"), fg=c("text"))
            info["status"].config(bg=c("transfer_bg"))


# ═════════════════════════════════════════════════════════════════════════════
# Explorer Page
# ═════════════════════════════════════════════════════════════════════════════

class ExplorerPage(tk.Frame):
    """
    Full explorer page with dual file panels and transfer bar.
    """
    def __init__(self, master, navigator=None, api=None,
                 machine=None, **kw):
        super().__init__(master, bg=c("bg"), **kw)
        self._nav     = navigator
        self._api     = api
        self._machine = machine or {}
        self._build()
        # Load initial paths after a brief delay
        self.after(300, self._load_initial_paths)

    def _build(self):
        # ── Header ──
        self._header = AppHeader(
            self,
            machine=self._machine,
            on_send=self._do_send,
            on_fetch=self._do_fetch,
            on_home=self._go_home,
            on_signout=self._do_signout,
            on_theme=self._toggle_theme,
            on_troubleshoot=self._show_troubleshoot,
        )
        self._header.pack(fill="x")

        tk.Frame(self, bg=c("divider"), height=1).pack(fill="x")

        # ── Body: PanedWindow with local + remote panels ──
        self._paned = tk.PanedWindow(
            self, orient="horizontal",
            bg=c("divider"), sashwidth=4, sashpad=0,
            bd=0, relief="flat")
        self._paned.pack(fill="both", expand=True)

        remote_host = self._machine.get("ip")

        self._local_panel = FilePanel(
            self._paned, label="Local Files",
            api=self._api, remote_host=None)
        self._remote_panel = FilePanel(
            self._paned, label="Remote Files",
            api=self._api, remote_host=remote_host)

        self._paned.add(self._local_panel, stretch="always")
        self._paned.add(self._remote_panel, stretch="always")

        # ── Transfer panel ──
        self._transfers = TransferPanel(self, api=self._api)
        self._transfers.pack(fill="x", side="bottom")

        tk.Frame(self, bg=c("divider"), height=1).pack(
            fill="x", side="bottom")

    def _load_initial_paths(self):
        """Fetch default paths from API and load directories."""
        if not self._api:
            return

        remote_host = self._machine.get("ip")

        def _bg():
            local_path  = self._api.get_default_path()
            remote_path = self._api.get_default_path(remote_host=remote_host)
            self.after(0, lambda: self._on_paths_loaded(local_path, remote_path))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_paths_loaded(self, local_path, remote_path):
        if local_path:
            self._local_panel.load_path(local_path)
        else:
            # Fallback to home dir
            self._local_panel.load_path(
                os.path.join(os.path.expanduser("~"), "Lanfxplorer"))

        if remote_path:
            self._remote_panel.load_path(remote_path)
        else:
            self._remote_panel.load_path("/")

    # ── actions ──
    def _do_send(self):
        """Send selected local files to the remote machine."""
        paths = self._local_panel.get_selected_paths()
        if not paths:
            messagebox.showinfo("Send Files",
                                "Select files in the Local panel first.")
            return

        remote_host = self._machine.get("ip")
        dest_dir = self._remote_panel.get_current_path()

        def _bg():
            result = self._api.send_files(remote_host, paths,
                                           dest_dir=dest_dir)
            self.after(0, lambda: self._on_send_result(result, paths))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_send_result(self, result, paths):
        if result and result.get("task_id"):
            desc = f"{len(paths)} file(s) → {self._machine.get('username', 'Remote')}"
            self._transfers.add_transfer(
                result["task_id"], "send", file_desc=desc)
        else:
            messagebox.showerror("Send Failed",
                                 "Could not initiate file transfer.")

    def _do_fetch(self):
        """Fetch selected remote files to the local machine."""
        paths = self._remote_panel.get_selected_paths()
        if not paths:
            messagebox.showinfo("Fetch Files",
                                "Select files in the Remote panel first.")
            return

        remote_host = self._machine.get("ip")
        dest_dir = self._local_panel.get_current_path()

        def _bg():
            result = self._api.fetch_files(remote_host, paths,
                                            dest_dir=dest_dir)
            self.after(0, lambda: self._on_fetch_result(result, paths))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_fetch_result(self, result, paths):
        if result and result.get("task_id"):
            desc = f"{len(paths)} file(s) ← {self._machine.get('username', 'Remote')}"
            self._transfers.add_transfer(
                result["task_id"], "fetch", file_desc=desc)
        else:
            messagebox.showerror("Fetch Failed",
                                 "Could not initiate file fetch.")

    def _go_home(self):
        if self._nav:
            self._nav.go("landing")

    def _do_signout(self):
        confirmed = messagebox.askyesno(
            "Sign Out",
            "Are you sure you want to sign out?\n"
            "You will need to enter your credentials again.")
        if confirmed:
            _remove_env_key("PASSWORD")
            if self._nav:
                self._nav.go("login")

    def _toggle_theme(self):
        if self._nav:
            self._nav.toggle_theme()

    def _show_troubleshoot(self):
        TroubleshootOverlay(self)

    def refresh_theme(self):
        self.config(bg=c("bg"))
        self._header.refresh_theme()
        self._local_panel.refresh_theme()
        self._remote_panel.refresh_theme()
        self._transfers.refresh_theme()
        self._paned.config(bg=c("divider"))