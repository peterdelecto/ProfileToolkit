# Reusable UI widgets

from __future__ import annotations

import logging
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox
from typing import Callable, Optional, Any, Dict, Tuple, Union
from urllib.parse import urlparse

from .constants import (
    _PLATFORM,
    _NOZZLE_SIZES,
    _ALL_BBL_PRINTERS,
    _KNOWN_PRINTERS,
    _WIN_SCROLL_DELTA_DIVISOR,
    TOOLTIP_DELAY_MS,
    UI_FONT,
    RECOMMENDATIONS,
    MAX_POPUP_SOURCES,
)
from .theme import Theme
from .utils import (
    bind_scroll,
    lighten_color,
    get_recommendation,
    get_recommendation_info,
    check_value_range,
    _resolve_key,
)

logger = logging.getLogger(__name__)


class Tooltip:
    """Lightweight hover tooltip for any widget.

    Displays a styled tooltip window when the user hovers over a widget.
    Automatically dismisses on mouse leave, button click, or when the app
    loses focus (macOS behavior to prevent stealing focus).

    Args:
        widget: The tkinter widget to attach the tooltip to.
        text: The tooltip text to display.
        delay: Delay in milliseconds before showing the tooltip (default: 500ms).
    """

    def __init__(
        self,
        widget: tk.Widget,
        text: str,
        delay: int = TOOLTIP_DELAY_MS,
        theme: "Theme | None" = None,
    ) -> None:
        self.widget: tk.Widget = widget
        self.text: str = text
        self.delay: int = delay
        self._theme = theme
        self._tip: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        widget.bind("<Button>", self._cancel, add="+")

    def _schedule(self, event: Optional[tk.Event] = None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self, event: Optional[tk.Event] = None) -> None:
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self._tip:
            self._tip.destroy()
            self._tip = None

    def _show(self) -> None:
        if not self.text:
            return
        if self._theme is None:
            return
        try:
            if not self.widget.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            if not self.widget.winfo_toplevel().focus_displayof():
                return
        except (tk.TclError, AttributeError):
            pass
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except tk.TclError:
            return
        self._tip = tooltip_window = tk.Toplevel(self.widget)
        tooltip_window.wm_overrideredirect(True)
        tooltip_window.wm_geometry(f"+{x}+{y}")
        t = self._theme
        popup_bg = t.bg4
        popup_fg = t.fg
        popup_border = t.border
        lbl = tk.Label(
            tooltip_window,
            text=self.text,
            bg=popup_bg,
            fg=popup_fg,
            font=(UI_FONT, 12),
            padx=8,
            pady=4,
            relief="solid",
            bd=1,
            borderwidth=1,
            highlightbackground=popup_border,
        )
        lbl.pack()

    def update_text(self, text: str) -> None:
        self.text = text


class InfoPopup:
    """Click-triggered info popup for parameter recommendations.

    Shows material-specific ranges and general info in a styled popup.
    Only one popup can be active at a time; opening a new popup automatically
    dismisses any existing one.

    Args:
        widget: The tkinter widget to attach the popup trigger to.
        key: The parameter key for looking up recommendations.
        material: The material name for material-specific range display (default: "General").
    """

    _active_popup: Optional[InfoPopup] = None  # Class-level: only one popup at a time

    def __init__(
        self,
        widget: tk.Widget,
        key: str,
        material: str = "General",
        theme: "Theme | None" = None,
    ) -> None:
        self.widget: tk.Widget = widget
        self.key: str = key
        self.material: str = material
        self._theme = theme
        self._popup: Optional[tk.Toplevel] = None
        self._root_click_binding: str | None = None
        widget.bind("<Button-1>", self._toggle, add="+")

    def _toggle(self, event: Optional[tk.Event] = None) -> None:
        if self._popup:
            self._dismiss()
            return
        if InfoPopup._active_popup and InfoPopup._active_popup is not self:
            InfoPopup._active_popup._dismiss()
        self._show()

    def _dismiss(self, event: Optional[tk.Event] = None) -> None:
        try:
            if self._popup:
                self._popup.destroy()
                self._popup = None
        except tk.TclError:
            pass
        finally:
            if self._root_click_binding:
                try:
                    self.widget.winfo_toplevel().unbind(
                        "<Button-1>", self._root_click_binding
                    )
                except tk.TclError:
                    pass
                self._root_click_binding = None
            if InfoPopup._active_popup is self:
                InfoPopup._active_popup = None

    def _build_info_section(
        self, content: tk.Frame, rec: Dict[str, Any], popup_bg: str, popup_fg: str
    ) -> None:
        """Build the general info text label section."""
        info_text = rec.get("info", "")
        if info_text:
            info_lbl = tk.Label(
                content,
                text=info_text,
                bg=popup_bg,
                fg=popup_fg,
                font=(UI_FONT, 12),
                wraplength=380,
                justify="left",
                anchor="w",
            )
            info_lbl.pack(anchor="w", pady=(0, 6))

    def _build_range_section(
        self,
        content: tk.Frame,
        mat_range: Dict[str, Any],
        ranges: Dict[str, Any],
        popup_bg: str,
        popup_fg: str,
        popup_fg3: str,
        range_bg: str,
        popup_border: str,
        rec_fg: str,
        note_fg: str,
    ) -> None:
        """Build the material-specific range and other materials summary section."""
        if mat_range:
            mat_display = (
                self.material if self.material != "General" else "All materials"
            )
            range_frame = tk.Frame(
                content,
                bg=range_bg,
                highlightbackground=popup_border,
                highlightthickness=1,
            )
            range_frame.pack(fill="x", pady=(2, 0))
            inner = tk.Frame(range_frame, bg=range_bg, padx=8, pady=6)
            inner.pack(fill="x")

            tk.Label(
                inner,
                text=f"Recommended for {mat_display}:",
                bg=range_bg,
                fg=rec_fg,
                font=(UI_FONT, 12, "bold"),
                anchor="w",
            ).pack(anchor="w")

            range_parts = []
            if "min" in mat_range and "max" in mat_range:
                range_parts.append(f"Range: {mat_range['min']} – {mat_range['max']}")
            if "typical" in mat_range:
                range_parts.append(f"Typical: {mat_range['typical']}")
            if range_parts:
                tk.Label(
                    inner,
                    text="  ·  ".join(range_parts),
                    bg=range_bg,
                    fg=popup_fg,
                    font=(UI_FONT, 12),
                    anchor="w",
                ).pack(anchor="w", pady=(2, 0))

            notes = mat_range.get("notes")
            if notes:
                tk.Label(
                    inner,
                    text=notes,
                    bg=range_bg,
                    fg=note_fg,
                    font=(UI_FONT, 12, "bold italic"),
                    anchor="w",
                    wraplength=360,
                ).pack(anchor="w", pady=(2, 0))

        # If there are other material ranges, show a compact summary
        other_mats = {
            k: v for k, v in ranges.items() if k != self.material and k != "General"
        }
        if other_mats:
            sep = tk.Frame(content, bg=popup_border, height=1)
            sep.pack(fill="x", pady=(8, 4))
            tk.Label(
                content,
                text="Other materials:",
                bg=popup_bg,
                fg=popup_fg3,
                font=(UI_FONT, 12),
                anchor="w",
            ).pack(anchor="w")
            summary_parts = []
            for mat, rng in sorted(other_mats.items()):
                _t = rng.get("typical", "")
                if _t:
                    summary_parts.append(f"{mat}: {_t}")
            if summary_parts:
                # Show in rows of 3
                for i in range(0, len(summary_parts), 3):
                    row_text = "  ·  ".join(summary_parts[i : i + 3])
                    tk.Label(
                        content,
                        text=row_text,
                        bg=popup_bg,
                        fg=popup_fg3,
                        font=(UI_FONT, 12),
                        anchor="w",
                    ).pack(anchor="w")

    def _build_sources_section(
        self,
        content: tk.Frame,
        rec: Dict[str, Any],
        mat_range: Optional[Dict[str, Any]],
        popup_bg: str,
        popup_fg3: str,
        popup_border: str,
        link_fg: str,
    ) -> None:
        """Build the sources links section.

        Source priority: material-specific sources are shown when available.
        Top-level (parameter-wide) sources are only used as fallback when the
        active material has no dedicated sources.
        """
        _all_sources = []
        _seen_urls: set[str] = set()
        # Material-specific sources first (higher priority)
        if mat_range and mat_range.get("sources"):
            for src in mat_range["sources"]:
                if src["url"] not in _seen_urls:
                    _all_sources.append(src)
                    _seen_urls.add(src["url"])
        # Top-level sources ONLY when no material-specific sources exist
        if not _all_sources and rec.get("sources"):
            for src in rec["sources"]:
                if src["url"] not in _seen_urls:
                    _all_sources.append(src)
                    _seen_urls.add(src["url"])
        # If more than 5, pick the most diverse set by domain
        if len(_all_sources) > MAX_POPUP_SOURCES:
            sources_to_show = []
            _used_domains: dict[str, int] = {}
            # Pass 1: one source per unique domain
            for src in _all_sources:
                domain = urlparse(src["url"]).netloc.lower()
                if domain not in _used_domains:
                    sources_to_show.append(src)
                    _used_domains[domain] = 1
                    if len(sources_to_show) >= MAX_POPUP_SOURCES:
                        break
            # Pass 2: fill remaining slots from least-represented domains
            if len(sources_to_show) < MAX_POPUP_SOURCES:
                for src in _all_sources:
                    if src in sources_to_show:
                        continue
                    domain = urlparse(src["url"]).netloc.lower()
                    sources_to_show.append(src)
                    _used_domains[domain] = _used_domains.get(domain, 0) + 1
                    if len(sources_to_show) >= MAX_POPUP_SOURCES:
                        break
        else:
            sources_to_show = _all_sources
        if sources_to_show:
            sep2 = tk.Frame(content, bg=popup_border, height=1)
            sep2.pack(fill="x", pady=(8, 4))
            tk.Label(
                content,
                text="Sources:",
                bg=popup_bg,
                fg=popup_fg3,
                font=(UI_FONT, 12),
                anchor="w",
            ).pack(anchor="w")
            for src in sources_to_show:
                link = tk.Label(
                    content,
                    text=f"\u2197 {src['label']}",
                    bg=popup_bg,
                    fg=link_fg,
                    font=(UI_FONT, 12, "underline"),
                    cursor="pointinghand",
                    anchor="w",
                )
                link.pack(anchor="w", padx=(8, 0))
                link.bind("<Button-1>", lambda e, u=src["url"]: webbrowser.open(u))

    def _show(self) -> None:
        """Display the info popup with recommendations.

        Orchestrates popup creation and calls helper methods to build sections:
        - General info text about the parameter
        - Material-specific range recommendations
        - Other material ranges in a compact summary
        - Sources for the recommendations
        """
        rec = RECOMMENDATIONS.get(_resolve_key(self.key))
        if not rec:
            return
        ranges = rec.get("ranges", {})
        mat_range = ranges.get(self.material) or ranges.get("General")

        InfoPopup._active_popup = self

        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4

        theme = self._theme
        popup_bg = theme.bg4
        popup_border = theme.border
        popup_fg = theme.fg
        popup_fg3 = theme.fg3
        range_bg = theme.bg3
        rec_fg = theme.recommended
        note_fg = theme.note
        link_fg = theme.accent

        self._popup = popup = tk.Toplevel(self.widget)
        popup.wm_overrideredirect(True)
        popup.configure(
            bg=popup_bg, highlightbackground=popup_border, highlightthickness=1
        )

        # Content frame
        content = tk.Frame(popup, bg=popup_bg, padx=12, pady=10)
        content.pack(fill="both", expand=True)

        # Build popup sections
        self._build_info_section(content, rec, popup_bg, popup_fg)
        self._build_range_section(
            content,
            mat_range,
            ranges,
            popup_bg,
            popup_fg,
            popup_fg3,
            range_bg,
            popup_border,
            rec_fg,
            note_fg,
        )
        self._build_sources_section(
            content, rec, mat_range, popup_bg, popup_fg3, popup_border, link_fg
        )

        # Position popup — clamp to screen
        popup.update_idletasks()
        popup_width = popup.winfo_reqwidth()
        popup_height = popup.winfo_reqheight()
        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        if x + popup_width > screen_width:
            x = screen_width - popup_width - 10
        if y + popup_height > screen_height:
            y = self.widget.winfo_rooty() - popup_height - 4
        popup.wm_geometry(f"+{x}+{y}")

        # Dismiss on click outside or Escape
        popup.bind("<Escape>", self._dismiss)
        popup.bind("<FocusOut>", self._dismiss)
        # Also dismiss if user clicks anywhere else (delayed to not catch our own click)
        self._root_click_binding = self.widget.winfo_toplevel().bind(
            "<Button-1>", self._on_root_click, add="+"
        )

    def _on_root_click(self, event: tk.Event) -> None:
        if not self._popup:
            return
        try:
            px = self._popup.winfo_rootx()
            py = self._popup.winfo_rooty()
            pw = self._popup.winfo_width()
            ph = self._popup.winfo_height()
            if not (px <= event.x_root <= px + pw and py <= event.y_root <= py + ph):
                wx = self.widget.winfo_rootx()
                wy = self.widget.winfo_rooty()
                ww = self.widget.winfo_width()
                wh = self.widget.winfo_height()
                if wx <= event.x_root <= wx + ww and wy <= event.y_root <= wy + wh:
                    return
                self._dismiss()
        except tk.TclError:
            pass

    def update_material(self, material: str) -> None:
        self.material = material


class ScrollableFrame(tk.Frame):
    """Reusable scrollable frame with automatic scrolling.

    Wraps the Canvas+Scrollbar+inner-Frame boilerplate into a single reusable widget.
    The inner scrollable area is available via the `body` attribute.

    Usage:
        sf = ScrollableFrame(parent, bg=theme.bg3)
        sf.pack(fill="both", expand=True)
        # Add widgets to sf.body (the inner scrollable frame)
        tk.Label(sf.body, text="Hello").pack()

    Args:
        parent: Parent tkinter widget.
        bg: Background color (default: "#2D2D31").
        highlight_border: Optional border color; if provided, adds a 1px border.
        **kwargs: Additional keyword arguments passed to tk.Frame.
    """

    def __init__(
        self,
        parent: tk.Widget,
        bg: Optional[str] = None,
        highlight_border: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize scrollable frame with canvas and scrollbar.

        Args:
            parent: Parent widget.
            bg: Background color (defaults to Theme().bg if not provided).
            highlight_border: Optional border highlight color.
            **kwargs: Additional frame keyword arguments.
        """
        if bg is None:
            bg = "#2D2D31"  # Theme.bg default — avoids instantiating Theme()
        super().__init__(parent, bg=bg, **kwargs)
        if highlight_border:
            self.configure(highlightbackground=highlight_border, highlightthickness=1)
        self.canvas: tk.Canvas = tk.Canvas(
            self, bg=bg, highlightthickness=0, yscrollincrement=4
        )
        self._scrollbar: ttk.Scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.body: tk.Frame = tk.Frame(self.canvas, bg=bg)
        self.body.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self._canvas_window: int = self.canvas.create_window(
            (0, 0), window=self.body, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=self._scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")
        # Auto-resize inner frame to canvas width
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self._canvas_window, width=e.width),
        )
        # Bind mousewheel scrolling
        bind_scroll(self.canvas, self.canvas)

    def bind_scroll_recursive(self) -> None:
        def _recurse(widget: tk.Widget) -> None:
            bind_scroll(widget, self.canvas)
            for child in widget.winfo_children():
                _recurse(child)

        _recurse(self.body)


def make_btn(
    parent: tk.Widget,
    text: str,
    command: Callable[[], None],
    bg: str,
    fg: str,
    font: Union[Tuple[str, int], Tuple[str, int, str]] = (UI_FONT, 12),
    padx: int = 10,
    pady: int = 4,
    image: Optional[Any] = None,
    compound: str = "left",
    **kw: Any,
) -> tk.Frame:
    """Create a Label-based button with hover color lightening.

    macOS ignores bg/fg on tk.Button; Labels respect them and we bind click
    events manually. This provides a cross-platform button with hover effects.

    Args:
        parent: Parent widget to contain the button.
        text: Button label text.
        command: Callable to invoke when button is clicked.
        bg: Background color.
        fg: Foreground (text) color.
        font: Font tuple (family, size) or (family, size, style).
        padx: Horizontal padding in pixels.
        pady: Vertical padding in pixels.
        image: Optional tk.PhotoImage to display alongside text.
        compound: How to compound image and text ("left", "right", "top", "bottom").
        **kw: Additional keyword arguments (currently unused).

    Returns:
        A tk.Frame containing the label-based button. The frame can be used
        like a normal widget and has a `configure` method that proxies to
        the inner label for convenience.
    """
    state = {"bg": bg}

    wrapper = tk.Frame(
        parent,
        bg=bg,
        highlightthickness=1,
        highlightbackground=bg,
        highlightcolor=fg,
        takefocus=True,
    )
    lbl_kw: Dict[str, Any] = dict(
        text=text,
        bg=bg,
        fg=fg,
        font=font,
        padx=padx,
        pady=pady,
        highlightthickness=0,
    )
    if image is not None:
        lbl_kw["image"] = image
        lbl_kw["compound"] = compound
    lbl = tk.Label(wrapper, **lbl_kw)
    lbl.pack(side="top")

    def _on_click(e: tk.Event) -> None:
        command()

    lbl.bind("<Button-1>", _on_click)
    wrapper.bind("<Button-1>", lambda e: None)  # absorb click, label handler fires
    wrapper.bind("<Return>", lambda e: command() if command else None)
    wrapper.bind("<space>", lambda e: command() if command else None)

    def _on_btn_enter(e: tk.Event) -> None:
        lit = lighten_color(state["bg"])
        lbl.configure(bg=lit)
        _orig_configure(bg=lit)

    def _on_btn_leave(e: tk.Event) -> None:
        lbl.configure(bg=state["bg"])
        _orig_configure(bg=state["bg"])

    lbl.bind("<Enter>", _on_btn_enter)
    lbl.bind("<Leave>", _on_btn_leave)
    wrapper.bind("<Enter>", _on_btn_enter)
    wrapper.bind("<Leave>", _on_btn_leave)

    wrapper._inner_label = lbl  # type: ignore
    _orig_configure = wrapper.configure

    def _proxy_configure(**kwargs: Any) -> None:
        """Route configure() to both wrapper Frame and inner Label.

        macOS tk.Button renders with a system chrome bezel that ignores
        bg/fg, so make_btn uses a Frame+Label pair instead.  This proxy
        lets callers treat the wrapper like a normal widget — label keys
        (fg, text, font, ...) go to the Label while frame keys go to the
        wrapper, keeping both in sync.
        """
        label_keys = {
            "fg",
            "bg",
            "font",
            "text",
            "cursor",
            "image",
            "compound",
            "state",
        }
        lbl_kw_new = {k: v for k, v in kwargs.items() if k in label_keys}
        wrap_kw = {k: v for k, v in kwargs.items() if k not in label_keys}
        if "bg" in kwargs:
            wrap_kw["bg"] = kwargs["bg"]
            state["bg"] = kwargs["bg"]
        if lbl_kw_new:
            lbl.configure(**lbl_kw_new)
        if wrap_kw:
            _orig_configure(**wrap_kw)

    wrapper.configure = _proxy_configure  # type: ignore
    wrapper.config = _proxy_configure  # type: ignore
    return wrapper


class ExportDialog(tk.Toplevel):
    """Dialog shown before export. Offers file export and slicer quick-install.

    This dialog appears when the user initiates a profile export. It allows them to:
    - Export directly to a detected slicer's preset folder
    - Export to a file

    All exports are automatically flattened (inherited parameters included).

    Args:
        parent: Parent window.
        theme: Theme object containing color scheme.
        count: Number of profiles being exported (for plural display).
        detected_slicers: Dict mapping slicer name -> path to installation.
    """

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        count: int = 1,
        detected_slicers: Optional[Dict[str, str]] = None,
        default_format: str = "json",
    ) -> None:
        """Initialize export dialog.

        Args:
            parent: Parent window.
            theme: Theme for dialog styling.
            count: Number of profiles to export.
            detected_slicers: Detected slicer installations.
            default_format: Pre-selected format ("json" or "ini"), auto-detected from profile origin.
        """
        super().__init__(parent)
        self.theme: Theme = theme
        self.result: Optional[str] = None  # "file" for save-to-file, or None for cancel
        self.flatten: bool = True
        self.export_format: str = default_format
        self.slicer_target: Optional[Tuple[str, str]] = (
            None  # (name, path) if installing to slicer
        )
        self._detected_slicers: Dict[str, str] = detected_slicers or {}
        self.title("Export Profiles")
        self.configure(bg=theme.bg)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 80, parent.winfo_rooty() + 80))
        self._build(count)
        self.wait_window()

    def _build(self, count: int) -> None:
        theme = self.theme
        tk.Label(
            self,
            text=f"Export {count} profile{'s' if count != 1 else ''}",
            font=(UI_FONT, 14, "bold"),
            bg=theme.bg,
            fg=theme.fg,
        ).pack(pady=(16, 8), padx=20)

        # Options frame
        opts = tk.Frame(self, bg=theme.bg)
        opts.pack(fill="x", padx=20, pady=8)

        tk.Label(
            opts,
            text="All inherited parameters will be included in the export.",
            bg=theme.bg,
            fg=theme.fg2,
            font=(UI_FONT, 12, "italic"),
            justify="left",
        ).pack(anchor="w", padx=8, pady=4)

        # Format selection
        fmt_frame = tk.Frame(opts, bg=theme.bg)
        fmt_frame.pack(anchor="w", padx=8, pady=(8, 0))
        tk.Label(
            fmt_frame, text="Format:", bg=theme.bg, fg=theme.fg, font=(UI_FONT, 12)
        ).pack(side="left", padx=(0, 8))
        self._fmt_var = tk.StringVar(value=default_format)
        for fmt_val, fmt_label in [("json", "JSON"), ("ini", "INI (PrusaSlicer)")]:
            tk.Radiobutton(
                fmt_frame,
                text=fmt_label,
                variable=self._fmt_var,
                value=fmt_val,
                bg=theme.bg,
                fg=theme.fg,
                selectcolor=theme.bg,
                activebackground=theme.bg,
                activeforeground=theme.fg,
                font=(UI_FONT, 12),
            ).pack(side="left", padx=(0, 12))

        if self._detected_slicers:
            sep = tk.Frame(self, bg=theme.border, height=1)
            sep.pack(fill="x", padx=20, pady=(12, 0))

            tk.Label(
                self,
                text="Or export directly to a slicer's user preset folder:",
                font=(UI_FONT, 12),
                bg=theme.bg,
                fg=theme.fg2,
            ).pack(anchor="w", padx=20, pady=(10, 6))

            slicer_row = tk.Frame(self, bg=theme.bg)
            slicer_row.pack(fill="x", padx=20, pady=(0, 4))
            from .models import SlicerDetector

            for name, path in self._detected_slicers.items():
                try:
                    dest_dir = SlicerDetector.get_export_dir(path)
                except OSError as e:
                    logger.error(f"Failed to get slicer export dir for {name}: {e}")
                    continue
                make_btn(
                    slicer_row,
                    f"Export to {name}",
                    lambda n=name, p=path: self._install_to_slicer(n, p),
                    bg=theme.bg4,
                    fg=theme.fg,
                    font=(UI_FONT, 12),
                    padx=12,
                    pady=5,
                ).pack(side="left", padx=(0, 6))
            if len(self._detected_slicers) == 1:
                name, path = list(self._detected_slicers.items())[0]
                try:
                    dest = SlicerDetector.get_export_dir(path)
                    tk.Label(
                        self, text=dest, bg=theme.bg, fg=theme.fg3, font=(UI_FONT, 12)
                    ).pack(anchor="w", padx=28, pady=(0, 4))
                except OSError as e:
                    logger.error(f"Failed to show slicer path for {name}: {e}")

            sep2 = tk.Frame(self, bg=theme.border, height=1)
            sep2.pack(fill="x", padx=20, pady=(8, 0))

        button_frame = tk.Frame(self, bg=theme.bg)
        button_frame.pack(fill="x", padx=20, pady=(12, 16))

        make_btn(
            button_frame,
            "Export to File...",
            self._ok,
            bg=theme.accent2,
            fg=theme.accent_fg,
            font=(UI_FONT, 12, "bold"),
            padx=16,
            pady=5,
        ).pack(side="right", padx=(4, 0))
        make_btn(
            button_frame,
            "Cancel",
            self._cancel,
            bg=theme.bg3,
            fg=theme.fg3,
            font=(UI_FONT, 12),
            padx=12,
            pady=5,
        ).pack(side="right")

    def _ok(self) -> None:
        self.result = "file"
        self.export_format = self._fmt_var.get()
        self.destroy()

    def _install_to_slicer(self, name: str, path: str) -> None:
        self.result = "slicer"
        self.slicer_target = (name, path)
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class UnlockDialog(tk.Toplevel):
    """Dialog for unlocking profiles to work across different printer models.

    Allows users to either:
    - Make profiles universal (work with any printer)
    - Assign profiles to specific printer models with nozzle sizes

    Args:
        parent: Parent window.
        theme: Theme object containing color scheme.
        count: Number of profiles being unlocked.
    """

    def __init__(self, parent: tk.Widget, theme: Theme, count: int = 1) -> None:
        """Initialize unlock dialog.

        Args:
            parent: Parent window.
            theme: Theme for dialog styling.
            count: Number of profiles to unlock.
        """
        super().__init__(parent)
        self.theme: Theme = theme
        self.result: Optional[Any] = None
        self.title("Make Universal")
        self.configure(bg=theme.bg)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        self._build(count)
        self.wait_window()

    def _build(self, count: int) -> None:
        theme = self.theme
        tk.Label(
            self,
            text=f"Make {count} {'profile' if count == 1 else 'profiles'} universal",
            font=(UI_FONT, 14, "bold"),
            bg=theme.bg,
            fg=theme.fg,
        ).pack(pady=(16, 8), padx=16)

        note_frame = tk.Frame(
            self,
            bg=theme.bg3,
            highlightbackground=theme.border,
            highlightthickness=1,
        )
        note_frame.pack(fill="x", padx=16, pady=(0, 8))
        note_icon = tk.Label(
            note_frame, text="\u2139", bg=theme.bg3, fg=theme.info, font=(UI_FONT, 14)
        )
        note_icon.pack(side="left", padx=(10, 6), pady=8)
        note_text_frame = tk.Frame(note_frame, bg=theme.bg3)
        note_text_frame.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=8)
        tk.Label(
            note_text_frame,
            text="Only changes printer compatibility — your print settings stay the same.",
            bg=theme.bg3,
            fg=theme.fg,
            font=(UI_FONT, 12, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            note_text_frame,
            text=(
                "Settings like print speed or acceleration for the "
                "target printer won't be automatically tuned. "
                "After unlocking, check those values for your machine."
            ),
            bg=theme.bg3,
            fg=theme.fg2,
            font=(UI_FONT, 12, "italic"),
            wraplength=380,
            justify="left",
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        self.mode: tk.StringVar = tk.StringVar(value="universal")
        mode_frame = tk.Frame(self, bg=theme.bg)
        mode_frame.pack(fill="x", padx=16, pady=8)

        tk.Radiobutton(
            mode_frame,
            text="Make universal (works with any printer)",
            variable=self.mode,
            value="universal",
            bg=theme.bg,
            fg=theme.fg,
            selectcolor=theme.bg3,
            activebackground=theme.bg,
            activeforeground=theme.fg,
            command=self._mode_changed,
        ).pack(anchor="w", padx=12, pady=6)
        tk.Radiobutton(
            mode_frame,
            text="Assign to specific printer(s):",
            variable=self.mode,
            value="retarget",
            bg=theme.bg,
            fg=theme.fg,
            selectcolor=theme.bg3,
            activebackground=theme.bg,
            activeforeground=theme.fg,
            command=self._mode_changed,
        ).pack(anchor="w", padx=12, pady=6)

        self.printer_frame: tk.Frame = tk.Frame(self, bg=theme.bg)
        self.printer_frame.pack(fill="both", expand=True, padx=32, pady=(0, 8))

        # Search filter for printer list
        self._printer_search_var = tk.StringVar()
        search_row = tk.Frame(self.printer_frame, bg=theme.bg)
        search_row.pack(fill="x", pady=(0, 4))
        tk.Label(
            search_row,
            text="Filter:",
            bg=theme.bg,
            fg=theme.fg3,
            font=(UI_FONT, 11),
        ).pack(side="left")
        printer_search = tk.Entry(
            search_row,
            textvariable=self._printer_search_var,
            bg=theme.bg3,
            fg=theme.fg,
            insertbackground=theme.fg,
            font=(UI_FONT, 11),
            width=20,
        )
        printer_search.pack(side="left", padx=(4, 0), fill="x", expand=True)
        self._printer_search_var.trace_add("write", lambda *_: self._filter_printers())

        list_frame = tk.Frame(
            self.printer_frame,
            bg=theme.bg3,
            highlightbackground=theme.border,
            highlightthickness=1,
        )
        list_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(
            list_frame, bg=theme.bg3, highlightthickness=0, width=380, height=200
        )
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.check_frame: tk.Frame = tk.Frame(canvas, bg=theme.bg3)
        self.check_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.check_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.pvars: Dict[str, tk.BooleanVar] = {}
        for manufacturer, models in _KNOWN_PRINTERS.items():
            tk.Label(
                self.check_frame,
                text=manufacturer,
                font=(UI_FONT, 12, "bold"),
                bg=theme.bg3,
                fg=theme.fg2,
            ).pack(anchor="w", padx=8, pady=(8, 2))
            for model in models:
                for nz in _NOZZLE_SIZES:
                    printer_nozzle_name = f"{model} {nz} nozzle"
                    v: tk.BooleanVar = tk.BooleanVar(value=False)
                    self.pvars[printer_nozzle_name] = v
                    tk.Checkbutton(
                        self.check_frame,
                        text=printer_nozzle_name,
                        variable=v,
                        bg=theme.bg3,
                        fg=theme.fg,
                        selectcolor=theme.bg4,
                        activebackground=theme.bg3,
                        activeforeground=theme.fg,
                    ).pack(anchor="w", padx=24)

        # Bind mousewheel scroll on all children of the scrollable canvas
        for child in self.check_frame.winfo_children():
            bind_scroll(child, canvas)
        bind_scroll(self.check_frame, canvas)
        bind_scroll(canvas, canvas)

        tk.Label(
            self.printer_frame,
            text="Type a printer name:",
            bg=theme.bg,
            fg=theme.fg2,
            font=(UI_FONT, 12),
        ).pack(anchor="w", pady=(8, 2))
        self.custom: tk.Entry = tk.Entry(
            self.printer_frame,
            bg=theme.bg3,
            fg=theme.fg,
            insertbackground=theme.fg,
            highlightbackground=theme.border,
            highlightthickness=1,
            font=(UI_FONT, 12),
        )
        self.custom.pack(fill="x", pady=(0, 8))
        # Placeholder text
        self._placeholder = "e.g. Bambu Lab P1S, Prusa MK4"
        self.custom.insert(0, self._placeholder)
        self.custom.configure(fg=theme.fg3)
        self.custom.bind("<FocusIn>", self._clear_placeholder)
        self.custom.bind("<FocusOut>", self._restore_placeholder)
        self._set_state("disabled")

        button_frame = tk.Frame(self, bg=theme.bg)
        button_frame.pack(fill="x", padx=16, pady=(8, 16))
        cancel_btn = make_btn(
            button_frame,
            "Cancel",
            self._cancel,
            bg=theme.btn_bg,
            fg=theme.btn_fg,
            padx=20,
            pady=6,
        )
        cancel_btn.pack(side="right", padx=(8, 0))
        unlock_btn = make_btn(
            button_frame,
            "Make Universal",
            self._unlock,
            bg=theme.accent,
            fg=theme.accent_fg,
            font=(UI_FONT, 12, "bold"),
            padx=20,
            pady=6,
        )
        unlock_btn.pack(side="right")

    def _filter_printers(self) -> None:
        """Show/hide printer checkboxes based on search text."""
        query = self._printer_search_var.get().lower()
        for w in self.check_frame.winfo_children():
            if isinstance(w, tk.Checkbutton):
                text = w.cget("text").lower()
                if query and query not in text:
                    w.pack_forget()
                else:
                    w.pack(anchor="w", padx=24)

    def _mode_changed(self) -> None:
        self._set_state("normal" if self.mode.get() == "retarget" else "disabled")

    def _clear_placeholder(self, _event: object = None) -> None:
        if self.custom.get() == self._placeholder:
            self.custom.delete(0, "end")
            self.custom.configure(fg=self.theme.fg)

    def _restore_placeholder(self, _event: object = None) -> None:
        if not self.custom.get().strip():
            self.custom.delete(0, "end")
            self.custom.insert(0, self._placeholder)
            self.custom.configure(fg=self.theme.fg3)

    def _set_state(self, state: str) -> None:
        for w in self.check_frame.winfo_children():
            if isinstance(w, tk.Checkbutton):
                w.configure(state=state)
        self.custom.configure(state=state)

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    def _unlock(self) -> None:
        if self.mode.get() == "universal":
            self.result = "universal"
        else:
            sel = [n for n, v in self.pvars.items() if v.get()]
            c = self.custom.get().strip()
            if c and c != self._placeholder:
                custom_entries = [p.strip() for p in c.split(",") if p.strip()]
                # Validate custom entries have reasonable format
                bad = [e for e in custom_entries if len(e) < 2 or len(e) > 100]
                if bad:
                    messagebox.showwarning(
                        "Invalid Printer Name",
                        f"These entries seem invalid:\n{', '.join(bad)}\n\n"
                        "Printer names should be 2–100 characters.",
                        parent=self,
                    )
                    return
                sel.extend(custom_entries)
            if not sel:
                messagebox.showwarning(
                    "No Printers",
                    "Select at least one printer.",
                    parent=self,
                )
                return
            self.result = sel
        self.destroy()
