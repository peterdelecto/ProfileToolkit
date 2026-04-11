# Material detection, enum handling, scroll binding, color math

from __future__ import annotations

import logging
import re
import tkinter as tk

from .constants import (
    RECOMMENDATIONS,
    ENUM_VALUES,
    _ENUM_JSON_TO_LABEL,
    _KNOWN_VENDORS,
    _PLATFORM,
    _WIN_SCROLL_DELTA_DIVISOR,
    COLOR_LIGHTEN_AMOUNT,
)

logger = logging.getLogger(__name__)


def detect_material(profile_or_data: dict | object) -> str:
    """Normalize material from a Profile or raw data dict (e.g. 'PLA', 'PETG-CF', 'General')."""
    data = getattr(profile_or_data, 'data', profile_or_data)
    if not data:
        return "General"
    ft = data.get("filament_type", "")
    if isinstance(ft, list):
        ft = ft[0] if ft else ""
    ft = str(ft).strip().upper()
    if not ft:
        name = data.get("name", "")
        if isinstance(name, str):
            name_upper = name.upper()
            for mat in ("PLA-CF", "PETG-CF", "PA-CF", "PA6-GF", "PA12-CF",
                        "PLA", "PETG", "ABS", "ASA", "TPU", "PA", "PC"):
                if mat in name_upper:
                    ft = mat
                    break
    # Normalize CF variants
    if "CF" in ft or "GF" in ft:
        if "PLA" in ft:
            return "PLA-CF"
        elif "PETG" in ft:
            return "PETG-CF"
        elif "PA" in ft:
            return "PA-CF"
    # Normalize base materials
    for mat in ("PLA", "PETG", "ABS", "ASA", "TPU", "PC"):
        if mat in ft:
            return mat
    if "PA" in ft or "NYLON" in ft:
        return "PA"
    return "General"


_KEY_ALIASES: dict[str, str] = {
    # Prusa key → Bambu/Orca key (RECOMMENDATIONS use Bambu/Orca names)
    "temperature": "nozzle_temperature",
    "first_layer_temperature": "nozzle_temperature_initial_layer",
    "disable_fan_first_layers": "close_fan_the_first_x_layers",
    "min_fan_speed": "fan_min_speed",
    "max_fan_speed": "fan_max_speed",
    "min_print_speed": "slow_down_min_speed",
    "extrusion_multiplier": "filament_flow_ratio",
    "filament_retract_length": "filament_retraction_length",
    "filament_retract_speed": "filament_retraction_speed",
    "filament_deretract_speed": "filament_deretraction_speed",
    "start_filament_gcode": "filament_start_gcode",
    "end_filament_gcode": "filament_end_gcode",
}


def _resolve_key(key: str) -> str:
    """Return the canonical RECOMMENDATIONS key, checking aliases."""
    if key in RECOMMENDATIONS:
        return key
    return _KEY_ALIASES.get(key, key)


def get_recommendation(key: str, material: str = "General") -> dict | None:
    """Look up min/max/typical/notes for a parameter+material combo, or None."""
    rec = RECOMMENDATIONS.get(_resolve_key(key))
    if not rec:
        return None
    ranges = rec.get("ranges", {})
    return ranges.get(material) or ranges.get("General")


def get_recommendation_info(key: str) -> str | None:
    rec = RECOMMENDATIONS.get(_resolve_key(key))
    return rec.get("info") if rec else None


def check_value_range(key: str, value: float | list | None, material: str = "General") -> str | None:
    """Returns 'low', 'high', 'ok', or None. For lists, checks first element."""
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    try:
        num = float(value)
    except (ValueError, TypeError):
        logger.debug("Could not parse value %r for key %r as float", value, key)
        return None
    rec = get_recommendation(key, material)
    if not rec:
        return None
    low = rec.get("min")
    high = rec.get("max")
    if low is not None and num < low:
        return "low"
    if high is not None and num > high:
        return "high"
    return "ok"


def humanize_enum_value(raw_value: str) -> str:
    """Turn 'monotonicline' into 'Monotonic Line', 'even_odd' into 'Even Odd', etc."""
    raw = str(raw_value)
    raw = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw)   # camelCase split
    raw = re.sub(r'(?<=[a-z])(?=\d)', ' ', raw)
    raw = re.sub(r'(?<=\d)(?=[a-z])', ' ', raw)
    raw = raw.replace('_', ' ').replace('-', ' ')
    parts = re.split(r'(\([^)]*\))', raw)
    result = []
    for part in parts:
        if part.startswith('('):
            inner = part[1:-1].strip().capitalize()
            result.append(f"({inner})")
        else:
            result.append(' '.join(w.capitalize() for w in part.split()))
    return ' '.join(result).strip()


def get_enum_human_label(key: str, raw_value: str | None) -> str:
    """Known label from lookup table, or auto-humanized fallback."""
    if raw_value is None:
        return ""
    s = str(raw_value)
    lookup = _ENUM_JSON_TO_LABEL.get(key)
    if lookup and s in lookup:
        return lookup[s]
    return humanize_enum_value(s)


def bind_scroll(widget: tk.Widget, canvas: tk.Canvas) -> None:
    """Hook up mousewheel events on a widget to scroll a canvas (cross-platform)."""
    is_mac = _PLATFORM == "Darwin"

    def _clamp_scroll(units: int) -> None:
        """Scroll canvas by units, but don't overshoot top or bottom."""
        top, bottom = canvas.yview()
        # Content fits entirely — no scrolling needed
        if top <= 0.0 and bottom >= 1.0:
            return
        if units < 0 and top <= 0.0:
            return
        if units > 0 and bottom >= 1.0:
            return
        canvas.yview_scroll(units, "units")

    def on_wheel(event: tk.Event) -> None:
        if is_mac:
            _clamp_scroll(int(-1 * event.delta * 3))
        else:
            units = round(-1 * event.delta / _WIN_SCROLL_DELTA_DIVISOR)
            if units == 0:
                units = -1 if event.delta > 0 else 1
            _clamp_scroll(units)

    widget.bind("<MouseWheel>", on_wheel)
    widget.bind("<Button-4>", lambda event: _clamp_scroll(-3))
    widget.bind("<Button-5>", lambda event: _clamp_scroll(3))


def lighten_color(hex_color: str, amount: int = COLOR_LIGHTEN_AMOUNT) -> str:
    """Bump each RGB channel by `amount`. Returns original if not 6-digit hex."""
    h = hex_color.lstrip('#')
    if len(h) != 6:
        return hex_color
    r = min(255, int(h[0:2], 16) + amount)
    g = min(255, int(h[2:4], 16) + amount)
    b = min(255, int(h[4:6], 16) + amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def guess_material(name: str) -> str:
    """Detect material type from profile name."""
    n = name.upper()
    for mat in ("PLA-CF", "PETG", "PLA", "ABS", "ASA", "TPU", "PC", "PA", "PVA", "HIPS", "PPS", "PVDF"):
        if mat in n:
            return mat.replace("-CF", " CF")  # normalize compound names
    return ""


def guess_brand(name: str) -> str:
    """Detect brand from profile name."""
    for brand in ("Polymaker", "eSUN", "Hatchbox", "Sunlu", "Prusament",
                   "Bambu", "Overture", "3DJake", "Coex", "addnorth", "OVERTURE"):
        if brand.lower() in name.lower():
            return brand
    return ""


_MACHINE_ALIASES = {
    # Bambu Lab
    "A1": "A1",
    "A1M": "A1 Mini",
    "A1 MINI": "A1 Mini",
    "H2C": "H2C",
    "H2D": "H2D",
    "H2DP": "H2D Pro",
    "H2S": "H2S",
    "X1C": "X1 Carbon",
    "X1E": "X1E",
    "X1": "X1",
    "P1S": "P1S",
    "P1P": "P1P",
    "P2S": "P2S",
    # Prusa
    "PG": "Planetary Gear",
    "PGIS": "Planetary Gear IS",
    "COREONE": "Core One",
    "XL": "XL",
    "XLIS": "XL IS",
    "HT90": "HT90",
    "MINI": "Mini",
    "MINI+": "Mini+",
    "MINIIS": "Mini IS",
    "MMU": "Planetary Gear MMU",
    "MMU1": "MK3 MMU1",
    "MK2": "MK2",
    "MK2S": "MK2S",
    "MK2.5": "MK2.5",
    "MK2.5S": "MK2.5S",
    "MK3": "MK3",
    "MK3S": "MK3S",
    "MK3S+": "MK3S+",
    "MK3.5": "MK3.5",
    "MK3.5S": "MK3.5S",
    "MK4": "MK4",
    "MK4S": "MK4S",
}


def parse_printer_nozzle(raw: str) -> tuple[str, str]:
    """Parse printer + nozzle from '@BBL X1C 0.6 nozzle' or 'COREONE HF0.6' etc.

    Handles BBL, Prusa, and generic formats. Returns (printer, nozzle) tuple.
    """
    import re

    s = raw.strip()
    # Strip leading "@BBL ", "BBL ", "@"
    for prefix in ("@BBL ", "BBL ", "@"):
        if s.upper().startswith(prefix):
            s = s[len(prefix):]
            break

    # Check if string starts with nozzle spec (HF0.6, 0.8, 0.8 nozzle MINI)
    m_nozzle_first = re.match(r"^(HF)?(\d+\.\d+)\s*(?:nozzle)?\s*(.*)", s)
    if m_nozzle_first:
        nozzle = (m_nozzle_first.group(1) or "") + m_nozzle_first.group(2)
        remainder = m_nozzle_first.group(3).strip()
        if remainder:
            key = remainder.upper()
            printer = _MACHINE_ALIASES.get(key, remainder)
        else:
            printer = "Planetary Gear HF" if m_nozzle_first.group(1) else "Planetary Gear"
        return printer, nozzle

    # Extract trailing nozzle: "0.4 nozzle", "HF0.6", "0.6"
    nozzle = ""
    m = re.search(r"\s+(HF)?(\d+\.\d+)\s*(?:nozzle)?$", s)
    if m:
        nozzle = (m.group(1) or "") + m.group(2)
        s = s[: m.start()].strip()
    else:
        # Check for " HF" suffix without digits (Prusa HF variant)
        if s.upper().endswith(" HF"):
            s = s[:-3].strip()
            nozzle = ""
            key = s.upper()
            printer = _MACHINE_ALIASES.get(key, s)
            return printer + " HF", nozzle

    # Expand machine alias
    key = s.strip().upper()
    printer = _MACHINE_ALIASES.get(key, s.strip())
    return printer, nozzle
