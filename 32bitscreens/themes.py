"""
LANFXplorer – Shared Themes
Unified DARK / LIGHT colour palettes for all tkinter screens.

Usage:
    from themes import c, T, DARK, LIGHT, set_theme
    bg = c("bg")
"""

# ═════════════════════════════════════════════════════════════════════════════
# DARK palette
# ═════════════════════════════════════════════════════════════════════════════
DARK = dict(
    # ── global ──
    bg="#18181a",
    text="#e6e6eb",
    subtext="#8c8c96",
    accent="#338fff",
    accent_fg="#ffffff",
    error="#e05555",
    error_border="#cc3333",
    error_bg="#2a1414",
    divider="#2e2e32",
    placeholder="#5a5a62",

    # ── header / topbar ──
    header="#1e1e20",
    header_border="#2e2e32",

    # ── cards ──
    card_bg="#212124",
    card_border="#2e2e32",
    card_hover="#29292d",

    # ── panels (explorer) ──
    panel="#1e1e20",
    panel_top="#242426",

    # ── input fields (login) ──
    field_bg="#252528",
    field_border="#3a3a3e",
    field_focus="#338fff",
    field_error="#cc3333",

    # ── icons ──
    icon_fg="#7aadee",

    # ── buttons ──
    btn="#2e2e32",
    btn_fg="#e6e6eb",
    btn_outline="#3a3a3e",
    btn_outline_fg="#8c8c96",
    btn_hover_fg="#e6e6eb",

    # ── status ──
    online="#4caf82",
    offline="#cc4444",

    # ── sign-out button ──
    signout_bg="#cc3333",
    signout_fg="#ffffff",

    # ── tree / file list ──
    selected="#1e4080",
    row_hover="#2a2a2e",

    # ── transfers ──
    transfer_bg="#202024",
    progress_bg="#38383c",
    progress_fill="#338fff",

    # ── misc ──
    scrollbar="#3a3a3e",
    scan_dot="#338fff",
)


# ═════════════════════════════════════════════════════════════════════════════
# LIGHT palette
# ═════════════════════════════════════════════════════════════════════════════
LIGHT = dict(
    # ── global ──
    bg="#f0f0f4",
    text="#111118",
    subtext="#66666e",
    accent="#1a5acc",
    accent_fg="#ffffff",
    error="#cc2222",
    error_border="#cc2222",
    error_bg="#ffeaea",
    divider="#dddde8",
    placeholder="#aaaabc",

    # ── header / topbar ──
    header="#ffffff",
    header_border="#dddde8",

    # ── cards ──
    card_bg="#ffffff",
    card_border="#dddde8",
    card_hover="#f4f4f8",

    # ── panels (explorer) ──
    panel="#ffffff",
    panel_top="#f0f0f5",

    # ── input fields (login) ──
    field_bg="#ffffff",
    field_border="#ccccda",
    field_focus="#1a5acc",
    field_error="#cc2222",

    # ── icons ──
    icon_fg="#2255aa",

    # ── buttons ──
    btn="#dedee8",
    btn_fg="#111118",
    btn_outline="#ccccda",
    btn_outline_fg="#66666e",
    btn_hover_fg="#111118",

    # ── status ──
    online="#2e8b57",
    offline="#cc2222",

    # ── sign-out button ──
    signout_bg="#b01818",
    signout_fg="#ffffff",

    # ── tree / file list ──
    selected="#b3d4ff",
    row_hover="#e8e8f0",

    # ── transfers ──
    transfer_bg="#f2f2f5",
    progress_bg="#ccccda",
    progress_fill="#1a5acc",

    # ── misc ──
    scrollbar="#bbbbcc",
    scan_dot="#1a5acc",
)


# ── Active theme (module-level mutable) ─────────────────────────────────────
T = DARK
_is_dark = True


def c(key):
    """Colour lookup against the active theme."""
    return T[key]


def is_dark():
    return _is_dark


def set_theme(dark: bool):
    """Switch to dark or light theme.  Returns the new palette dict."""
    global T, _is_dark
    _is_dark = dark
    T = DARK if dark else LIGHT
    return T
