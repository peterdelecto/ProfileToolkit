# Layout definitions, enum maps, recommendation ranges, named constants

import platform

# --- Application & Platform Identification ---

APP_NAME = "ProfileToolkit"
APP_VERSION = "2.2.0"

# Cross-platform UI font family
_PLATFORM = platform.system()
if _PLATFORM == "Darwin":
    UI_FONT = "SF Pro"  # San Francisco (macOS 10.11+)
elif _PLATFORM == "Windows":
    UI_FONT = "Segoe UI"  # Windows Vista+
else:
    UI_FONT = "DejaVu Sans"  # Widely available on Linux

# --- UI Geometry Constants ---
_WIN_WIDTH = 1300
_WIN_HEIGHT = 780
_DLG_COMPARE_WIDTH = 960
_DLG_COMPARE_HEIGHT = 650
_DLG_COMPARE_MIN_WIDTH = 750
_DLG_COMPARE_MIN_HEIGHT = 450
_TREE_ROW_HEIGHT = 26
_VALUE_TRUNCATE_SHORT = 40  # CompareDialog._fmt
_VALUE_TRUNCATE_LONG = 80  # ProfileDetailPanel._format_value
_LABEL_COL_WIDTH = 220  # ProfileDetailPanel two-column grid
_VAL_COL_WIDTH = 200  # Value column width (detail + convert panels)
_ENTRY_CHARS = 20  # Entry widget character width
_WIN_SCROLL_DELTA_DIVISOR = 120  # Windows scroll delta units per "tick"


# --- Named Constants (extracted from magic numbers) ---

# Maximum inheritance depth for profile resolution (PresetIndex.resolve)
MAX_INHERITANCE_DEPTH = 10

# Color lightening amount for hover/active states (ColorPair._lighten_color)
COLOR_LIGHTEN_AMOUNT = 20

# Tooltip delay in milliseconds for profile detail panel
TOOLTIP_DELAY_MS = 500

# Tree hover tooltip delay (differs from TOOLTIP_DELAY_MS)
_TREE_TOOLTIP_DELAY_MS = 600

# Setting ID prefix for profile toolkit user settings (Profile Toolkit User Setting)
SETTING_ID_PREFIX = "PFUS"

# HTTP User-Agent string for web requests
HTTP_USER_AGENT = f"Mozilla/5.0 (compatible; ProfileToolkit/{APP_VERSION})"

# Monospace font for G-code and raw text displays
if _PLATFORM == "Darwin":
    MONO_FONT = "Menlo"
elif _PLATFORM == "Windows":
    MONO_FONT = "Consolas"
else:
    MONO_FONT = "DejaVu Sans Mono"
MONO_FONT_SIZE = 13

# Online catalog fetch watchdog timeout (milliseconds).
# Must exceed the per-socket HTTP timeout (30s) to avoid premature watchdog
# firing while large bundles (e.g. PrusaResearch.ini ~2MB) are still downloading.
FETCH_TIMEOUT_MS = 45_000

# Maximum sources shown in info popups
MAX_POPUP_SOURCES = 5

# Debug log filename for compare panel errors
COMPARE_DEBUG_LOG = "compare_debug.log"

# Maximum filename collision retries during export
MAX_COLLISION_ATTEMPTS = 100

# Maximum undo stack entries (compare panel copy operations)
MAX_UNDO_STACK_SIZE = 200


# --- BambuStudio UI Layout Definitions ---
# Each entry: (json_key, ui_label)
# Ordering matches BambuStudio's UI exactly (from screenshots + source code).

FILAMENT_LAYOUT = {
    "Filament": {
        "Basic information": [
            ("filament_type", "Type"),
            ("filament_vendor", "Vendor"),
            ("filament_soluble", "Soluble material"),
            ("filament_is_support", "Support material"),
            ("filament_abrasive", "Abrasive material", "Prusa"),
            ("filament_ramming_length", "Filament ramming length"),
            ("impact_strength_z", "Impact Strength Z"),
            ("required_nozzle_HRC", "Required nozzle HRC"),
            ("filament_colour", "Default color"),
            ("filament_diameter", "Diameter"),
            ("adhesiveness_category", "Adhesiveness Category"),
            ("filament_density", "Density"),
            ("filament_shrink", "Shrinkage"),
            (
                "filament_shrinkage_compensation_xy",
                "Shrinkage compensation XY",
                "Prusa",
            ),
            ("filament_shrinkage_compensation_z", "Shrinkage compensation Z", "Prusa"),
            ("velocity_adaptation_factor", "Velocity Adaptation Factor"),
            ("filament_cost", "Price"),
            ("filament_spool_weight", "Spool weight", "Prusa"),
            ("softening_temperature", "Softening temperature"),
            ("idle_temperature", "Idle temperature"),
            ("filament_prime_volume", "Filament prime volume"),
            ("travel_time_after_ramming", "Travel time after ramming"),
            ("precooling_target_temperature", "Precooling target temperature"),
            ("nozzle_temperature_range_low", "Recommended nozzle temperature (Min)"),
            ("nozzle_temperature_range_high", "Recommended nozzle temperature (Max)"),
        ],
        "Flow ratio and Pressure Advance": [
            ("filament_flow_ratio", "Flow ratio"),
            ("extrusion_multiplier", "Extrusion multiplier", "Prusa"),
            ("enable_pressure_advance", "Enable pressure advance"),
            ("pressure_advance", "Pressure advance"),
            ("adaptive_pressure_advance", "Enable adaptive pressure advance (beta)"),
        ],
        "Print chamber temperature": [
            ("activate_chamber_temp_control", "Activate temperature control"),
            ("chamber_temperature", "Chamber temperature", "Prusa"),
            ("chamber_minimal_temperature", "Chamber minimal temperature", "Prusa"),
        ],
        "Print temperature": [
            ("nozzle_temperature_initial_layer", "Nozzle (First layer)"),
            ("nozzle_temperature", "Nozzle (Other layers)"),
            ("first_layer_temperature", "First layer temperature", "Prusa"),
            ("temperature", "Temperature", "Prusa"),
        ],
        "Bed temperature": [
            (
                "supertack_plate_temp_initial_layer",
                "Cool Plate SuperTack (First layer)",
                "Bambu",
            ),
            ("supertack_plate_temp", "Cool Plate SuperTack (Other layers)", "Bambu"),
            ("cool_plate_temp_initial_layer", "Cool Plate (First layer)", "Bambu"),
            ("cool_plate_temp", "Cool Plate (Other layers)", "Bambu"),
            (
                "textured_cool_plate_temp_initial_layer",
                "Textured Cool Plate (First layer)",
                "Bambu",
            ),
            ("textured_cool_plate_temp", "Textured Cool Plate (Other layers)", "Bambu"),
            (
                "eng_plate_temp_initial_layer",
                "Engineering Plate (First layer)",
                "Bambu",
            ),
            ("eng_plate_temp", "Engineering Plate (Other layers)", "Bambu"),
            (
                "hot_plate_temp_initial_layer",
                "Smooth PEI Plate / High Temp Plate (First layer)",
                "Bambu",
            ),
            (
                "hot_plate_temp",
                "Smooth PEI Plate / High Temp Plate (Other layers)",
                "Bambu",
            ),
            (
                "textured_plate_temp_initial_layer",
                "Textured PEI Plate (First layer)",
                "Bambu",
            ),
            ("textured_plate_temp", "Textured PEI Plate (Other layers)", "Bambu"),
            ("first_layer_bed_temperature", "First layer bed temperature", "Prusa"),
            ("bed_temperature", "Bed temperature", "Prusa"),
        ],
        "Volumetric speed limitation": [
            ("adaptive_volumetric_speed", "Adaptive volumetric speed"),
            ("filament_max_volumetric_speed", "Max volumetric speed"),
            ("filament_infill_max_speed", "Infill max speed", "Prusa"),
            (
                "filament_infill_max_crossing_speed",
                "Infill max crossing speed",
                "Prusa",
            ),
            ("ramming_volumetric_speed", "Ramming volumetric speed"),
        ],
        "Filament scarf seam settings": [
            ("filament_scarf_seam_type", "Scarf seam type"),
            ("filament_scarf_start_height", "Scarf start height"),
            ("filament_scarf_slope_gap", "Scarf slope gap"),
            ("filament_scarf_length", "Scarf length"),
        ],
    },
    "Cooling": {
        "Cooling for specific layer": [
            ("close_fan_the_first_x_layers", "No cooling for the first"),
            ("disable_fan_first_layers", "Disable fan first layers", "Prusa"),
            ("full_fan_speed_layer", "Full fan speed at layer"),
            ("cooling", "Enable auto cooling", "Prusa"),
        ],
        "Part cooling fan": [
            ("min_fan_speed", "Min fan speed", "Prusa"),
            ("max_fan_speed", "Max fan speed", "Prusa"),
            ("fan_min_speed", "Min fan speed threshold (Fan speed)"),
            ("fan_min_speed_layer_time", "Min fan speed threshold (Layer time)"),
            ("fan_max_speed", "Max fan speed threshold (Fan speed)"),
            ("fan_max_speed_layer_time", "Max fan speed threshold (Layer time)"),
            ("fan_below_layer_time", "Fan below layer time", "Prusa"),
            ("fan_always_on", "Fan always on", "Prusa"),
            ("reduce_fan_stop_start_freq", "Keep fan always on"),
            (
                "slow_down_for_layer_cooling",
                "Slow printing down for better layer cooling",
            ),
            ("slowdown_below_layer_time", "Slowdown below layer time", "Prusa"),
            ("dont_slow_down_outer_wall", "Don't slow down outer walls"),
            ("cooling_slowdown_logic", "Cooling slowdown logic"),
            ("perimeter_transition_distance", "Perimeter transition distance"),
            ("slow_down_min_speed", "Min print speed"),
            ("min_print_speed", "Min print speed", "Prusa"),
            ("force_cooling_for_overhangs", "Force cooling for overhangs and bridges"),
            ("overhang_fan_threshold", "Overhang cooling activation threshold"),
            ("overhang_fan_speed", "Overhangs and external bridges fan speed"),
            ("enable_dynamic_fan_speeds", "Enable dynamic fan speeds", "Prusa"),
            ("bridge_fan_speed", "Bridge fan speed", "Prusa"),
            ("overhang_fan_speed_0", "Overhang fan speed (0%)", "Prusa"),
            ("overhang_fan_speed_1", "Overhang fan speed (25%)", "Prusa"),
            ("overhang_fan_speed_2", "Overhang fan speed (50%)", "Prusa"),
            ("overhang_fan_speed_3", "Overhang fan speed (75%)", "Prusa"),
            ("internal_bridge_fan_speed", "Internal bridges fan speed"),
            ("support_material_interface_fan_speed", "Support interface fan speed"),
            ("ironing_fan_speed", "Ironing fan speed"),
            ("cooling_overhang_threshold", "Cooling overhang threshold"),
            (
                "overhang_threshold_for_participating_cooling",
                "Overhang threshold for participating cooling",
            ),
            ("pre_start_fan_time", "Pre start fan time"),
        ],
        "Auxiliary part cooling fan": [
            ("auxiliary_fan_speed", "Fan speed"),
        ],
        "Exhaust fan": [
            ("activate_air_filtration", "Activate air filtration"),
            ("during_print_exhaust_fan_speed", "During print"),
            ("complete_print_exhaust_fan_speed", "Complete print"),
        ],
    },
    "Setting Overrides": {
        "Retraction": [
            ("filament_retraction_length", "Length"),
            ("filament_retract_length", "Retract length", "Prusa"),
            ("filament_z_hop", "Z-hop height"),
            ("filament_z_hop_type", "Z-hop type"),
            ("filament_retract_lift_above", "Only lift Z above"),
            ("filament_retract_lift_below", "Only lift Z below"),
            ("filament_retract_lift_enforce", "On surfaces"),
            ("filament_retraction_speed", "Retraction speed"),
            ("filament_retract_speed", "Retract speed", "Prusa"),
            ("filament_deretraction_speed", "Deretraction speed"),
            ("filament_deretract_speed", "Deretract speed", "Prusa"),
            ("filament_retract_lift", "Retract lift (Z-hop)", "Prusa"),
            ("retract_length_toolchange", "Length when change hotend"),
            (
                "filament_retract_length_toolchange",
                "Retract length (toolchange)",
                "Prusa",
            ),
            ("filament_unretraction_extra_length", "Extra length on restart"),
            ("filament_retract_restart_extra", "Retract restart extra", "Prusa"),
            (
                "filament_retract_restart_extra_toolchange",
                "Retract restart extra (toolchange)",
                "Prusa",
            ),
            ("travel_distance_threshold", "Travel distance threshold"),
            ("filament_retract_before_travel", "Retract before travel", "Prusa"),
            ("filament_retract_when_changing_layer", "Retract on layer change"),
            ("filament_retract_layer_change", "Retract on layer change", "Prusa"),
            ("wipe_while_retracting", "Wipe while retracting"),
            ("filament_wipe", "Wipe", "Prusa"),
            ("filament_retract_before_wipe", "Retract before wipe", "Prusa"),
            ("filament_wipe_distance", "Wipe distance"),
            ("retract_amount_before_wipe", "Retract amount before wipe"),
            ("filament_seam_gap_distance", "Seam gap distance", "Prusa"),
            ("long_retraction_when_cut", "Long retraction when cut (beta)"),
            ("filament_retraction_distances_when_cut", "Retraction distance when cut"),
        ],
        "Travel": [
            (
                "filament_travel_lift_before_obstacle",
                "Travel lift before obstacle",
                "Prusa",
            ),
            ("filament_travel_max_lift", "Travel max lift", "Prusa"),
            ("filament_travel_ramping_lift", "Travel ramping lift", "Prusa"),
            ("filament_travel_slope", "Travel slope", "Prusa"),
        ],
        "Ironing": [
            ("ironing_flow", "Ironing flow"),
            ("ironing_spacing", "Ironing line spacing"),
            ("ironing_inset", "Ironing inset"),
            ("ironing_speed", "Ironing speed"),
        ],
        "Speed": [
            ("override_overhang_speed", "Override overhang speed"),
        ],
    },
    "Advanced": {
        "Filament start G-code": [
            ("filament_start_gcode", "Filament start G-code"),
            ("start_filament_gcode", "Start filament G-code", "Prusa"),
        ],
        "Filament end G-code": [
            ("filament_end_gcode", "Filament end G-code"),
            ("end_filament_gcode", "End filament G-code", "Prusa"),
        ],
    },
    "Multimaterial": {
        "Wipe tower parameters": [
            ("filament_minimal_purge_on_wipe_tower", "Minimal purge on wipe tower"),
            ("wipe_tower_cooling", "Wipe tower cooling"),
            (
                "interface_layer_pre_extrusion_distance",
                "Interface layer pre-extrusion distance",
            ),
            (
                "interface_layer_pre_extrusion_length",
                "Interface layer pre-extrusion length",
            ),
            ("tower_ironing_area", "Tower ironing area"),
            ("interface_layer_purge_length", "Interface layer purge length"),
            ("interface_layer_print_temperature", "Interface layer print temperature"),
        ],
        "Tool change parameters with single extruder MM printers": [
            ("filament_loading_speed_start", "Loading speed at the start"),
            ("filament_loading_speed", "Loading speed"),
            ("filament_unloading_speed_start", "Unloading speed at the start"),
            ("filament_unloading_speed", "Unloading speed"),
            ("filament_toolchange_delay", "Delay after unloading"),
            ("filament_cooling_moves", "Number of cooling moves"),
            ("filament_cooling_initial_speed", "Speed of the first cooling move"),
            ("filament_cooling_final_speed", "Speed of the last cooling move"),
            ("filament_stamping_loading_speed", "Stamping loading speed"),
            ("filament_stamping_distance", "Stamping distance"),
            ("filament_ramming_parameters", "Ramming parameters"),
        ],
        "Tool change parameters with multi extruder MM printers": [
            ("filament_multitool_ramming", "Enable ramming for multi-tool setups"),
            ("filament_multitool_ramming_volume", "Multi-tool ramming volume"),
            ("filament_multitool_ramming_flow", "Multi-tool ramming flow"),
        ],
        "Purge and load/unload": [
            ("filament_purge_multiplier", "Purge multiplier", "Prusa"),
            ("filament_load_time", "Filament load time", "Prusa"),
            ("filament_unload_time", "Filament unload time", "Prusa"),
        ],
    },
    "Dependencies": {
        "Compatible printers": [
            ("compatible_printers", "Select printers"),
            ("compatible_printers_condition", "Condition"),
        ],
        "Compatible process profiles": [
            ("compatible_prints", "Select profiles"),
            ("compatible_prints_condition", "Condition"),
        ],
    },
    "Notes": {
        "Notes": [
            ("filament_notes", "Notes"),
            ("filament_settings_id", "Filament settings ID", "Prusa"),
        ],
    },
}

# Slicer identity colors and labels (used for origin badges in UI)
SLICER_COLORS = {
    "PrusaSlicer": "#FF7B15",  # Orange
    "BambuStudio": "#2ECC71",  # Green (4.6:1 AA with dark text)
    "OrcaSlicer": "#2196F3",  # Blue
}
SLICER_SHORT_LABELS = {
    "PrusaSlicer": "Prusa",
    "BambuStudio": "Bambu",
    "OrcaSlicer": "Orca",
}

# Tabs that only appear in Orca Slicer (shown with "(Orca only)" badge)
ORCA_ONLY_TABS = {"Setting Overrides", "Multimaterial", "Dependencies", "Notes"}

# Build key sets for each layout
_ALL_FILAMENT_KEYS = set()
for _tab_sections in FILAMENT_LAYOUT.values():
    for _params in _tab_sections.values():
        for _entry in _params:
            _ALL_FILAMENT_KEYS.add(_entry[0])
for _name in ("_tab_sections", "_params", "_entry"):
    vars().pop(_name, None)

# Identity/meta keys: profile bookkeeping fields shown in the header,
# not as editable parameters. Excluded from tab layout and diff views.
# Criteria: keys that identify or version the profile itself, rather than
# describe printer/filament settings. Add new keys here if they should
# never appear in the parameter tabs or diff comparisons.
_IDENTITY_KEYS = {
    "name",
    "type",
    "inherits",
    "from",
    "setting_id",
    "compatible_printers",
    "compatible_printers_condition",
    "printer_settings_id",
    "version",
    "is_custom_defined",
    "instantiation",
    "user_id",
    "updated_time",
}

# Keys that strongly indicate a filament profile
_FILAMENT_SIGNAL_KEYS = frozenset(
    {
        "filament_type",
        "nozzle_temperature",
        "filament_flow_ratio",
        "fan_min_speed",
        "fan_max_speed",
        "filament_retraction_length",
        "nozzle_temperature_initial_layer",
        "cool_plate_temp",
        "hot_plate_temp",
        "filament_max_volumetric_speed",
        "filament_density",
        "filament_colour",
        "filament_vendor",
        "filament_cost",
    }
)

# Keys that strongly indicate a process/print profile
_PROCESS_SIGNAL_KEYS = frozenset(
    {
        "layer_height",
        "wall_loops",
        "sparse_infill_density",
        "support_type",
        "print_speed",
    }
)

# Keys that identify any profile data (either type)
_PROFILE_SIGNAL_KEYS = (
    _FILAMENT_SIGNAL_KEYS
    | _PROCESS_SIGNAL_KEYS
    | frozenset(
        {
            "compatible_printers",
            "inherits",
            "from",
        }
    )
)

# --- Smart Recommendations Knowledge Base ---
# Static knowledge base of recommended ranges per material.
# Structure: RECOMMENDATIONS[json_key] = {
#   "info": str,   # general info text for the ⓘ popup (material-independent)
#   "ranges": {material: {"min": float, "max": float, "typical": float, "notes": str}, ...}
# }
# Materials: PLA, PETG, ABS, ASA, TPU, PA, PC, PLA-CF, PETG-CF, PA-CF
# "General" is the fallback when material is unknown.

RECOMMENDATIONS = {
    # Quality Tab
    "layer_height": {
        "info": "Layer height controls detail vs speed tradeoff. Thicker layers = stronger parts (more bonding area), thinner = more detail. Speed relationship: Speed (mm/s) = Volumetric Flow / layer_height / line_width.",
        "sources": [
            {
                "label": "Sloyd.ai Layer Height Guide",
                "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide",
            },
            {
                "label": "Ellis3DP Max Volumetric Flow",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/determining_max_volumetric_flow_rate.html",
            },
            {
                "label": "Prusa Composite Materials",
                "url": "https://help.prusa3d.com/article/composite-materials-filled-with-carbon-kevlar-or-glass_167387",
            },
            {
                "label": "Simplify3D CF Guide",
                "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/",
            },
        ],
        "ranges": {
            "PLA": {
                "min": 0.1,
                "max": 0.3,
                "typical": 0.2,
                "notes": "Lower for detail, higher for speed",
                "sources": [
                    {
                        "label": "Sloyd.ai Layer Height Guide",
                        "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide",
                    }
                ],
            },
            "PETG": {
                "min": 0.1,
                "max": 0.3,
                "typical": 0.2,
                "sources": [
                    {
                        "label": "Sloyd.ai Layer Height Guide",
                        "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide",
                    }
                ],
            },
            "ABS": {
                "min": 0.2,
                "max": 0.3,
                "typical": 0.2,
                "sources": [
                    {
                        "label": "Sloyd.ai Layer Height Guide",
                        "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide",
                    }
                ],
            },
            "TPU": {
                "min": 0.2,
                "max": 0.3,
                "typical": 0.2,
                "notes": "0.05 mm possible for fine details",
                "sources": [
                    {
                        "label": "Sloyd.ai Layer Height Guide",
                        "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide",
                    }
                ],
            },
            "PA": {
                "min": 0.2,
                "max": 0.4,
                "typical": 0.2,
                "notes": "Broader range reduces warping",
                "sources": [
                    {
                        "label": "Sloyd.ai Layer Height Guide",
                        "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide",
                    }
                ],
            },
            "PC": {"min": 0.2, "max": 0.3, "typical": 0.2},
            "PLA-CF": {
                "min": 0.2,
                "max": 0.3,
                "typical": 0.2,
                "notes": "Minimum 0.2 mm to reduce clogging",
                "sources": [
                    {
                        "label": "Prusa Composite Materials",
                        "url": "https://help.prusa3d.com/article/composite-materials-filled-with-carbon-kevlar-or-glass_167387",
                    },
                    {
                        "label": "Simplify3D CF Guide",
                        "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/",
                    },
                ],
            },
            "PETG-CF": {
                "min": 0.2,
                "max": 0.3,
                "typical": 0.2,
                "notes": "Minimum 0.2 mm to reduce clogging",
                "sources": [
                    {
                        "label": "Prusa Composite Materials",
                        "url": "https://help.prusa3d.com/article/composite-materials-filled-with-carbon-kevlar-or-glass_167387",
                    },
                    {
                        "label": "Simplify3D CF Guide",
                        "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/",
                    },
                ],
            },
            "PA-CF": {
                "min": 0.2,
                "max": 0.3,
                "typical": 0.2,
                "notes": "Minimum 0.2 mm to reduce clogging",
                "sources": [
                    {
                        "label": "Prusa Composite Materials",
                        "url": "https://help.prusa3d.com/article/composite-materials-filled-with-carbon-kevlar-or-glass_167387",
                    },
                    {
                        "label": "Simplify3D CF Guide",
                        "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/",
                    },
                ],
            },
            "General": {"min": 0.1, "max": 0.3, "typical": 0.2},
        },
    },
    "initial_layer_print_height": {
        "info": "First layer height. Thicker first layers are less sensitive to bed leveling errors. Ellis3DP recommends ≥0.25 mm, especially on larger printers.",
        "sources": [
            {
                "label": "Ellis3DP First Layer Squish",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/first_layer_squish.html",
            },
        ],
        "ranges": {
            "General": {"min": 0.2, "max": 0.35, "typical": 0.28},
        },
    },
    "line_width": {
        "info": "Standard: match nozzle diameter (0.4 mm for 0.4 mm nozzle). Misconception: two 0.4 mm perimeters ≠ 0.8 mm wall. Actual Slic3r formula: spacing = width − layer_height × (1 − π/4).",
        "sources": [
            {
                "label": "Ellis3DP Misconceptions",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html",
            },
        ],
        "ranges": {
            "General": {"min": 0.35, "max": 0.55, "typical": 0.42},
        },
    },
    "initial_layer_line_width": {
        "info": "Set to ≥120% of nozzle diameter for first layer. Wider first layer improves bed adhesion.",
        "sources": [
            {
                "label": "Ellis3DP First Layer Squish",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/first_layer_squish.html",
            },
        ],
        "ranges": {
            "General": {"min": 0.42, "max": 0.6, "typical": 0.5},
        },
    },
    "outer_wall_line_width": {
        "info": "Typically 100% of nozzle diameter or slightly less for sharper detail. Narrower = finer detail; wider = more strength.",
        "ranges": {
            "General": {"min": 0.35, "max": 0.5, "typical": 0.4},
        },
    },
    "sparse_infill_line_width": {
        "info": "Can be wider than walls (110–150% of nozzle) for faster infill without quality loss. Wider lines = faster print, slightly stronger infill bonds.",
        "ranges": {
            "General": {"min": 0.4, "max": 0.65, "typical": 0.45},
        },
    },
    "bridge_flow": {
        "info": "Typically 90–100%. Slightly under-extruding bridges improves sag. Lower values stretch the filament more during bridging.",
        "ranges": {
            "General": {"min": 0.7, "max": 1.0, "typical": 0.95},
        },
    },
    "top_solid_infill_flow_ratio": {
        "info": "Controls extrusion for top surfaces specifically. Ellis3DP: tune extrusion multiplier for perfect top surfaces.",
        "ranges": {
            "General": {"min": 0.9, "max": 1.0, "typical": 0.97},
        },
    },
    "xy_hole_compensation": {
        "info": "Compensates for holes printing smaller than designed. Tune per-printer: print test holes and measure deviation.",
        "ranges": {
            "General": {"min": 0.0, "max": 0.3, "typical": 0.1},
        },
    },
    "xy_contour_compensation": {
        "info": "Compensates for outer dimensions printing larger/smaller than designed. Use slicer shrinkage compensation for dimensional accuracy rather than EM tuning.",
        "sources": [
            {
                "label": "Ellis3DP Misconceptions",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html",
            },
        ],
        "ranges": {
            "General": {"min": -0.2, "max": 0.2, "typical": 0.0},
        },
    },
    # Strength Tab
    "wall_loops": {
        "info": "2–3 walls for general use, 4+ for strength. Walls contribute more to strength than infill in most cases. Single wall mode exists for vase/spiral prints.",
        "ranges": {
            "General": {"min": 2, "max": 6, "typical": 3},
        },
    },
    "top_shell_layers": {
        "info": "Minimum 3–5 layers for solid top surfaces. More layers = better surface quality, less infill show-through. Rule of thumb: at least 0.8 mm total top thickness.",
        "ranges": {
            "General": {"min": 3, "max": 8, "typical": 4},
        },
    },
    "bottom_shell_layers": {
        "info": "Minimum 3–4 layers. More layers = better bottom quality on textured surfaces.",
        "ranges": {
            "General": {"min": 3, "max": 6, "typical": 4},
        },
    },
    # Speed Tab
    "initial_layer_speed": {
        "info": "Typically 50–70% of normal print speed. Slower = better adhesion. Too slow on some materials (PETG) can cause elephant's foot.",
        "ranges": {
            "General": {"min": 20, "max": 60, "typical": 40},
        },
    },
    "outer_wall_speed": {
        "info": "Outer wall speed is the primary quality-affecting speed parameter. Material-dependent — TPU needs very slow speeds.",
        "sources": [],
        "ranges": {
            "PLA": {
                "min": 50,
                "max": 200,
                "typical": 70,
                "sources": [
                    {
                        "label": "Polymaker Printing Temperature",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
                    },
                    {
                        "label": "Sovol3D Temp Guide 2026",
                        "url": "https://www.sovol3d.com/blogs/news/3d-print-nozzle-temperature-guide-for-materials-2026",
                    },
                ],
            },
            "PETG": {
                "min": 40,
                "max": 100,
                "typical": 55,
                "sources": [
                    {
                        "label": "Polymaker PolyLite PETG",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg",
                    },
                    {
                        "label": "All3DP PETG Settings",
                        "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/",
                    },
                ],
            },
            "ABS": {
                "min": 40,
                "max": 200,
                "typical": 55,
                "sources": [
                    {
                        "label": "Polymaker PolyLite ABS",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs",
                    },
                    {
                        "label": "Sovol3D Temp Guide 2026",
                        "url": "https://www.sovol3d.com/blogs/news/3d-print-nozzle-temperature-guide-for-materials-2026",
                    },
                ],
            },
            "ASA": {
                "min": 30,
                "max": 200,
                "typical": 50,
                "sources": [
                    {
                        "label": "Polymaker ASA",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa",
                    },
                    {
                        "label": "All3DP ASA",
                        "url": "https://all3dp.com/2/3d-printing-asa/",
                    },
                ],
            },
            "TPU": {
                "min": 15,
                "max": 35,
                "typical": 25,
                "notes": "Slow speeds mandatory; direct drive preferred",
                "sources": [
                    {
                        "label": "Overture TPU Guide",
                        "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide",
                    },
                    {
                        "label": "Prusa Flexible Materials",
                        "url": "https://help.prusa3d.com/article/flexible-materials_2057",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PA": {
                "min": 25,
                "max": 60,
                "typical": 45,
                "sources": [
                    {
                        "label": "Polymaker Nylon (PA)",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa",
                    },
                    {
                        "label": "All3DP Printing Temperatures",
                        "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/",
                    },
                ],
            },
            "PC": {
                "min": 20,
                "max": 200,
                "typical": 40,
                "sources": [
                    {
                        "label": "Polymaker PolyLite PC",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc",
                    },
                    {
                        "label": "Sovol3D Temp Guide 2026",
                        "url": "https://www.sovol3d.com/blogs/news/3d-print-nozzle-temperature-guide-for-materials-2026",
                    },
                ],
            },
            "PLA-CF": {
                "min": 25,
                "max": 60,
                "typical": 40,
                "notes": "25–50% slower than base PLA",
                "sources": [
                    {
                        "label": "Simplify3D Carbon Fiber Guide",
                        "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/",
                    }
                ],
            },
            "General": {"min": 30, "max": 200, "typical": 60},
        },
    },
    "inner_wall_speed": {
        "info": "Can typically be 25–50% faster than outer wall speed since not visible. Same material constraints apply.",
        "ranges": {
            "TPU": {"min": 20, "max": 50, "typical": 35},
            "General": {"min": 50, "max": 300, "typical": 100},
        },
    },
    "sparse_infill_speed": {
        "info": "Can be fastest print move (not visible). Limited by max volumetric speed of hotend, not quality. Speed = volumetric_flow / layer_height / line_width.",
        "sources": [
            {
                "label": "Ellis3DP Max Volumetric Flow",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/determining_max_volumetric_flow_rate.html",
            },
        ],
        "ranges": {
            "TPU": {"min": 20, "max": 50, "typical": 30},
            "General": {"min": 50, "max": 300, "typical": 150},
        },
    },
    "top_surface_speed": {
        "info": "Slower than infill for quality (typically 50–70% of outer wall speed). Affects visible surface quality significantly.",
        "ranges": {
            "General": {"min": 30, "max": 150, "typical": 60},
        },
    },
    "bridge_speed": {
        "info": "Typically 20–40 mm/s. Slower bridges sag less.",
        "ranges": {
            "General": {"min": 15, "max": 50, "typical": 30},
        },
    },
    "travel_speed": {
        "info": "Typically 120–250 mm/s (as fast as machine allows). Faster travel = less stringing, less ooze. TPU: 100–150 mm/s.",
        "ranges": {
            "TPU": {"min": 100, "max": 150, "typical": 120},
            "General": {"min": 120, "max": 300, "typical": 200},
        },
    },
    "default_acceleration": {
        "info": "Tune accelerations FIRST, then speeds (Ellis3DP). Apply ~15% safety margin below tested maximums. Common ranges 500–5000 mm/s², tested up to 10000.",
        "sources": [
            {
                "label": "Ellis3DP Max Speeds & Accelerations",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/determining_max_speeds_accels.html",
            },
        ],
        "ranges": {
            "General": {"min": 500, "max": 10000, "typical": 3000},
        },
    },
    "outer_wall_acceleration": {
        "info": "Lower than inner wall/infill for surface quality. Reduces ringing/ghosting artifacts on visible surfaces.",
        "ranges": {
            "General": {"min": 500, "max": 5000, "typical": 2000},
        },
    },
    # Support Tab
    "support_threshold_angle": {
        "info": "Angle from vertical below which supports generate. 45° is a common default. Material-dependent: PLA handles steeper overhangs better with cooling.",
        "ranges": {
            "General": {"min": 30, "max": 60, "typical": 45},
        },
    },
    "support_top_z_distance": {
        "info": "Standard: 1 layer height. Water-soluble supports (PVA/BVOH): 0 mm for perfect interface. TPU supports: 0.3 mm Z-spacing.",
        "ranges": {
            "TPU": {
                "min": 0.2,
                "max": 0.4,
                "typical": 0.3,
                "notes": "0.3 mm Z-spacing recommended",
                "sources": [
                    {
                        "label": "Prusa Prusament TPU 95A",
                        "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653",
                    }
                ],
            },
            "General": {
                "min": 0.1,
                "max": 0.3,
                "typical": 0.2,
                "sources": [
                    {
                        "label": "Prusa Water-Soluble (PVA/BVOH)",
                        "url": "https://help.prusa3d.com/article/water-soluble-bvoh-pva_167012",
                    }
                ],
            },
        },
    },
    # Others Tab
    "brim_width": {
        "info": "HIPS: recommended for small contact areas. PP: 5–10 mm depending on model size. ABS/ASA: helps with warping on unenclosed printers.",
        "ranges": {
            "ABS": {"min": 3, "max": 10, "typical": 5, "notes": "Helps with warping"},
            "ASA": {"min": 3, "max": 10, "typical": 5, "notes": "Helps with warping"},
            "PP": {
                "min": 5,
                "max": 10,
                "typical": 8,
                "notes": "Needed for adhesion",
                "sources": [
                    {
                        "label": "Prusa Polypropylene",
                        "url": "https://help.prusa3d.com/article/polypropylene-pp_167126",
                    }
                ],
            },
            "General": {"min": 0, "max": 10, "typical": 3},
        },
    },
    # Filament Parameters
    "filament_flow_ratio": {
        "info": "Starting range: 0.92–0.98 for most filaments. Tune for perfect TOP SURFACE appearance, NOT dimensional accuracy. If uncertain between two values, pick the higher one. Must be tuned per filament brand/type minimum.",
        "sources": [
            {
                "label": "Ellis3DP Extrusion Multiplier",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/extrusion_multiplier.html",
            },
            {
                "label": "Ellis3DP Misconceptions",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html",
            },
        ],
        "ranges": {
            "General": {"min": 0.9, "max": 1.0, "typical": 0.96},
        },
    },
    "nozzle_temperature": {
        "info": "Hotter = better layer adhesion but more stringing/oozing. All-metal hotend required above ~240°C. Temperature tuning: adjust 5°C at a time.",
        "sources": [
            {
                "label": "OrcaSlicer Material Temps",
                "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
            },
            {
                "label": "Polymaker Printing Temperature",
                "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
            },
            {
                "label": "Teaching Tech Calibration",
                "url": "https://teachingtechyt.github.io/calibration.html",
            },
            {"label": "Filament Cheat Sheet", "url": "https://filamentcheatsheet.com/"},
            {
                "label": "All3DP Filament Types",
                "url": "https://all3dp.com/1/3d-printer-filament-types-3d-printing-3d-filament/",
            },
        ],
        "ranges": {
            "PLA": {
                "min": 190,
                "max": 225,
                "typical": 210,
                "sources": [
                    {
                        "label": "Polymaker Printing Temperature",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
                    },
                    {
                        "label": "Prusa PLA",
                        "url": "https://help.prusa3d.com/article/pla_2062",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PETG": {
                "min": 220,
                "max": 255,
                "typical": 240,
                "notes": "Use release layer on glass; can over-adhere to PEI",
                "sources": [
                    {
                        "label": "Polymaker PolyLite PETG",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg",
                    },
                    {
                        "label": "Prusa PETG",
                        "url": "https://help.prusa3d.com/article/petg_2059",
                    },
                    {
                        "label": "MatterHackers PETG",
                        "url": "https://www.matterhackers.com/news/how-to-succeed-when-printing-with-petg-filament",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "ABS": {
                "min": 230,
                "max": 260,
                "typical": 245,
                "notes": "Enclosure critical; emits fumes",
                "sources": [
                    {
                        "label": "Polymaker PolyLite ABS",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs",
                    },
                    {
                        "label": "Prusa ABS",
                        "url": "https://help.prusa3d.com/article/abs_2058",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "ASA": {
                "min": 230,
                "max": 270,
                "typical": 255,
                "sources": [
                    {
                        "label": "Polymaker ASA",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa",
                    },
                    {
                        "label": "Prusa ASA",
                        "url": "https://help.prusa3d.com/article/asa_1809",
                    },
                    {
                        "label": "All3DP ASA",
                        "url": "https://all3dp.com/2/3d-printing-asa/",
                    },
                ],
            },
            "TPU": {
                "min": 210,
                "max": 245,
                "typical": 225,
                "notes": "Direct drive extruder strongly preferred",
                "sources": [
                    {
                        "label": "Prusa Prusament TPU 95A",
                        "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653",
                    },
                    {
                        "label": "Overture TPU Guide",
                        "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PA": {
                "min": 240,
                "max": 290,
                "typical": 265,
                "notes": "Extremely hygroscopic; must dry before use",
                "sources": [
                    {
                        "label": "Prusa Polyamide",
                        "url": "https://help.prusa3d.com/article/polyamide-nylon_167188",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                    {
                        "label": "All3DP Temps",
                        "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PC": {
                "min": 260,
                "max": 310,
                "typical": 280,
                "notes": "Enclosure required; dry before printing",
                "sources": [
                    {
                        "label": "Polymaker PolyLite PC",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc",
                    },
                    {
                        "label": "Prusa PC",
                        "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PLA-CF": {
                "min": 200,
                "max": 240,
                "typical": 225,
                "notes": "Base +10–20°C",
                "sources": [
                    {
                        "label": "Polymaker Printing Temperature",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
                    },
                    {
                        "label": "Nobufil PLA-CF Guide",
                        "url": "https://www.nobufil.com/en/post/3d-printing-with-pla-cf-filament",
                    },
                    {
                        "label": "Simplify3D CF Guide",
                        "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/",
                    },
                ],
            },
            "PETG-CF": {
                "min": 240,
                "max": 270,
                "typical": 250,
                "sources": [
                    {
                        "label": "Polymaker Printing Temperature",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
                    }
                ],
            },
            "PA-CF": {
                "min": 260,
                "max": 300,
                "typical": 280,
                "sources": [
                    {
                        "label": "Polymaker Nylon (PA)",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa",
                    }
                ],
            },
            "General": {"min": 190, "max": 310, "typical": 230},
        },
    },
    "nozzle_temperature_initial_layer": {
        "info": "Typically same as nozzle temp or 5°C higher for adhesion. Prusa PLA: 215°C first layer. Some filaments benefit from slightly lower first layer temp to reduce elephant's foot.",
        "ranges": {
            "PLA": {"min": 195, "max": 230, "typical": 215},
            "PETG": {"min": 225, "max": 260, "typical": 245},
            "ABS": {"min": 235, "max": 265, "typical": 250},
            "ASA": {"min": 235, "max": 275, "typical": 260},
            "TPU": {"min": 215, "max": 250, "typical": 230},
            "PA": {"min": 245, "max": 295, "typical": 270},
            "PC": {"min": 265, "max": 315, "typical": 285},
            "General": {"min": 195, "max": 315, "typical": 235},
        },
    },
    "hot_plate_temp": {
        "info": "Bed temperature for PEI Plate (other layers).",
        "sources": [
            {
                "label": "OrcaSlicer Material Temps",
                "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
            },
            {
                "label": "Polymaker Printing Temperature",
                "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
            },
        ],
        "ranges": {
            "PLA": {
                "min": 25,
                "max": 65,
                "typical": 60,
                "sources": [
                    {
                        "label": "Polymaker Printing Temperature",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
                    },
                    {
                        "label": "Prusa PLA",
                        "url": "https://help.prusa3d.com/article/pla_2062",
                    },
                    {
                        "label": "Hatchbox Guides",
                        "url": "https://www.hatchbox3d.com/pages/guides",
                    },
                ],
            },
            "PETG": {
                "min": 60,
                "max": 90,
                "typical": 80,
                "sources": [
                    {
                        "label": "Polymaker PolyLite PETG",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg",
                    },
                    {
                        "label": "Prusa PETG",
                        "url": "https://help.prusa3d.com/article/petg_2059",
                    },
                    {
                        "label": "All3DP PETG",
                        "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/",
                    },
                ],
            },
            "ABS": {
                "min": 80,
                "max": 110,
                "typical": 100,
                "sources": [
                    {
                        "label": "Polymaker PolyLite ABS",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs",
                    },
                    {
                        "label": "Prusa ABS",
                        "url": "https://help.prusa3d.com/article/abs_2058",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                ],
            },
            "ASA": {
                "min": 85,
                "max": 110,
                "typical": 105,
                "sources": [
                    {
                        "label": "Polymaker ASA",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa",
                    },
                    {
                        "label": "Prusa ASA",
                        "url": "https://help.prusa3d.com/article/asa_1809",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "TPU": {
                "min": 25,
                "max": 65,
                "typical": 50,
                "sources": [
                    {
                        "label": "Polymaker TPU",
                        "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu",
                    },
                    {
                        "label": "Prusa Prusament TPU 95A",
                        "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653",
                    },
                    {
                        "label": "Overture TPU",
                        "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PA": {
                "min": 60,
                "max": 110,
                "typical": 90,
                "notes": "Must dry filament before printing",
                "sources": [
                    {
                        "label": "Polymaker Nylon (PA)",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa",
                    },
                    {
                        "label": "Prusa Polyamide",
                        "url": "https://help.prusa3d.com/article/polyamide-nylon_167188",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PC": {
                "min": 90,
                "max": 125,
                "typical": 110,
                "notes": "Enclosure strongly recommended",
                "sources": [
                    {
                        "label": "Polymaker PolyLite PC",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc",
                    },
                    {
                        "label": "Prusa PC",
                        "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "General": {"min": 25, "max": 125, "typical": 60},
        },
    },
    "textured_plate_temp": {
        "info": "Bed temperature for Textured PEI Plate (other layers).",
        "sources": [
            {
                "label": "OrcaSlicer Material Temps",
                "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
            },
            {
                "label": "Polymaker Printing Temperature",
                "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
            },
        ],
        "ranges": {
            "PLA": {
                "min": 25,
                "max": 65,
                "typical": 60,
                "sources": [
                    {
                        "label": "Polymaker Printing Temperature",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
                    },
                    {
                        "label": "Prusa PLA",
                        "url": "https://help.prusa3d.com/article/pla_2062",
                    },
                    {
                        "label": "Hatchbox Guides",
                        "url": "https://www.hatchbox3d.com/pages/guides",
                    },
                ],
            },
            "PETG": {
                "min": 60,
                "max": 90,
                "typical": 80,
                "sources": [
                    {
                        "label": "Polymaker PolyLite PETG",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg",
                    },
                    {
                        "label": "Prusa PETG",
                        "url": "https://help.prusa3d.com/article/petg_2059",
                    },
                    {
                        "label": "All3DP PETG",
                        "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/",
                    },
                ],
            },
            "ABS": {
                "min": 80,
                "max": 110,
                "typical": 100,
                "sources": [
                    {
                        "label": "Polymaker PolyLite ABS",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs",
                    },
                    {
                        "label": "Prusa ABS",
                        "url": "https://help.prusa3d.com/article/abs_2058",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                ],
            },
            "ASA": {
                "min": 85,
                "max": 110,
                "typical": 105,
                "sources": [
                    {
                        "label": "Polymaker ASA",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa",
                    },
                    {
                        "label": "Prusa ASA",
                        "url": "https://help.prusa3d.com/article/asa_1809",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "TPU": {
                "min": 25,
                "max": 65,
                "typical": 50,
                "sources": [
                    {
                        "label": "Polymaker TPU",
                        "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu",
                    },
                    {
                        "label": "Prusa Prusament TPU 95A",
                        "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653",
                    },
                    {
                        "label": "Overture TPU",
                        "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PA": {
                "min": 60,
                "max": 110,
                "typical": 90,
                "notes": "Must dry filament before printing",
                "sources": [
                    {
                        "label": "Polymaker Nylon (PA)",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa",
                    },
                    {
                        "label": "Prusa Polyamide",
                        "url": "https://help.prusa3d.com/article/polyamide-nylon_167188",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PC": {
                "min": 90,
                "max": 125,
                "typical": 110,
                "notes": "Enclosure strongly recommended",
                "sources": [
                    {
                        "label": "Polymaker PolyLite PC",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc",
                    },
                    {
                        "label": "Prusa PC",
                        "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812",
                    },
                    {
                        "label": "OrcaSlicer Material Temps",
                        "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "General": {"min": 25, "max": 125, "typical": 60},
        },
    },
    "filament_max_volumetric_speed": {
        "info": "Hotend-dependent. Larger nozzles = higher flow rates. Hardened steel nozzles may need higher temps or lower flow. Apply safety margin below tested maximum.",
        "sources": [
            {
                "label": "Ellis3DP Max Volumetric Flow",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/determining_max_volumetric_flow_rate.html",
            },
            {
                "label": "Obico OrcaSlicer Calibration",
                "url": "https://www.obico.io/blog/orcaslicer-comprehensive-calibration-guide/",
            },
        ],
        "ranges": {
            "PLA": {
                "min": 10,
                "max": 25,
                "typical": 16.75,
                "sources": [
                    {
                        "label": "Obico OrcaSlicer Calibration",
                        "url": "https://www.obico.io/blog/orcaslicer-comprehensive-calibration-guide/",
                    }
                ],
            },
            "PETG": {
                "min": 10,
                "max": 20,
                "typical": 14.5,
                "sources": [
                    {
                        "label": "Obico OrcaSlicer Calibration",
                        "url": "https://www.obico.io/blog/orcaslicer-comprehensive-calibration-guide/",
                    },
                    {
                        "label": "Polymaker PolyLite PETG",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg",
                    },
                ],
            },
            "ABS": {
                "min": 12,
                "max": 24,
                "typical": 17,
                "sources": [
                    {
                        "label": "Obico OrcaSlicer Calibration",
                        "url": "https://www.obico.io/blog/orcaslicer-comprehensive-calibration-guide/",
                    },
                    {
                        "label": "Polymaker PolyLite ABS",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs",
                    },
                ],
            },
            "ASA": {
                "min": 12,
                "max": 20,
                "typical": 16,
                "sources": [
                    {
                        "label": "Polymaker ASA",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa",
                    }
                ],
            },
            "PC": {
                "min": 8,
                "max": 16,
                "typical": 12,
                "sources": [
                    {
                        "label": "Polymaker PolyLite PC",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc",
                    }
                ],
            },
            "General": {
                "min": 8,
                "max": 25,
                "typical": 15,
                "sources": [
                    {
                        "label": "Ellis3DP Max Volumetric Flow",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/determining_max_volumetric_flow_rate.html",
                    }
                ],
            },
        },
    },
    # Cooling Tab
    "close_fan_the_first_x_layers": {
        "info": "PLA: 1 layer off. PETG: 2–3 layers off then ramp up. ABS/ASA: all layers off if unenclosed. Running max fan from layer 1 ruins bed adhesion.",
        "sources": [
            {
                "label": "MatterHackers PETG",
                "url": "https://www.matterhackers.com/news/how-to-succeed-when-printing-with-petg-filament",
            },
            {
                "label": "Ellis3DP Cooling",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html",
            },
        ],
        "ranges": {
            "PLA": {"min": 1, "max": 1, "typical": 1},
            "PETG": {"min": 2, "max": 3, "typical": 3},
            "ABS": {"min": 1, "max": 5, "typical": 3},
            "ASA": {"min": 1, "max": 5, "typical": 3},
            "General": {"min": 1, "max": 3, "typical": 1},
        },
    },
    "fan_min_speed": {
        "info": "Minimum fan speed threshold. Constant fan speeds recommended — varying speeds cause inconsistent layers and banding.",
        "sources": [
            {
                "label": "Ellis3DP Cooling",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html",
            },
            {
                "label": "Ellis3DP Misconceptions",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html",
            },
            {"label": "Filament Cheat Sheet", "url": "https://filamentcheatsheet.com/"},
        ],
        "ranges": {
            "PLA": {
                "min": 70,
                "max": 100,
                "typical": 80,
                "sources": [
                    {
                        "label": "Ellis3DP Cooling",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html",
                    }
                ],
            },
            "PETG": {
                "min": 10,
                "max": 50,
                "typical": 20,
                "sources": [
                    {
                        "label": "MatterHackers PETG",
                        "url": "https://www.matterhackers.com/news/how-to-succeed-when-printing-with-petg-filament",
                    },
                    {
                        "label": "Ellis3DP Cooling",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html",
                    },
                ],
            },
            "ABS": {
                "min": 0,
                "max": 50,
                "typical": 0,
                "notes": "0% unenclosed, 40%+ enclosed",
                "sources": [
                    {
                        "label": "Ellis3DP Misconceptions",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html",
                    },
                    {
                        "label": "Ellis3DP Cooling",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html",
                    },
                ],
            },
            "ASA": {
                "min": 0,
                "max": 30,
                "typical": 0,
                "sources": [
                    {
                        "label": "3DTrcek ASA Guide",
                        "url": "https://3dtrcek.com/en/blog/post/how-to-print-asa-filament-a-practical-guide-for-durable-prints-2",
                    }
                ],
            },
            "TPU": {
                "min": 20,
                "max": 80,
                "typical": 50,
                "notes": "30–80% typical; adjust for bridging",
                "sources": [
                    {
                        "label": "Prusa TPU 95A",
                        "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653",
                    },
                    {
                        "label": "Polymaker TPU",
                        "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PA": {
                "min": 0,
                "max": 30,
                "typical": 0,
                "notes": "Low cooling; dry filament essential",
                "sources": [
                    {
                        "label": "All3DP Temps",
                        "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PC": {
                "min": 0,
                "max": 30,
                "typical": 0,
                "notes": "Minimal; reduce to prevent cracking",
                "sources": [
                    {
                        "label": "All3DP Temps",
                        "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/",
                    },
                    {
                        "label": "Polymaker PolyLite PC",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PLA-CF": {
                "min": 70,
                "max": 100,
                "typical": 80,
                "sources": [
                    {
                        "label": "Polymaker Printing Temperature",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
                    }
                ],
            },
            "General": {"min": 0, "max": 100, "typical": 50},
        },
    },
    "fan_max_speed": {
        "info": "Maximum fan speed threshold. ABS 'no cooling' ONLY applies to unenclosed printers — enclosed setups often NEED cooling.",
        "sources": [
            {
                "label": "Ellis3DP Cooling",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html",
            },
            {
                "label": "Ellis3DP Misconceptions",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html",
            },
            {"label": "Filament Cheat Sheet", "url": "https://filamentcheatsheet.com/"},
        ],
        "ranges": {
            "PLA": {
                "min": 80,
                "max": 100,
                "typical": 100,
                "sources": [
                    {
                        "label": "Ellis3DP Cooling",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html",
                    }
                ],
            },
            "PETG": {
                "min": 20,
                "max": 60,
                "typical": 50,
                "sources": [
                    {
                        "label": "MatterHackers PETG",
                        "url": "https://www.matterhackers.com/news/how-to-succeed-when-printing-with-petg-filament",
                    },
                    {
                        "label": "Ellis3DP Cooling",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html",
                    },
                ],
            },
            "ABS": {
                "min": 0,
                "max": 100,
                "typical": 0,
                "notes": "Enclosed: 40–100%",
                "sources": [
                    {
                        "label": "Ellis3DP Misconceptions",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html",
                    },
                    {
                        "label": "Ellis3DP Cooling",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html",
                    },
                ],
            },
            "ASA": {
                "min": 0,
                "max": 30,
                "typical": 20,
                "sources": [
                    {
                        "label": "3DTrcek ASA Guide",
                        "url": "https://3dtrcek.com/en/blog/post/how-to-print-asa-filament-a-practical-guide-for-durable-prints-2",
                    }
                ],
            },
            "TPU": {
                "min": 30,
                "max": 80,
                "typical": 60,
                "notes": "30–80% typical; adjust for bridging",
                "sources": [
                    {
                        "label": "Prusa TPU 95A",
                        "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653",
                    },
                    {
                        "label": "Polymaker TPU",
                        "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PA": {
                "min": 0,
                "max": 30,
                "typical": 0,
                "notes": "Low cooling; dry filament essential",
                "sources": [
                    {
                        "label": "All3DP Temps",
                        "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PC": {
                "min": 0,
                "max": 30,
                "typical": 10,
                "notes": "Minimal; reduce to prevent cracking",
                "sources": [
                    {
                        "label": "All3DP Temps",
                        "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/",
                    },
                    {
                        "label": "Polymaker PolyLite PC",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PLA-CF": {
                "min": 80,
                "max": 100,
                "typical": 100,
                "sources": [
                    {
                        "label": "Polymaker Printing Temperature",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
                    }
                ],
            },
            "General": {"min": 0, "max": 100, "typical": 70},
        },
    },
    "overhang_fan_speed": {
        "info": "Typically 100% for PLA overhangs. Force cooling for overhangs improves quality on all materials.",
        "ranges": {
            "PLA": {"min": 80, "max": 100, "typical": 100},
            "General": {"min": 50, "max": 100, "typical": 100},
        },
    },
    # Setting Overrides: Retraction
    "filament_retraction_length": {
        "info": "Direct drive: 0.5–2 mm (hard max 2 mm). Bowden: 1–6 mm. Calibrate in 0.1 mm increments (direct drive) or 0.5 mm (Bowden). Should be calibrated AFTER flow rate and pressure advance.",
        "sources": [
            {
                "label": "Ellis3DP Retraction",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html",
            },
            {
                "label": "Polymaker Travel & Retraction",
                "url": "https://wiki.polymaker.com/the-basics/3d-slicers/travel-and-retraction",
            },
        ],
        "ranges": {
            "PLA": {
                "min": 0.5,
                "max": 4.0,
                "typical": 0.8,
                "notes": "Direct drive: 0.5–1 mm",
                "sources": [
                    {
                        "label": "Ellis3DP Retraction",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html",
                    },
                    {
                        "label": "Polymaker Travel & Retraction",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/travel-and-retraction",
                    },
                ],
            },
            "PETG": {
                "min": 1.0,
                "max": 5.0,
                "typical": 1.5,
                "notes": "More prone to stringing than PLA; tune retraction carefully",
                "sources": [
                    {
                        "label": "Ellis3DP Retraction",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html",
                    },
                    {
                        "label": "Polymaker Travel & Retraction",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/travel-and-retraction",
                    },
                ],
            },
            "ABS": {
                "min": 1.0,
                "max": 4.0,
                "typical": 1.5,
                "sources": [
                    {
                        "label": "Polymaker PolyLite ABS",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs",
                    },
                    {
                        "label": "Ellis3DP Retraction",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html",
                    },
                ],
            },
            "ASA": {
                "min": 1.0,
                "max": 3.0,
                "typical": 1.5,
                "sources": [
                    {
                        "label": "Polymaker ASA",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa",
                    },
                    {
                        "label": "3DTrcek ASA",
                        "url": "https://3dtrcek.com/en/blog/post/how-to-print-asa-filament-a-practical-guide-for-durable-prints-2",
                    },
                ],
            },
            "TPU": {
                "min": 0.0,
                "max": 1.0,
                "typical": 0.5,
                "notes": "Minimal or disabled; Bowden often 0 mm",
                "sources": [
                    {
                        "label": "Prusa TPU 95A",
                        "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653",
                    },
                    {
                        "label": "Overture TPU",
                        "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide",
                    },
                    {
                        "label": "Filament Cheat Sheet",
                        "url": "https://filamentcheatsheet.com/",
                    },
                ],
            },
            "PA": {
                "min": 1.0,
                "max": 6.0,
                "typical": 3.0,
                "sources": [
                    {
                        "label": "Polymaker Nylon (PA)",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa",
                    }
                ],
            },
            "PC": {
                "min": 0.5,
                "max": 3.0,
                "typical": 1.0,
                "sources": [
                    {
                        "label": "Polymaker PolyLite PC",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc",
                    }
                ],
            },
            "PLA-CF": {
                "min": 0.5,
                "max": 2.0,
                "typical": 1.0,
                "notes": "Minimize — fibers clog extruder",
                "sources": [
                    {
                        "label": "Polymaker Printing Temperature",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
                    },
                    {
                        "label": "Simplify3D CF Guide",
                        "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/",
                    },
                ],
            },
            "PETG-CF": {
                "min": 1.0,
                "max": 5.0,
                "typical": 3.0,
                "sources": [
                    {
                        "label": "Polymaker Printing Temperature",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature",
                    }
                ],
            },
            "PA-CF": {
                "min": 1.0,
                "max": 5.0,
                "typical": 3.0,
                "sources": [
                    {
                        "label": "Polymaker Nylon (PA)",
                        "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa",
                    }
                ],
            },
            "General": {"min": 0.5, "max": 5.0, "typical": 1.5},
        },
    },
    "filament_retraction_speed": {
        "info": "Direct drive: 20–35 mm/s (start at 35). Bowden: 30–50 mm/s. Slower retraction speeds often outperform faster ones.",
        "sources": [
            {
                "label": "Ellis3DP Retraction",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html",
            },
            {
                "label": "Polymaker Travel & Retraction",
                "url": "https://wiki.polymaker.com/the-basics/3d-slicers/travel-and-retraction",
            },
            {
                "label": "Teaching Tech Calibration",
                "url": "https://teachingtechyt.github.io/calibration.html",
            },
        ],
        "ranges": {
            "TPU": {
                "min": 10,
                "max": 20,
                "typical": 15,
                "notes": "Short and slow",
                "sources": [
                    {
                        "label": "Overture TPU Guide",
                        "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide",
                    },
                    {
                        "label": "Prusa Flexible Materials",
                        "url": "https://help.prusa3d.com/article/flexible-materials_2057",
                    },
                ],
            },
            "General": {
                "min": 20,
                "max": 50,
                "typical": 30,
                "sources": [
                    {
                        "label": "Ellis3DP Retraction",
                        "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html",
                    },
                    {
                        "label": "Sovol3D Retraction Guide",
                        "url": "https://www.sovol3d.com/blogs/news/adjust-3d-printer-retraction-settings-for-optimal-print-quality",
                    },
                    {
                        "label": "Polymaker Travel & Retraction",
                        "url": "https://wiki.polymaker.com/the-basics/3d-slicers/travel-and-retraction",
                    },
                    {
                        "label": "Teaching Tech Calibration",
                        "url": "https://teachingtechyt.github.io/calibration.html",
                    },
                ],
            },
        },
    },
    "filament_deretraction_speed": {
        "info": "Typically same as retraction speed. Ellis3DP: test at 30 mm/s for both retract and unretract.",
        "sources": [
            {
                "label": "Ellis3DP Retraction",
                "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html",
            },
        ],
        "ranges": {
            "General": {"min": 20, "max": 50, "typical": 30},
        },
    },
    "filament_z_hop": {
        "info": "Helps prevent nozzle dragging across printed surfaces during travel. Too high = more stringing from ooze during travel.",
        "ranges": {
            "General": {"min": 0.0, "max": 0.6, "typical": 0.3},
        },
    },
}

# Alias bed temp initial layer entries to point to the same ranges
for _plate in ("hot_plate_temp", "textured_plate_temp"):
    _il_key = f"{_plate}_initial_layer"
    if _plate in RECOMMENDATIONS and _il_key not in RECOMMENDATIONS:
        RECOMMENDATIONS[_il_key] = {
            "info": RECOMMENDATIONS[_plate]["info"].replace(
                "(other layers)", "(initial layer)"
            ),
            "sources": RECOMMENDATIONS[_plate].get("sources", []),
            "ranges": RECOMMENDATIONS[_plate]["ranges"],
        }
for _name in ("_plate", "_il_key"):
    vars().pop(_name, None)


# --- Enum Value Mappings ---
# Maps JSON parameter values to human-readable labels.

ENUM_VALUES = {
    # Process: Quality
    "seam_position": [
        ("nearest", "Nearest"),
        ("aligned", "Aligned"),
        ("aligned_back", "Aligned Back"),
        ("back", "Back"),
        ("random", "Random"),
    ],
    "scarf_seam_application": [
        ("none", "None"),
        ("external", "External"),
        ("all", "All"),
    ],
    "wall_generator": [
        ("classic", "Classic"),
        ("arachne", "Arachne"),
    ],
    "wall_sequence": [
        ("inner wall/outer wall", "Inner Wall / Outer Wall"),
        ("outer wall/inner wall", "Outer Wall / Inner Wall"),
        ("inner-outer-inner wall", "Inner-Outer-Inner Wall"),
    ],
    "top_one_wall_type": [
        ("none", "None"),
        ("all top", "All Top"),
        ("topmost", "Topmost"),
    ],
    # Process: Strength — surface/infill patterns
    "top_surface_pattern": [
        ("monotonic", "Monotonic"),
        ("monotonicline", "Monotonic Line"),
        ("rectilinear", "Rectilinear"),
        ("alignedrectilinear", "Aligned Rectilinear"),
        ("concentric", "Concentric"),
        ("hilbertcurve", "Hilbert Curve"),
        ("archimedeanchords", "Archimedean Chords"),
        ("octagramspiral", "Octagram Spiral"),
    ],
    "bottom_surface_pattern": [
        ("monotonic", "Monotonic"),
        ("monotonicline", "Monotonic Line"),
        ("rectilinear", "Rectilinear"),
        ("alignedrectilinear", "Aligned Rectilinear"),
        ("concentric", "Concentric"),
        ("hilbertcurve", "Hilbert Curve"),
        ("archimedeanchords", "Archimedean Chords"),
        ("octagramspiral", "Octagram Spiral"),
    ],
    "internal_solid_infill_pattern": [
        ("monotonic", "Monotonic"),
        ("monotonicline", "Monotonic Line"),
        ("rectilinear", "Rectilinear"),
        ("alignedrectilinear", "Aligned Rectilinear"),
        ("concentric", "Concentric"),
        ("hilbertcurve", "Hilbert Curve"),
        ("archimedeanchords", "Archimedean Chords"),
        ("octagramspiral", "Octagram Spiral"),
    ],
    "sparse_infill_pattern": [
        ("grid", "Grid"),
        ("triangles", "Triangles"),
        ("tri-hexagon", "Tri-Hexagon"),
        ("cubic", "Cubic"),
        ("adaptivecubic", "Adaptive Cubic"),
        ("quartercubic", "Quarter Cubic"),
        ("supportcubic", "Support Cubic"),
        ("gyroid", "Gyroid"),
        ("honeycomb", "Honeycomb"),
        ("3dhoneycomb", "3D Honeycomb"),
        ("lateral-honeycomb", "Lateral Honeycomb"),
        ("lateral-lattice", "Lateral Lattice"),
        ("crosshatch", "Crosshatch"),
        ("lightning", "Lightning"),
        ("line", "Line"),
        ("rectilinear", "Rectilinear"),
        ("alignedrectilinear", "Aligned Rectilinear"),
        ("concentric", "Concentric"),
        ("zigzag", "Zig Zag"),
        ("crosszag", "Cross Zag"),
        ("lockedzag", "Locked Zag"),
        ("tpmsd", "TPMS-D"),
        ("tpmsfk", "TPMS-FK"),
        ("hilbertcurve", "Hilbert Curve"),
        ("archimedeanchords", "Archimedean Chords"),
        ("octagramspiral", "Octagram Spiral"),
    ],
    # Process: Support
    "support_type": [
        ("normal(auto)", "Normal (Auto)"),
        ("tree(auto)", "Tree (Auto)"),
        ("normal(manual)", "Normal (Manual)"),
        ("tree(manual)", "Tree (Manual)"),
    ],
    "support_style": [
        ("default", "Default"),
        ("grid", "Grid"),
        ("snug", "Snug"),
        ("organic", "Organic"),
        ("tree_slim", "Tree Slim"),
        ("tree_strong", "Tree Strong"),
        ("tree_hybrid", "Tree Hybrid"),
    ],
    "support_base_pattern": [
        ("default", "Default"),
        ("rectilinear", "Rectilinear"),
        ("rectilinear-grid", "Rectilinear Grid"),
        ("honeycomb", "Honeycomb"),
        ("lightning", "Lightning"),
        ("hollow", "Hollow"),
    ],
    "support_interface_pattern": [
        ("auto", "Auto"),
        ("rectilinear", "Rectilinear"),
        ("concentric", "Concentric"),
        ("rectilinear_interlaced", "Rectilinear Interlaced"),
        ("grid", "Grid"),
    ],
    # Process: Others
    "slicing_mode": [
        ("regular", "Regular"),
        ("even_odd", "Even-Odd"),
        ("close_holes", "Close Holes"),
    ],
    "print_sequence": [
        ("by layer", "By Layer"),
        ("by object", "By Object"),
    ],
    "timelapse_type": [
        ("0", "Traditional"),
        ("1", "Smooth"),
    ],
    "fuzzy_skin": [
        ("none", "None"),
        ("external", "External"),
        ("all", "All"),
        ("allwalls", "All Walls"),
    ],
    "brim_type": [
        ("auto_brim", "Auto"),
        ("outer_only", "Outer Only"),
        ("inner_only", "Inner Only"),
        ("outer_and_inner", "Outer and Inner"),
        ("brim_ears", "Brim Ears"),
        ("painted", "Painted"),
        ("no_brim", "No Brim"),
    ],
    "ensure_vertical_shell_thickness": [
        ("none", "None"),
        ("ensure_critical_only", "Critical Only"),
        ("ensure_moderate", "Moderate"),
        ("ensure_all", "All"),
    ],
    # Filament
    "filament_type": [
        ("PLA", "PLA"),
        ("PLA-CF", "PLA-CF"),
        ("PETG", "PETG"),
        ("PETG-CF", "PETG-CF"),
        ("ABS", "ABS"),
        ("ASA", "ASA"),
        ("TPU", "TPU"),
        ("PA", "PA"),
        ("PA-CF", "PA-CF"),
        ("PA-GF", "PA-GF"),
        ("PA6-CF", "PA6-CF"),
        ("PA6-GF", "PA6-GF"),
        ("PC", "PC"),
        ("PC-CF", "PC-CF"),
        ("PVA", "PVA"),
        ("HIPS", "HIPS"),
        ("PET-CF", "PET-CF"),
        ("PP", "PP"),
        ("PP-CF", "PP-CF"),
        ("PP-GF", "PP-GF"),
        ("PPS", "PPS"),
        ("PPS-CF", "PPS-CF"),
        ("PPA-CF", "PPA-CF"),
        ("PPA-GF", "PPA-GF"),
    ],
    "filament_z_hop_type": [
        ("auto", "Auto"),
        ("normal", "Normal"),
        ("slope", "Slope"),
        ("spiral", "Spiral"),
    ],
    "filament_scarf_seam_type": [
        ("none", "None"),
        ("external", "External"),
        ("all", "All"),
    ],
}

# Build reverse lookup: human label → json value, per parameter
_ENUM_LABEL_TO_JSON = {}
for _ekey, _evals in ENUM_VALUES.items():
    _ENUM_LABEL_TO_JSON[_ekey] = {label: jval for jval, label in _evals}

# Build forward lookup: json value → human label, per parameter
_ENUM_JSON_TO_LABEL = {}
for _ekey, _evals in ENUM_VALUES.items():
    _ENUM_JSON_TO_LABEL[_ekey] = {jval: label for jval, label in _evals}

# --- Printer & Filament Database ---

_KNOWN_PRINTERS = {
    "Bambu Lab": [
        "Bambu Lab X1 Carbon",
        "Bambu Lab X1",
        "Bambu Lab X1E",
        "Bambu Lab P1S",
        "Bambu Lab P1P",
        "Bambu Lab P2S",
        "Bambu Lab A1",
        "Bambu Lab A1 mini",
        "Bambu Lab A1 combo",
    ],
    "Prusa": [
        "Prusa MK4",
        "Prusa MK4S",
        "Prusa MK3.9",
        "Prusa MK3S+",
        "Prusa MINI+",
        "Prusa XL",
        "Prusa CORE One",
    ],
    "Creality": [
        "Creality K1",
        "Creality K1 Max",
        "Creality K1C",
        "Creality Ender-3 V3",
    ],
    "Voron": ["Voron 0.2", "Voron 2.4", "Voron Trident"],
}
_NOZZLE_SIZES = ["0.2", "0.4", "0.6", "0.8", "1.0"]

# All BambuStudio-recognized printer strings.  Used by make_universal() to
# add every known printer so the profile is usable on any BBL machine.
# BambuStudio treats compatible_printers as a whitelist — an empty list means
# "compatible with nothing", NOT "compatible with everything".
_ALL_BBL_PRINTERS = [
    f"Bambu Lab {model} {nz} nozzle"
    for model in [
        "X1 Carbon",
        "X1",
        "X1E",
        "P1S",
        "P1P",
        "P2S",
        "A1",
        "A1 mini",
        "H2C",
        "H2D",
        "H2D Pro",
        "H2S",
    ]
    for nz in ["0.2", "0.4", "0.6", "0.8"]
]

_KNOWN_VENDORS = [
    "Bambu",
    "Bambu Lab",
    "BBL",
    "eSUN",
    "Extrudr",
    "Polymaker",
    "PolyTerra",
    "PolyLite",
    "Prusament",
    "Prusa",
    "Hatchbox",
    "Overture",
    "Sunlu",
    "Inland",
    "MatterHackers",
    "ColorFabb",
    "NinjaTek",
    "3DXTech",
    "Atomic",
    "Protopasta",
    "Fiberlogy",
    "Fillamentum",
    "FormFutura",
    "Verbatim",
    "AzureFilm",
    "Das Filament",
    "add:north",
    "Spectrum",
    "Generic",
]
_FILAMENT_TYPES = {
    "PLA",
    "ABS",
    "PETG",
    "TPU",
    "ASA",
    "HIPS",
    "PVA",
    "PC",
    "PA",
    "PP",
    "PET",
    "PCTG",
    "POM",
    "PVDF",
}

# Smart defaults for missing conversion params — shown as suggestions, not auto-filled.
# Each entry: key → (default_value, rationale)
CONVERSION_DEFAULTS: dict[str, tuple[object, str]] = {
    # PrusaSlicer defaults (from factory profiles)
    "cooling": (1, "Enable cooling — required for most materials except ABS/ASA"),
    "fan_always_on": (1, "Keep fan running after first layers — PrusaSlicer default"),
    "fan_below_layer_time": (
        60,
        "Slow down if layer prints faster than 60s — PrusaSlicer default",
    ),
    "slowdown_below_layer_time": (5, "Slow down for very short layers under 5s"),
    "enable_dynamic_fan_speeds": (0, "Dynamic fan speeds off — PrusaSlicer default"),
    "filament_retract_before_travel": (2, "Retract before travel moves over 2mm"),
    "filament_retract_before_wipe": (0, "No retraction before wipe — standard default"),
    "filament_retract_layer_change": (0, "No extra retraction on layer change"),
    "filament_retract_length_toolchange": (
        10,
        "10mm retraction for toolchange — MMU default",
    ),
    "filament_retract_restart_extra": (0, "No extra restart after retraction"),
    "filament_retract_restart_extra_toolchange": (
        0,
        "No extra restart after toolchange",
    ),
    "filament_retract_lift": (
        0,
        "No Z-lift on retraction — set per-material if needed",
    ),
    "filament_wipe": (0, "Wipe disabled — enable for stringing-prone materials"),
    "filament_load_time": (0, "Load time 0 — only relevant for MMU setups"),
    "filament_unload_time": (0, "Unload time 0 — only relevant for MMU setups"),
    "filament_abrasive": (0, "Not abrasive — enable for CF/GF filled filaments"),
    "filament_purge_multiplier": (
        1,
        "Standard purge amount — increase for color changes",
    ),
    "filament_spool_weight": (0, "Spool weight unknown — weigh empty spool to set"),
    "filament_settings_id": ("", "Auto-generated by PrusaSlicer on save"),
}
