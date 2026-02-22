"""
LANFXplorer – Tkinter Application Entry Point & Navigator
Unified app that wires login → landing → explorer screens
to the Flask backend via api_client.

Usage:  python 32bitscreens/tkinter_app.py
"""

import tkinter as tk
from tkinter import ttk
import sys
import os

# Ensure 32bitscreens package is on path
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _SCRIPT_DIR)
sys.path.insert(0, _PROJECT_ROOT)

from themes import c, set_theme, is_dark
from api_client import ApiClient
from login import LoginPage
from landing_page import LandingPage
from explorer import ExplorerPage


class Navigator:
    """
    Manages screen transitions.
    Destroys the current screen frame and instantiates the next one.
    """
    def __init__(self, root: tk.Tk, api: ApiClient):
        self._root = root
        self._api  = api
        self._current_page = None
        self._dark = True

    def go(self, screen_name: str, **kwargs):
        """
        Navigate to a screen.
        screen_name: "login" | "landing" | "explorer"
        kwargs are forwarded to the screen constructor.
        """
        # Tear down old screen
        if self._current_page is not None:
            self._current_page.destroy()
            self._current_page = None

        # Build new screen
        if screen_name == "login":
            self._current_page = LoginPage(
                self._root, navigator=self, api=self._api)
        elif screen_name == "landing":
            self._current_page = LandingPage(
                self._root, navigator=self, api=self._api)
        elif screen_name == "explorer":
            self._current_page = ExplorerPage(
                self._root, navigator=self, api=self._api,
                machine=kwargs.get("machine"))
        else:
            raise ValueError(f"Unknown screen: {screen_name}")

        self._current_page.pack(fill="both", expand=True)
        self._root.configure(bg=c("bg"))

    def toggle_theme(self):
        """Toggle dark/light theme and refresh the current screen."""
        self._dark = not self._dark
        set_theme(self._dark)
        self._root.configure(bg=c("bg"))

        # Update ttk styles
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

        if self._current_page and hasattr(self._current_page, "refresh_theme"):
            self._current_page.refresh_theme()


def main():
    root = tk.Tk()
    root.title("LANFXplorer")
    root.geometry("1456x816")
    root.configure(bg=c("bg"))
    root.minsize(800, 500)

    # Set ttk theme
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    api  = ApiClient()
    nav  = Navigator(root, api)

    # Start at login screen
    nav.go("login")

    root.mainloop()


if __name__ == "__main__":
    main()
