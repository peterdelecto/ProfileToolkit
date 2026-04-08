#!/usr/bin/env python3
"""
Print Profile Converter v2.2.0
===============================
Cross-platform GUI for unlocking/converting 3D printer slicer profiles.
Mirrors BambuStudio's exact UI layout. OrcaSlicer-inspired teal theme.

No external dependencies — Python standard library + tkinter.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import zipfile
import xml.etree.ElementTree as ET
import os
import sys
import platform
import re
import subprocess
from pathlib import Path
from copy import deepcopy
from datetime import datetime


APP_NAME = "Print Profile Converter"
APP_VERSION = "2.2.0"

# Cross-platform UI font family
_SYS = platform.system()
if _SYS == "Darwin":
    UI_FONT = "SF Pro"          # San Francisco (macOS 10.11+)
elif _SYS == "Windows":
    UI_FONT = "Segoe UI"        # Windows Vista+
else:
    UI_FONT = "DejaVu Sans"     # Widely available on Linux

# --- UI Geometry Constants ---
_WIN_WIDTH = 1300
_WIN_HEIGHT = 780
_DLG_COMPARE_WIDTH = 960
_DLG_COMPARE_HEIGHT = 650
_DLG_COMPARE_MIN_WIDTH = 750
_DLG_COMPARE_MIN_HEIGHT = 450
_TREE_ROW_HEIGHT = 26
_TREE_TOOLTIP_DELAY_MS = 600
_VALUE_TRUNCATE_SHORT = 40   # CompareDialog._fmt
_VALUE_TRUNCATE_LONG = 80    # ProfileDetailPanel._format_value
_LABEL_COL_WIDTH = 220       # ProfileDetailPanel two-column grid
_TOOLTIP_BORDER_COLOR = "#555555"  # _Tooltip border — not theme-dependent


# --- BambuStudio UI Layout Definitions ---
# Each entry: (json_key, ui_label)
# Ordering matches BambuStudio's UI exactly (from screenshots + source code).

PROCESS_LAYOUT = {
    "Quality": {
        "Layer height": [
            ("layer_height", "Layer height"),
            ("initial_layer_print_height", "Initial layer height"),
        ],
        "Line width": [
            ("line_width", "Default"),
            ("initial_layer_line_width", "Initial layer"),
            ("outer_wall_line_width", "Outer wall"),
            ("inner_wall_line_width", "Inner wall"),
            ("top_surface_line_width", "Top surface"),
            ("sparse_infill_line_width", "Sparse infill"),
            ("internal_solid_infill_line_width", "Internal solid infill"),
            ("support_line_width", "Support"),
        ],
        "Seam": [
            ("seam_position", "Seam position"),
            ("staggered_inner_seams", "Staggered inner seams"),
            ("seam_slope_conditional", "Seam placement away from overhangs(experimental)"),
            ("seam_gap", "Seam gap"),
            ("scarf_seam_application", "Smart scarf seam application"),
            ("scarf_angle_threshold", "Scarf application angle threshold"),
            ("scarf_overhang", "Scarf around entire wall"),
            ("scarf_steps", "Scarf steps"),
            ("scarf_joint_inner_walls", "Scarf joint for inner walls"),
            ("override_filament_scarf_seam", "Override filament scarf seam setting"),
            ("wipe_speed", "Wipe speed"),
            ("role_based_wipe_speed", "Role-based wipe speed"),
        ],
        "Precision": [
            ("slice_closing_radius", "Slice gap closing radius"),
            ("resolution", "Resolution"),
            ("enable_arc_fitting", "Arc fitting"),
            ("xy_hole_compensation", "X-Y hole compensation"),
            ("xy_contour_compensation", "X-Y contour compensation"),
        ],
        "Wall generator": [
            ("wall_generator", "Wall generator"),
        ],
        "Advanced": [
            ("wall_sequence", "Order of walls"),
            ("is_infill_first", "Print infill first"),
            ("bridge_flow", "Bridge flow"),
            ("thick_bridges", "Thick bridges"),
            ("top_solid_infill_flow_ratio", "Top surface flow ratio"),
            ("initial_layer_flow_ratio", "Initial layer flow ratio"),
            ("top_one_wall_type", "Only one wall on top surfaces"),
            ("top_area_threshold", "Top area threshold"),
            ("only_one_wall_first_layer", "Only one wall on first layer"),
            ("detect_overhang_walls", "Detect overhang walls"),
            ("smooth_speed_discontinuity_area", "Smooth speed discontinuity area"),
            ("smooth_coefficient", "Smooth coefficient"),
            ("reduce_crossing_wall", "Avoid crossing wall"),
            ("smoothing_wall_speed_along_z", "Smoothing wall speed along Z(experimental)"),
        ],
    },
    "Strength": {
        "Walls": [
            ("wall_loops", "Wall loops"),
            ("embed_wall_infill", "Embedding the wall into the infill"),
            ("detect_thin_wall", "Detect thin wall"),
        ],
        "Top/bottom shells": [
            ("interface_shells", "Interface shells"),
            ("top_surface_pattern", "Top surface pattern"),
            ("top_surface_density", "Top surface density"),
            ("top_shell_layers", "Top shell layers"),
            ("top_shell_thickness", "Top shell thickness"),
            ("top_paint_penetration_layers", "Top paint penetration layers"),
            ("bottom_surface_pattern", "Bottom surface pattern"),
            ("bottom_surface_density", "Bottom surface density"),
            ("bottom_shell_layers", "Bottom shell layers"),
            ("bottom_shell_thickness", "Bottom shell thickness"),
            ("bottom_paint_penetration_layers", "Bottom paint penetration layers"),
            ("internal_solid_infill_pattern", "Internal solid infill pattern"),
        ],
        "Sparse infill": [
            ("sparse_infill_density", "Sparse infill density"),
            ("fill_multiline", "Fill multiline"),
            ("sparse_infill_pattern", "Sparse infill pattern"),
            ("infill_anchor", "Length of sparse infill anchor"),
            ("infill_anchor_max", "Maximum length of sparse infill anchor"),
            ("filter_out_gap_fill", "Filter out tiny gaps"),
        ],
        "Advanced": [
            ("infill_wall_overlap", "Infill/Wall overlap"),
            ("infill_direction", "Infill direction"),
            ("bridge_angle", "Bridge direction"),
            ("minimum_sparse_infill_area", "Minimum sparse infill threshold"),
            ("infill_combination", "Infill combination"),
            ("detect_narrow_internal_solid_infill", "Detect narrow internal solid infill"),
            ("ensure_vertical_shell_thickness", "Ensure vertical shell thickness"),
            ("detect_floating_vertical_shell", "Detect floating vertical shells"),
        ],
    },
    "Speed": {
        "Initial layer speed": [
            ("initial_layer_speed", "Initial layer"),
            ("initial_layer_infill_speed", "Initial layer infill"),
        ],
        "Other layers speed": [
            ("outer_wall_speed", "Outer wall"),
            ("inner_wall_speed", "Inner wall"),
            ("small_perimeter_speed", "Small perimeters"),
            ("small_perimeter_threshold", "Small perimeter threshold"),
            ("sparse_infill_speed", "Sparse infill"),
            ("internal_solid_infill_speed", "Internal solid infill"),
            ("vertical_shell_speed", "Vertical shell speed"),
            ("top_surface_speed", "Top surface"),
            ("enable_overhang_speed", "Slow down for overhangs"),
            ("overhang_1_4_speed", "Overhang speed 10%"),
            ("overhang_2_4_speed", "Overhang speed 25%"),
            ("overhang_3_4_speed", "Overhang speed 50%"),
            ("overhang_4_4_speed", "Overhang speed 75%"),
            ("overhang_totally_speed", "Overhang speed 100%"),
            ("slow_down_by_height", "Slow down by height"),
            ("bridge_speed", "Bridge"),
            ("gap_infill_speed", "Gap infill"),
            ("support_speed", "Support"),
            ("support_interface_speed", "Support interface"),
        ],
        "Travel speed": [
            ("travel_speed", "Travel"),
        ],
        "Acceleration": [
            ("default_acceleration", "Normal printing"),
            ("travel_acceleration", "Travel"),
            ("travel_short_distance_acceleration", "Short travel"),
            ("initial_layer_travel_acceleration", "Initial layer travel"),
            ("initial_layer_acceleration", "Initial layer"),
            ("outer_wall_acceleration", "Outer wall"),
            ("inner_wall_acceleration", "Inner wall"),
            ("top_surface_acceleration", "Top surface"),
            ("sparse_infill_acceleration", "Sparse infill"),
            ("internal_solid_infill_acceleration", "Internal solid infill"),
            ("bridge_acceleration", "Bridge"),
        ],
        "Jerk": [
            ("default_jerk", "Normal printing"),
            ("outer_wall_jerk", "Outer wall"),
            ("inner_wall_jerk", "Inner wall"),
            ("top_surface_jerk", "Top surface"),
            ("infill_jerk", "Infill"),
            ("initial_layer_jerk", "Initial layer"),
            ("travel_jerk", "Travel"),
        ],
    },
    "Support": {
        "Support": [
            ("enable_support", "Enable support"),
            ("support_type", "Type"),
            ("support_style", "Style"),
            ("support_threshold_angle", "Threshold angle"),
            ("support_on_build_plate_only", "On build plate only"),
            ("support_remove_small_overhang", "Remove small overhangs"),
        ],
        "Raft": [
            ("raft_layers", "Raft layers"),
        ],
        "Filament for Supports": [
            ("support_filament", "Support/raft base"),
            ("support_interface_filament", "Support/raft interface"),
        ],
        "Support ironing": [
            ("support_interface_ironing", "Enable ironing support interface"),
        ],
        "Advanced": [
            ("support_base_pattern_density", "Initial layer density"),
            ("support_expansion", "Initial layer expansion"),
            ("support_wall_loops", "Support wall loops"),
            ("support_top_z_distance", "Top Z distance"),
            ("support_bottom_z_distance", "Bottom Z distance"),
            ("support_base_pattern", "Base pattern"),
            ("support_base_pattern_spacing", "Base pattern spacing"),
            ("support_angle", "Pattern angle"),
            ("support_interface_top_layers", "Top interface layers"),
            ("support_interface_bottom_layers", "Bottom interface layers"),
            ("support_interface_pattern", "Interface pattern"),
            ("support_interface_spacing", "Top interface spacing"),
            ("support_bottom_interface_spacing", "Bottom interface spacing"),
            ("support_normal_expansion", "Normal Support expansion"),
            ("support_object_xy_distance", "Support/object xy distance"),
            ("z_overrides_xy", "Z overrides X/Y"),
            ("support_object_first_layer_gap", "Support/object first layer gap"),
            ("bridge_no_support", "Don't support bridges"),
            ("independent_support_layer_height", "Independent support layer height"),
        ],
    },
    "Others": {
        "Bed adhesion": [
            ("skirt_loops", "Skirt loops"),
            ("skirt_height", "Skirt height"),
            ("skirt_distance", "Skirt distance"),
            ("brim_type", "Brim type"),
            ("brim_width", "Brim width"),
            ("brim_object_gap", "Brim-object gap"),
        ],
        "Prime tower": [
            ("enable_prime_tower", "Enable"),
            ("prime_tower_skip_points", "Skip points"),
            ("prime_tower_internal_ribs", "Internal ribs"),
            ("prime_tower_width", "Width"),
            ("prime_tower_max_speed", "Max speed"),
            ("prime_tower_brim_width", "Brim width"),
            ("prime_tower_infill_gap", "Infill gap"),
            ("prime_tower_rib_wall", "Rib wall"),
            ("prime_tower_extra_rib_length", "Extra rib length"),
            ("prime_tower_rib_width", "Rib width"),
            ("prime_tower_fillet_wall", "Fillet wall"),
        ],
        "Purge options": [
            ("purge_in_prime_tower_infill", "Purge into objects' infill"),
            ("purge_in_prime_tower_support", "Purge into objects' support"),
        ],
        "Special mode": [
            ("slicing_mode", "Slicing Mode"),
            ("print_sequence", "Print sequence"),
            ("spiral_mode", "Spiral vase"),
            ("timelapse_type", "Timelapse"),
            ("fuzzy_skin", "Fuzzy Skin"),
            ("fuzzy_skin_point_dist", "Fuzzy skin point distance"),
            ("fuzzy_skin_thickness", "Fuzzy skin thickness"),
        ],
        "Advanced": [
            ("enable_clumping_detection", "Enable clumping detection by probing"),
            ("use_beam_interlocking", "Use beam interlocking"),
            ("interlocking_depth", "Interlocking depth of a segmented region"),
        ],
        "G-code output": [
            ("reduce_infill_retraction", "Reduce infill retraction"),
            ("add_line_number", "Add line number"),
            ("filename_format", "Filename format"),
        ],
        "Post-processing scripts": [
            ("post_process", "Post-processing scripts"),
        ],
    },
}

FILAMENT_LAYOUT = {
    "Filament": {
        "Basic information": [
            ("filament_type", "Type"),
            ("filament_vendor", "Vendor"),
            ("filament_soluble", "Soluble material"),
            ("filament_is_support", "Support material"),
            ("impact_strength_z", "Impact Strength Z"),
            ("required_nozzle_HRC", "Required nozzle HRC"),
            ("filament_colour", "Default color"),
            ("filament_diameter", "Diameter"),
            ("adhesiveness_category", "Adhesiveness Category"),
            ("filament_flow_ratio", "Flow ratio"),
            ("filament_density", "Density"),
            ("filament_shrink", "Shrinkage"),
            ("velocity_adaptation_factor", "Velocity Adaptation Factor"),
            ("filament_cost", "Price"),
            ("softening_temperature", "Softening temperature"),
            ("wipe_tower_cooling", "Wipe tower cooling"),
            ("interface_layer_pre_extrusion_distance", "Interface layer pre-extrusion distance"),
            ("interface_layer_pre_extrusion_length", "Interface layer pre-extrusion length"),
            ("tower_ironing_area", "Tower ironing area"),
            ("interface_layer_purge_length", "Interface layer purge length"),
            ("interface_layer_print_temperature", "Interface layer print temperature"),
            ("filament_prime_volume", "Filament prime volume"),
            ("filament_ramming_length", "Filament ramming length"),
            ("travel_time_after_ramming", "Travel time after ramming"),
            ("precooling_target_temperature", "Precooling target temperature"),
            ("nozzle_temperature_range_low", "Recommended nozzle temperature (Min)"),
            ("nozzle_temperature_range_high", "Recommended nozzle temperature (Max)"),
        ],
        "Print temperature": [
            ("supertack_plate_temp_initial_layer", "Cool Plate SuperTack (Initial layer)"),
            ("supertack_plate_temp", "Cool Plate SuperTack (Other layers)"),
            ("cool_plate_temp_initial_layer", "Cool Plate (Initial layer)"),
            ("cool_plate_temp", "Cool Plate (Other layers)"),
            ("eng_plate_temp_initial_layer", "Engineering Plate (Initial layer)"),
            ("eng_plate_temp", "Engineering Plate (Other layers)"),
            ("hot_plate_temp_initial_layer", "Smooth PEI Plate / High Temp Plate (Initial layer)"),
            ("hot_plate_temp", "Smooth PEI Plate / High Temp Plate (Other layers)"),
            ("textured_plate_temp_initial_layer", "Textured PEI Plate (Initial layer)"),
            ("textured_plate_temp", "Textured PEI Plate (Other layers)"),
            ("nozzle_temperature_initial_layer", "Nozzle (Initial layer)"),
            ("nozzle_temperature", "Nozzle (Other layers)"),
        ],
        "Volumetric speed limitation": [
            ("adaptive_volumetric_speed", "Adaptive volumetric speed"),
            ("filament_max_volumetric_speed", "Max volumetric speed"),
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
            ("close_fan_the_first_x_layers", "Special cooling settings (layers)"),
            ("first_x_layer_fan_speed", "Fan speed"),
        ],
        "Part cooling fan": [
            ("fan_min_speed", "Min fan speed threshold (Fan speed)"),
            ("fan_min_speed_layer_time", "Min fan speed threshold (Layer time)"),
            ("fan_max_speed", "Max fan speed threshold (Fan speed)"),
            ("fan_max_speed_layer_time", "Max fan speed threshold (Layer time)"),
            ("reduce_fan_stop_start_freq", "Keep fan always on"),
            ("slow_down_for_layer_cooling", "Slow printing down for better layer cooling"),
            ("dont_slow_down_outer_walls", "Don't slow down outer walls"),
            ("cooling_slowdown_logic", "Cooling slowdown logic"),
            ("perimeter_transition_distance", "Perimeter transition distance"),
            ("slow_down_min_speed", "Min print speed"),
            ("force_cooling_for_overhangs", "Force cooling for overhangs and bridges"),
            ("cooling_overhang_threshold", "Cooling overhang threshold"),
            ("overhang_threshold_for_participating_cooling", "Overhang threshold for participating cooling"),
            ("overhang_fan_speed", "Fan speed for overhangs"),
            ("pre_start_fan_time", "Pre start fan time"),
        ],
        "Auxiliary part cooling fan": [
            ("auxiliary_fan_speed", "Fan speed"),
        ],
    },
    "Setting Overrides": {
        "Retraction": [
            ("filament_retraction_length", "Length"),
            ("filament_z_hop", "Z hop when retract"),
            ("filament_z_hop_type", "Z Hop Type"),
            ("filament_retraction_speed", "Retraction Speed"),
            ("filament_deretraction_speed", "Deretraction Speed"),
            ("retract_length_toolchange", "Length when change hotend"),
            ("filament_unretraction_extra_length", "Extra length on restart"),
            ("travel_distance_threshold", "Travel distance threshold"),
            ("retract_when_changing_layer", "Retract when change layer"),
            ("wipe_while_retracting", "Wipe while retracting"),
            ("filament_wipe_distance", "Wipe Distance"),
            ("retract_amount_before_wipe", "Retract amount before wipe"),
            ("long_retraction_when_cut", "Long retraction when cut (experimental)"),
        ],
        "Speed": [
            ("override_overhang_speed", "Override overhang speed"),
        ],
    },
    "Advanced": {
        "Filament start G-code": [
            ("filament_start_gcode", "Filament start G-code"),
        ],
        "Filament end G-code": [
            ("filament_end_gcode", "Filament end G-code"),
        ],
    },
    "Notes": {
        "Notes": [
            ("filament_notes", "Notes"),
        ],
    },
    "Multi Filament": {
    },
}

# Build key sets for each layout
_ALL_PROCESS_KEYS = set()
for _tab_sections in PROCESS_LAYOUT.values():
    for _params in _tab_sections.values():
        for _key, _label in _params:
            _ALL_PROCESS_KEYS.add(_key)

_ALL_FILAMENT_KEYS = set()
for _tab_sections in FILAMENT_LAYOUT.values():
    for _params in _tab_sections.values():
        for _key, _label in _params:
            _ALL_FILAMENT_KEYS.add(_key)

# Identity/meta keys: profile bookkeeping fields shown in the header,
# not as editable parameters. Excluded from tab layout and diff views.
_IDENTITY_KEYS = {
    "name", "type", "inherits", "from", "setting_id",
    "compatible_printers", "compatible_printers_condition",
    "printer_settings_id", "version", "is_custom_defined",
    "instantiation", "user_id", "updated_time",
}

# Keys that strongly indicate a filament profile
_FILAMENT_SIGNAL_KEYS = frozenset({
    "filament_type", "nozzle_temperature", "filament_flow_ratio",
    "fan_min_speed", "filament_retraction_length",
    "nozzle_temperature_initial_layer", "cool_plate_temp",
    "filament_max_volumetric_speed",
})

# Keys that strongly indicate a process/print profile
_PROCESS_SIGNAL_KEYS = frozenset({
    "layer_height", "wall_loops", "sparse_infill_density",
    "support_type", "print_speed", "hot_plate_temp",
})

# Keys that identify any profile data (either type)
_PROFILE_SIGNAL_KEYS = _FILAMENT_SIGNAL_KEYS | _PROCESS_SIGNAL_KEYS | frozenset({
    "compatible_printers", "inherits", "from",
})


# --- Enum Parameter Definitions ---
# Each key maps to a list of (json_value, human_label) tuples.
# If a profile contains a value not in this list, it is auto-humanized and
# appended to the dropdown so nothing is ever lost.

ENUM_VALUES = {
    # ── Process: Quality ──
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

    # ── Process: Strength — surface/infill patterns ──
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

    # ── Process: Support ──
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

    # ── Process: Others ──
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

    # ── Filament ──
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
del _ekey, _evals


def _humanize_enum_value(raw_value: str) -> str:
    """Auto-humanize an unknown enum value for display.
    monotonicline → Monotonic Line, even_odd → Even Odd,
    rectilinear-grid → Rectilinear Grid, tree(auto) → Tree (Auto)."""
    raw = str(raw_value)
    # Insert space before uppercase runs (camelCase splitting)
    raw = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw)
    # Insert space between lowercase-to-digit and digit-to-lowercase
    raw = re.sub(r'(?<=[a-z])(?=\d)', ' ', raw)
    raw = re.sub(r'(?<=\d)(?=[a-z])', ' ', raw)
    # Replace underscores and hyphens with spaces
    raw = raw.replace('_', ' ').replace('-', ' ')
    # Title-case each word, but preserve content in parentheses
    parts = re.split(r'(\([^)]*\))', raw)
    result = []
    for part in parts:
        if part.startswith('('):
            # Capitalize first letter inside parens
            inner = part[1:-1].strip().capitalize()
            result.append(f"({inner})")
        else:
            result.append(' '.join(w.capitalize() for w in part.split()))
    return ' '.join(result).strip()


def _get_enum_human_label(key: str, raw_value) -> str:
    """Get the human-readable label for a parameter value.
    Returns the known label if found, otherwise auto-humanizes."""
    s = str(raw_value)
    lookup = _ENUM_JSON_TO_LABEL.get(key)
    if lookup and s in lookup:
        return lookup[s]
    return _humanize_enum_value(s)


# --- Known Printers & Nozzles ---

KNOWN_PRINTERS = {
    "Bambu Lab": [
        "Bambu Lab X1 Carbon", "Bambu Lab X1", "Bambu Lab X1E",
        "Bambu Lab P1S", "Bambu Lab P1P", "Bambu Lab P2S",
        "Bambu Lab A1", "Bambu Lab A1 mini", "Bambu Lab A1 combo",
    ],
    "Prusa": [
        "Prusa MK4", "Prusa MK4S", "Prusa MK3.9", "Prusa MK3S+",
        "Prusa MINI+", "Prusa XL", "Prusa CORE One",
    ],
    "Creality": [
        "Creality K1", "Creality K1 Max", "Creality K1C", "Creality Ender-3 V3",
    ],
    "Voron": ["Voron 0.2", "Voron 2.4", "Voron Trident"],
}
NOZZLE_SIZES = ["0.2", "0.4", "0.6", "0.8", "1.0"]

_KNOWN_VENDORS = [
    "Bambu", "Bambu Lab", "BBL", "eSUN", "Extrudr", "Polymaker",
    "PolyTerra", "PolyLite", "Prusament", "Prusa", "Hatchbox",
    "Overture", "Sunlu", "Inland", "MatterHackers", "ColorFabb",
    "NinjaTek", "3DXTech", "Atomic", "Protopasta", "Fiberlogy",
    "Fillamentum", "FormFutura", "Verbatim", "AzureFilm",
    "Das Filament", "add:north", "Spectrum", "Generic",
]
_FILAMENT_TYPES = {"PLA", "ABS", "PETG", "TPU", "ASA", "HIPS", "PVA",
                   "PC", "PA", "PP", "PET", "PCTG", "POM", "PVDF"}


# --- Preset Index — resolves inheritance chains ---

class PresetIndex:
    """
    Indexes all presets (system + user) from a slicer directory so we can
    resolve inheritance chains.  Call build() once per slicer path, then
    resolve(profile) to fill in inherited parameters.
    """

    # Typical slicer directory layouts
    SYSTEM_SUBDIRS = {
        "BambuStudio": ["system"],
        "OrcaSlicer": ["system"],
        "PrusaSlicer": ["vendor"],
    }

    def __init__(self):
        self._by_name = {}  # name → dict of raw JSON data

    def build(self, slicer_path: str, slicer_name: str = ""):
        """Scan a slicer directory and index all presets by name."""
        # Index user presets
        user_dir = os.path.join(slicer_path, "user")
        if os.path.isdir(user_dir):
            self._scan_dir(user_dir)

        # Index system presets
        for subdir in self.SYSTEM_SUBDIRS.get(slicer_name, ["system", "vendor"]):
            sys_dir = os.path.join(slicer_path, subdir)
            if os.path.isdir(sys_dir):
                self._scan_dir(sys_dir)

    def _scan_dir(self, directory: str):
        """Recursively scan for .json preset files."""
        for root, dirs, files in os.walk(directory):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "name" in data:
                        self._by_name[data["name"]] = data
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "name" in item:
                                self._by_name[item["name"]] = item
                except Exception:
                    pass

    def add_profiles(self, profiles):
        """Add loaded Profile objects to the index (for cross-referencing)."""
        for profile in profiles:
            if profile.name and profile.name not in self._by_name:
                self._by_name[profile.name] = profile.data

    def resolve(self, profile, max_depth: int = 10):
        """
        Resolve a profile's inheritance chain.
        Sets profile.resolved_data (full merged dict) and
        profile.inherited_keys (set of keys that came from parents).
        """
        merged = {}
        inherited_keys = set()
        chain = []

        # Walk up the inheritance chain
        current_name = profile.inherits
        depth = 0
        while current_name and depth < max_depth:
            parent_data = self._by_name.get(current_name)
            if parent_data is None:
                # Try fuzzy match: strip @suffix
                base = re.sub(r'\s*@.*$', '', current_name)
                parent_data = self._by_name.get(base)
            if parent_data is None:
                break
            chain.append(current_name)
            current_name = parent_data.get("inherits", "")
            depth += 1

        # Merge from deepest ancestor → nearest parent → profile itself
        for ancestor_name in reversed(chain):
            ancestor = self._by_name.get(ancestor_name)
            if ancestor is None:
                base = re.sub(r'\s*@.*$', '', ancestor_name)
                ancestor = self._by_name.get(base, {})
            for k, v in ancestor.items():
                if k not in _IDENTITY_KEYS:
                    merged[k] = v
                    inherited_keys.add(k)

        # Profile's own data overwrites inherited
        for k, v in profile.data.items():
            if k not in _IDENTITY_KEYS:
                merged[k] = v
                inherited_keys.discard(k)  # It's an override, not inherited

        profile.resolved_data = merged
        profile.inherited_keys = inherited_keys
        profile.inheritance_chain = chain

    @property
    def preset_count(self):
        return len(self._by_name)

    def has_preset(self, name: str) -> bool:
        if name in self._by_name:
            return True
        base = re.sub(r'\s*@.*$', '', name)
        return base in self._by_name


# --- Theme ---

class Theme:
    """OrcaSlicer Teal dark theme."""
    def __init__(self, dark=True):
        self.dark = dark
        # Always use teal dark for now
        self.bg = "#1a1a1a"        # Window background
        self.bg2 = "#1e1e1e"       # Panels / sidebar
        self.bg3 = "#252525"       # Input fields / raised surfaces
        self.bg4 = "#333333"       # Buttons default
        self.fg = "#ededed"         # Primary text — light gray
        self.fg2 = "#e0e0e0"       # Secondary text — bright gray (high contrast)
        self.fg3 = "#b0b0b0"       # Muted text — never below this on dark bg
        self.accent = "#00d4a0"    # Teal — primary accent
        self.accent2 = "#00a67d"   # Teal darker — hover/secondary
        self.accent_fg = "#0a2620" # Dark text for use ON accent backgrounds (WCAG AA 4.5:1+)
        self.success = "#00d4a0"   # Same teal for success
        self.converted = "#4fc3f7" # Light blue for converted status
        self.warning = "#ffb74d"   # Orange for warnings
        self.locked = "#ff8a80"    # Soft red for locked status
        self.error = "#e57373"     # Red for errors
        self.border = "#2a2a2a"    # Subtle borders
        self.sel = "#0d3a2e"       # Selected row bg (dark teal)
        self.btn_bg = "#333333"    # Default button
        self.btn_fg = "#ffffff"    # Default button text
        self.section_bg = "#222222"
        self.param_bg = "#242424"   # Slightly lighter than bg2 for param content area
        self.edit_bg = "#2a2a2a"    # Subtle bg for editable value fields
        self.placeholder_fg = "#888888"  # Placeholder text in filter/entry fields
        self.convert_all_bg = "#282828"  # "Convert All" button — darker than btn_bg


# --- Profile Data Model ---

class Profile:
    def __init__(self, data: dict, source_path: str, source_type: str,
                 type_hint: str = None, origin: str = ""):
        self.data = data
        self.source_path = source_path
        self.source_type = source_type
        self.type_hint = type_hint  # From directory structure ("filament", "process", etc.)
        self.origin = origin or self._detect_origin(source_path)
        self.modified = False
        # Populated by PresetIndex.resolve():
        self.resolved_data = None   # Full merged data (parent + overrides)
        self.inherited_keys = set() # Keys that came from parent (not overridden)
        self.inheritance_chain = [] # List of ancestor names

    @staticmethod
    def _detect_origin(path: str) -> str:
        """Guess slicer origin from the file path."""
        p = path.lower()
        if "bambustudio" in p or "bambu" in p:
            return "BambuStudio"
        if "orcaslicer" in p or "orca" in p:
            return "OrcaSlicer"
        if "prusaslicer" in p or "prusa" in p:
            return "PrusaSlicer"
        return ""

    @property
    def name(self):
        n = self.data.get("name", "")
        return n if n else os.path.splitext(os.path.basename(self.source_path))[0]

    @property
    def profile_type(self):
        # 1. Explicit type field
        t = self.data.get("type", "").lower()
        if t in ("filament",):
            return "filament"
        elif t in ("process", "print"):
            return "process"
        elif t in ("machine", "printer"):
            return "printer"

        # 2. Directory-based hint (from slicer import)
        if self.type_hint:
            h = self.type_hint.lower()
            if h in ("filament",):
                return "filament"
            elif h in ("process", "print"):
                return "process"
            elif h in ("machine", "printer"):
                return "printer"

        # 3. Heuristic: guess from keys present
        keys = set(self.data.keys())
        filament_signals = keys & _FILAMENT_SIGNAL_KEYS
        process_signals = keys & _PROCESS_SIGNAL_KEYS

        if len(filament_signals) > len(process_signals):
            return "filament"
        if len(process_signals) > 0:
            return "process"
        return "unknown"

    @property
    def compatible_printers(self):
        cp = self.data.get("compatible_printers", [])
        if isinstance(cp, str):
            # Sometimes stored as JSON string
            try:
                cp = json.loads(cp)
            except Exception:
                cp = [cp] if cp else []
        return cp if isinstance(cp, list) else []

    @property
    def inherits(self):
        return self.data.get("inherits", "")

    @property
    def is_locked(self):
        if len(self.compatible_printers) > 0:
            return True
        # Also locked if printer_settings_id is set
        psid = self.data.get("printer_settings_id", "")
        if isinstance(psid, list):
            psid = psid[0] if psid else ""
        return bool(psid)

    @property
    def source_label(self):
        f = os.path.basename(self.source_path)
        if self.source_type == "3mf":
            return f"Extracted from {f}"
        return f

    @property
    def printer_group(self):
        """Extract a human-readable printer name for grouping.
        Uses compatible_printers first, then printer_settings_id,
        then the @... suffix in the profile name."""
        # 1. compatible_printers list
        cp = self.compatible_printers
        if cp:
            # Strip nozzle suffixes for cleaner grouping
            # "Bambu Lab X1 Carbon 0.4 nozzle" → "Bambu Lab X1 Carbon"
            names = set()
            for p in cp:
                clean = re.sub(r'\s+\d+\.\d+\s*nozzle$', '', p, flags=re.IGNORECASE).strip()
                names.add(clean)
            return ", ".join(sorted(names)) if names else "Universal"

        # 2. printer_settings_id
        psid = self.data.get("printer_settings_id", "")
        if isinstance(psid, list):
            psid = psid[0] if psid else ""
        if psid:
            return psid

        # 3. Name suffix after @ (e.g., "0.20mm Standard @BBL X1C" → "BBL X1C")
        name = self.data.get("name", "")
        if "@" in name:
            return name.split("@", 1)[1].strip()

        return "Universal"

    @property
    def manufacturer_group(self):
        """Extract manufacturer/vendor for grouping filament profiles.
        Uses filament_vendor field, then infers from profile name or inherits."""
        # 1. Explicit vendor field
        vendor = self.data.get("filament_vendor", "")
        if isinstance(vendor, list):
            vendor = vendor[0] if vendor else ""
        if vendor:
            return vendor

        # 2. Infer from profile name — common patterns:
        #    "Bambu PLA Basic @X1C" → "Bambu"
        #    "Extrudr DuraPro ASA" → "Extrudr"
        #    "Generic PETG" → "Generic"
        #    "PolyTerra PLA" → "PolyTerra"
        name = self.data.get("name", "")
        # Strip the @printer suffix first
        base = name.split("@")[0].strip() if "@" in name else name

        # Known vendor prefixes (check longest first)
        base_lower = base.lower()
        for v in sorted(_KNOWN_VENDORS, key=len, reverse=True):
            if base_lower.startswith(v.lower()):
                return v

        # 3. Infer from inherits field
        inherits = self.data.get("inherits", "")
        if inherits:
            for v in sorted(_KNOWN_VENDORS, key=len, reverse=True):
                if inherits.lower().startswith(v.lower()):
                    return v

        # 4. Use first word of profile name as inferred vendor
        if base.strip():
            first_word = base.split()[0]
            # Only use if it looks like a brand (starts uppercase, not a filament type)
            if first_word.upper() not in _FILAMENT_TYPES and len(first_word) > 1:
                return first_word
        return "Other"

    def group_key(self, group_by):
        """Return the grouping key for a given group_by mode."""
        if group_by == "printer":
            return self.printer_group
        elif group_by == "manufacturer":
            return self.manufacturer_group
        elif group_by == "status":
            if self.modified:
                return "Converted"
            elif self.is_locked:
                return "Locked"
            else:
                return "Universal"
        return ""  # "none" — no grouping

    def make_universal(self):
        self.data["compatible_printers"] = []
        if "compatible_printers_condition" in self.data:
            self.data["compatible_printers_condition"] = ""
        self.modified = True

    def retarget(self, printers: list):
        self.data["compatible_printers"] = printers
        if "compatible_printers_condition" in self.data:
            self.data["compatible_printers_condition"] = ""
        self.modified = True

    def to_json(self, indent=4, flatten=True):
        """Export to JSON. If flatten=True and resolved_data exists,
        exports the full flattened profile (no inheritance dependency)."""
        if flatten and self.resolved_data:
            # Build a self-contained export: identity fields from original +
            # all resolved parameters
            export = {}
            for k in ("name", "type", "setting_id", "from", "version"):
                if k in self.data:
                    export[k] = self.data[k]
            # Deliberately omit 'inherits' since we're flattening
            # Keep compatible_printers as modified
            if "compatible_printers" in self.data:
                export["compatible_printers"] = self.data["compatible_printers"]
            if "compatible_printers_condition" in self.data:
                export["compatible_printers_condition"] = self.data["compatible_printers_condition"]
            # Merge all resolved params
            export.update(self.resolved_data)
            return json.dumps(export, indent=indent, ensure_ascii=False)
        return json.dumps(self.data, indent=indent, ensure_ascii=False)

    def suggested_filename(self):
        name = re.sub(r'\s*@\s*\S+.*$', '', self.name)
        name = re.sub(r'[^\w\s\-.]', '', name)
        name = re.sub(r'\s+', '_', name.strip())
        return f"{name or 'profile'}.json"


# --- Profile Engine ---

class ProfileEngine:

    @staticmethod
    def load_json(path: str, type_hint: str = None) -> list:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return [Profile(data, path, "json", type_hint)]
        elif isinstance(data, list):
            return [Profile(d, path, "json", type_hint) for d in data if isinstance(d, dict)]
        return []

    @staticmethod
    def extract_from_3mf(path: str) -> list:
        profiles = []
        errors = []
        if not zipfile.is_zipfile(path):
            raise ValueError(f"{os.path.basename(path)} is not a valid .3mf")

        with zipfile.ZipFile(path, "r") as zf:
            for name in zf.namelist():
                # JSON profiles embedded directly
                if name.endswith(".json"):
                    try:
                        data = json.loads(zf.read(name).decode("utf-8"))
                        if isinstance(data, dict) and ("name" in data or "type" in data
                                                        or "filament_type" in data or "layer_height" in data):
                            profiles.append(Profile(data, path, "3mf"))
                    except Exception as e:
                        errors.append(f"{name}: {e}")

                # XML/config files in Metadata/ — try all text files
                if name.startswith("Metadata/") and any(
                        name.endswith(ext) for ext in (".config", ".xml", ".ini")):
                    try:
                        content = zf.read(name).decode("utf-8")
                        profiles.extend(ProfileEngine._parse_config(content, path))
                    except Exception as e:
                        errors.append(f"{name}: {e}")

                # Some slicers store settings in .gcode or text metadata
                if name.startswith("Metadata/") and name.endswith(".txt"):
                    try:
                        content = zf.read(name).decode("utf-8")
                        # Only try if it looks like it has profile keys
                        if any(k in content for k in ("filament_type", "layer_height",
                                                       "nozzle_temperature", "compatible_printers")):
                            profiles.extend(ProfileEngine._parse_config(content, path))
                    except Exception as e:
                        errors.append(f"{name}: {e}")

        if errors:
            print(f"[3MF extraction warnings] {'; '.join(errors)}")

        # Deduplicate by name
        seen = set()
        unique = []
        for profile in profiles:
            if profile.name not in seen:
                seen.add(profile.name)
                unique.append(profile)
        return unique

    @staticmethod
    def _parse_config(content: str, source_path: str) -> list:
        """Parse config content from .3mf metadata files.
        Handles multiple formats: JSON (BambuStudio .config), XML with
        <metadata> children, XML with direct attributes, and INI-style
        key=value sections.
        """
        profiles = []

        # BambuStudio stores .config files as JSON — detect and handle first
        stripped = content.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                data = json.loads(content)
                items = [data] if isinstance(data, dict) else (
                    [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
                )
                for item in items:
                    if ProfileEngine._is_profile_data(item):
                        # Infer type from keys/fields if not set
                        if "type" not in item:
                            # Use name hint: filament_settings_* → filament,
                            # project_settings / process_settings → process
                            item_name = item.get("name", "")
                            if "filament_settings" in item_name.lower():
                                item["type"] = "filament"
                            elif "project_settings" in item_name.lower():
                                item["type"] = "process"
                            elif len(item.keys() & _FILAMENT_SIGNAL_KEYS) > len(item.keys() & _PROCESS_SIGNAL_KEYS):
                                item["type"] = "filament"
                            else:
                                item["type"] = "process"
                        # Derive a descriptive name
                        raw_name = item.get("name", "")
                        basename = os.path.splitext(os.path.basename(source_path))[0]
                        # "project_settings" is generic — replace with source filename
                        if not raw_name or raw_name in ("project_settings", ""):
                            if item.get("type") == "process":
                                item["name"] = f"Project Settings ({basename})"
                            else:
                                sid = item.get("filament_settings_id") or item.get("setting_id")
                                if isinstance(sid, list):
                                    sid = sid[0] if sid else None
                                if sid and sid != "nil":
                                    item["name"] = sid
                                else:
                                    item["name"] = f"Extracted profile ({basename})"
                        profiles.append(Profile(item, source_path, "3mf"))
                return profiles
            except (json.JSONDecodeError, ValueError):
                pass  # Not valid JSON — fall through to XML/INI parsers

        try:
            root = ET.fromstring(content)
            # Walk ALL elements — real .3mf files may nest profiles in
            # <plate>, <config>, or other containers.
            # We look for: <filament>, <print>, <process> tags with metadata children
            # Also handle <plate> containers that CONTAIN filament/print children
            for elem in root.iter():
                tag_lower = elem.tag.lower().split("}")[-1]  # strip namespace

                # Direct profile elements
                if tag_lower in ("filament", "print", "process"):
                    data = ProfileEngine._extract_xml_profile(elem)
                    if data and ProfileEngine._is_profile_data(data):
                        if "type" not in data:
                            data["type"] = "filament" if (
                                "filament_type" in data or tag_lower == "filament"
                            ) else "process"
                        if "name" not in data:
                            ft = data.get("filament_type", "Unknown")
                            if isinstance(ft, list):
                                ft = ft[0] if ft else "Unknown"
                            data["name"] = f"Extracted {ft} profile"
                        profiles.append(Profile(data, source_path, "3mf"))

                # <plate> containers: skip the plate itself, children handled above
                # But also check for flat key-value configs inside plate
                elif tag_lower == "plate":
                    # Don't create a profile from the plate metadata itself
                    pass

                # Handle <object> or other containers with setting child elements
                elif tag_lower in ("settings", "object_settings"):
                    data = ProfileEngine._extract_xml_profile(elem)
                    if data and ProfileEngine._is_profile_data(data):
                        profiles.append(Profile(data, source_path, "3mf"))

        except ET.ParseError:
            # Fallback: parse INI-style [section:name] format
            current = {}
            current_name = None
            for line in content.splitlines():
                line = line.strip()
                m = re.match(r'^\[(\w+)(?::(.+))?\]$', line)
                if m:
                    if current and current_name and ProfileEngine._is_profile_data(current):
                        current["name"] = current_name
                        profiles.append(Profile(current, source_path, "3mf"))
                    current = {"type": m.group(1)}
                    current_name = m.group(2) or m.group(1)
                    continue
                kv = re.match(r'^(\S+)\s*=\s*(.+)$', line)
                if kv:
                    current[kv.group(1)] = ProfileEngine._pv(kv.group(2).strip())
            if current and current_name and ProfileEngine._is_profile_data(current):
                current["name"] = current_name
                profiles.append(Profile(current, source_path, "3mf"))

        # If no structured profiles found, try a flat key-value parse of entire content
        if not profiles and "=" in content and not content.strip().startswith("<"):
            data = {}
            for line in content.splitlines():
                line = line.strip()
                kv = re.match(r'^(\S+)\s*=\s*(.+)$', line)
                if kv:
                    data[kv.group(1)] = ProfileEngine._pv(kv.group(2).strip())
            if data and ProfileEngine._is_profile_data(data):
                if "name" not in data:
                    data["name"] = f"Extracted profile from {os.path.basename(source_path)}"
                profiles.append(Profile(data, source_path, "3mf"))

        return profiles

    @staticmethod
    def _extract_xml_profile(elem) -> dict:
        """Extract key-value pairs from an XML element.
        Handles both <metadata key='' value=''/> children and direct attributes."""
        data = {}
        for child in elem:
            tag = child.tag.lower().split("}")[-1]  # strip namespace
            if tag == "metadata":
                k = child.get("key", "")
                v = child.get("value", child.text or "")
                if k:
                    data[k] = ProfileEngine._pv(v)
            elif tag == "setting":
                # <setting key="..." value="..."/> or <setting key="...">value</setting>
                k = child.get("key", child.get("id", ""))
                v = child.get("value", child.text or "")
                if k:
                    data[k] = ProfileEngine._pv(v)
        # Also check direct attributes on the element itself
        for k, v in elem.attrib.items():
            if k in ("id", "idx"):
                continue  # skip index attributes
            if k not in data:
                data[k] = ProfileEngine._pv(v)
        return data

    @staticmethod
    def _is_profile_data(data: dict) -> bool:
        """Check if a dict looks like actual profile data (not just plate metadata)."""
        return bool(data.keys() & _PROFILE_SIGNAL_KEYS)

    @staticmethod
    def _pv(s):
        """Parse a config value string to its Python type.
        Only coerces strings that are entirely numeric — preserves hex colors,
        G-code snippets, version strings, and other non-numeric data."""
        # Coercion order: bool → numeric (if purely numeric) → JSON collection → str.
        # Called only for INI-style config values, not for JSON-parsed data.
        if not isinstance(s, str):
            return s
        sl = s.lower()
        if sl in ("true", "false"):
            return sl == "true"
        # Only attempt numeric coercion if the string looks purely numeric.
        # A string with spaces, '#', or multiple dots is not a plain number.
        if " " not in s and not s.startswith("#"):
            try:
                return float(s) if "." in s else int(s)
            except ValueError:
                pass
        if s.startswith(("[", "{")):
            try:
                return json.loads(s)
            except Exception:
                pass
        return s

    @staticmethod
    def load_file(path: str, type_hint: str = None) -> list:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".json":
            return ProfileEngine.load_json(path, type_hint)
        elif ext == ".3mf":
            return ProfileEngine.extract_from_3mf(path)
        raise ValueError(f"Unsupported: {ext}")


# --- Slicer Detection ---

class SlicerDetector:
    PATHS = {
        "BambuStudio": {"Darwin": "~/Library/Application Support/BambuStudio",
                        "Windows": "%APPDATA%/BambuStudio",
                        "Linux": "~/.config/BambuStudio"},
        "OrcaSlicer":  {"Darwin": "~/Library/Application Support/OrcaSlicer",
                        "Windows": "%APPDATA%/OrcaSlicer",
                        "Linux": "~/.config/OrcaSlicer"},
        "PrusaSlicer": {"Darwin": "~/Library/Application Support/PrusaSlicer",
                        "Windows": "%APPDATA%/PrusaSlicer",
                        "Linux": "~/.config/PrusaSlicer"},
    }

    @staticmethod
    def find_all():
        found = {}
        system = platform.system()
        for slicer, paths in SlicerDetector.PATHS.items():
            t = paths.get(system, "")
            if not t:
                continue
            p = os.path.expandvars(os.path.expanduser(t))
            if os.path.isdir(p):
                found[slicer] = p
        return found

    @staticmethod
    def find_user_presets(slicer_path):
        """Returns dict of {profile_type: [file_paths]} with type info preserved."""
        presets = {"filament": [], "process": [], "machine": []}
        user_dir = os.path.join(slicer_path, "user")
        if not os.path.isdir(user_dir):
            return presets
        for uid in os.listdir(user_dir):
            up = os.path.join(user_dir, uid)
            if not os.path.isdir(up):
                continue
            for pt in presets:
                td = os.path.join(up, pt)
                if os.path.isdir(td):
                    presets[pt].extend(
                        os.path.join(td, f) for f in os.listdir(td) if f.endswith(".json")
                    )
        return presets

    @staticmethod
    def get_export_dir(slicer_path):
        user_dir = os.path.join(slicer_path, "user")
        if os.path.isdir(user_dir):
            for e in os.listdir(user_dir):
                entry_path = os.path.join(user_dir, e)
                if os.path.isdir(entry_path):
                    return entry_path
        return slicer_path


# --- Tooltip Helper ---

class _Tooltip:
    """Lightweight hover tooltip for any widget."""
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._tip = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        widget.bind("<Button>", self._cancel, add="+")

    def _schedule(self, event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self, event=None):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self._tip:
            self._tip.destroy()
            self._tip = None

    def _show(self):
        if not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tooltip_window = tk.Toplevel(self.widget)
        tooltip_window.wm_overrideredirect(True)
        tooltip_window.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(tooltip_window, text=self.text, bg="#333333", fg="#ededed",
                       font=(UI_FONT, 11), padx=8, pady=4, relief="solid", bd=1,
                       borderwidth=1, highlightbackground=_TOOLTIP_BORDER_COLOR)
        lbl.pack()

    def update_text(self, text):
        self.text = text


def _bind_scroll(widget, canvas):
    """Bind mousewheel/scroll-button events on widget to scroll the given canvas."""
    is_mac = platform.system() == "Darwin"
    def _on_wheel(e):
        if is_mac:
            canvas.yview_scroll(int(-1 * e.delta), "units")
        else:
            units = round(-1 * e.delta / 120)
            if units == 0:
                units = -1 if e.delta > 0 else 1
            canvas.yview_scroll(units, "units")
    widget.bind("<MouseWheel>", _on_wheel)
    widget.bind("<Button-4>", lambda e: canvas.yview_scroll(-3, "units"))
    widget.bind("<Button-5>", lambda e: canvas.yview_scroll(3, "units"))


def _make_btn(parent, text, command, bg, fg, font=(UI_FONT, 11), padx=10, pady=4, **kw):
    """Create a Label-based button. macOS ignores bg/fg on tk.Button;
    Labels respect them and we bind click events manually.
    No hover effects — colors stay constant."""
    state = {"bg": bg}

    wrapper = tk.Frame(parent, bg=bg, highlightthickness=0)
    lbl = tk.Label(wrapper, text=text, bg=bg, fg=fg, font=font,
                   padx=padx, pady=pady, cursor="hand2",
                   highlightthickness=0)
    lbl.pack(side="top")
    lbl.bind("<Button-1>", lambda e: command())

    wrapper._inner_label = lbl
    # Proxy configure to inner label for tab switching
    _orig_configure = wrapper.configure

    def _proxy_configure(**kwargs):
        label_keys = {"fg", "bg", "font", "text"}
        lbl_kw = {k: v for k, v in kwargs.items() if k in label_keys}
        wrap_kw = {k: v for k, v in kwargs.items() if k not in label_keys}
        if "bg" in kwargs:
            wrap_kw["bg"] = kwargs["bg"]
            state["bg"] = kwargs["bg"]
        if lbl_kw:
            lbl.configure(**lbl_kw)
        if wrap_kw:
            _orig_configure(**wrap_kw)

    wrapper.configure = _proxy_configure
    wrapper.config = _proxy_configure
    return wrapper


class ExportDialog(tk.Toplevel):
    """Dialog shown before export. Offers file export and slicer quick-install."""

    def __init__(self, parent, theme, count=1, detected_slicers=None):
        super().__init__(parent)
        self.theme = theme
        self.result = None        # "file" for save-to-file, or None for cancel
        self.flatten = False
        self.slicer_target = None  # (name, path) if installing to slicer
        self._detected_slicers = detected_slicers or {}
        self.title("Export Profiles")
        self.configure(bg=theme.bg)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 80, parent.winfo_rooty() + 80))
        self._build(count)
        self.wait_window()

    def _build(self, count):
        theme = self.theme
        tk.Label(self, text=f"Export {count} profile{'s' if count != 1 else ''}",
                 font=(UI_FONT, 14, "bold"), bg=theme.bg, fg=theme.fg).pack(pady=(16, 8), padx=20)

        # Options frame
        opts = tk.Frame(self, bg=theme.bg)
        opts.pack(fill="x", padx=20, pady=8)

        self._flatten_var = tk.BooleanVar(value=False)
        checkbox = tk.Checkbutton(opts, text="Flatten inherited parameters (no inheritance)",
                            variable=self._flatten_var, bg=theme.bg, fg=theme.fg,
                            selectcolor=theme.bg, activebackground=theme.bg, activeforeground=theme.fg,
                            indicatoron=True, offrelief="flat",
                            font=(UI_FONT, 11))
        checkbox.pack(anchor="w", padx=8, pady=4)
        tk.Label(opts, text="When checked, all inherited values are written\n"
                            "explicitly into the exported file. The profile\n"
                            "becomes fully self-contained with no dependencies.",
                 bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 10), justify="left").pack(anchor="w", padx=28)

        # ── Quick-install slicer destinations ──
        if self._detected_slicers:
            sep = tk.Frame(self, bg=theme.border, height=1)
            sep.pack(fill="x", padx=20, pady=(12, 0))

            tk.Label(self, text="Or install directly to a slicer's user preset folder:",
                     font=(UI_FONT, 12), bg=theme.bg, fg=theme.fg2).pack(
                         anchor="w", padx=20, pady=(10, 6))

            slicer_row = tk.Frame(self, bg=theme.bg)
            slicer_row.pack(fill="x", padx=20, pady=(0, 4))
            for name, path in self._detected_slicers.items():
                dest_dir = SlicerDetector.get_export_dir(path)
                _make_btn(slicer_row, f"Install to {name}",
                          lambda n=name, p=path: self._install_to_slicer(n, p),
                          bg=theme.bg4, fg=theme.fg,
                          font=(UI_FONT, 11), padx=12, pady=5).pack(
                              side="left", padx=(0, 6))
            # Show the destination path for context
            if len(self._detected_slicers) == 1:
                name, path = list(self._detected_slicers.items())[0]
                dest = SlicerDetector.get_export_dir(path)
                tk.Label(self, text=dest, bg=theme.bg, fg=theme.fg3,
                         font=(UI_FONT, 9)).pack(anchor="w", padx=28, pady=(0, 4))

            sep2 = tk.Frame(self, bg=theme.border, height=1)
            sep2.pack(fill="x", padx=20, pady=(8, 0))

        # Buttons
        button_frame = tk.Frame(self, bg=theme.bg)
        button_frame.pack(fill="x", padx=20, pady=(12, 16))

        _make_btn(button_frame, "Export to File...",
                  self._ok,
                  bg=theme.accent2, fg=theme.accent_fg,
                  font=(UI_FONT, 11, "bold"), padx=16, pady=5).pack(side="right", padx=(4, 0))
        _make_btn(button_frame, "Cancel",
                  self._cancel,
                  bg=theme.bg3, fg=theme.fg3,
                  font=(UI_FONT, 11), padx=12, pady=5).pack(side="right")

    def _ok(self):
        self.result = "file"
        self.flatten = self._flatten_var.get()
        self.destroy()

    def _install_to_slicer(self, name, path):
        self.result = "slicer"
        self.flatten = self._flatten_var.get()
        self.slicer_target = (name, path)
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class ConvertDialog(tk.Toplevel):
    def __init__(self, parent, theme, count=1):
        super().__init__(parent)
        self.theme = theme
        self.result = None
        self.title("Convert Profiles")
        self.configure(bg=theme.bg)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        self._build(count)
        self.wait_window()

    def _build(self, count):
        theme = self.theme
        tk.Label(self, text=f"Convert {count} profile{'s' if count != 1 else ''}",
                 font=(UI_FONT, 14, "bold"), bg=theme.bg, fg=theme.fg).pack(pady=(16, 8), padx=16)

        self.mode = tk.StringVar(value="universal")
        mode_frame = tk.Frame(self, bg=theme.bg)
        mode_frame.pack(fill="x", padx=16, pady=8)

        tk.Radiobutton(mode_frame, text="Make universal (compatible with all printers)",
                       variable=self.mode, value="universal", bg=theme.bg, fg=theme.fg,
                       selectcolor=theme.bg3, activebackground=theme.bg, activeforeground=theme.fg,
                       command=self._mode_changed).pack(anchor="w", padx=12, pady=6)
        tk.Radiobutton(mode_frame, text="Assign to specific printers:",
                       variable=self.mode, value="retarget", bg=theme.bg, fg=theme.fg,
                       selectcolor=theme.bg3, activebackground=theme.bg, activeforeground=theme.fg,
                       command=self._mode_changed).pack(anchor="w", padx=12, pady=6)

        # Printer checklist
        self.pf = tk.Frame(self, bg=theme.bg)
        self.pf.pack(fill="both", expand=True, padx=32, pady=(0, 8))

        list_frame = tk.Frame(self.pf, bg=theme.bg3, highlightbackground=theme.border, highlightthickness=1)
        list_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(list_frame, bg=theme.bg3, highlightthickness=0, width=380, height=200)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.cf = tk.Frame(canvas, bg=theme.bg3)
        self.cf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.cf, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.pvars = {}
        for brand, models in KNOWN_PRINTERS.items():
            tk.Label(self.cf, text=brand, font=(UI_FONT, 10, "bold"),
                     bg=theme.bg3, fg=theme.fg2).pack(anchor="w", padx=8, pady=(8, 2))
            for model in models:
                for nz in NOZZLE_SIZES:
                    ps = f"{model} {nz} nozzle"
                    v = tk.BooleanVar(value=False)
                    self.pvars[ps] = v
                    tk.Checkbutton(self.cf, text=ps, variable=v, bg=theme.bg3, fg=theme.fg,
                                   selectcolor=theme.bg4, activebackground=theme.bg3,
                                   activeforeground=theme.fg).pack(anchor="w", padx=24)

        tk.Label(self.pf, text="Add unlisted printer (comma-separated):",
                 bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 10)).pack(anchor="w", pady=(8, 2))
        self.custom = tk.Entry(self.pf, bg=theme.bg3, fg=theme.fg, insertbackground=theme.fg,
                               highlightbackground=theme.border, highlightthickness=1, font=(UI_FONT, 11))
        self.custom.pack(fill="x", pady=(0, 8))
        self._set_state("disabled")

        button_frame = tk.Frame(self, bg=theme.bg)
        button_frame.pack(fill="x", padx=16, pady=(8, 16))
        cancel_btn = _make_btn(button_frame, "Cancel", self._cancel, bg=theme.btn_bg, fg=theme.btn_fg,
                               padx=20, pady=6)
        cancel_btn.pack(side="right", padx=(8, 0))
        convert_btn = _make_btn(button_frame, "Convert", self._convert, bg=theme.accent, fg=theme.accent_fg,
                                font=(UI_FONT, 11, "bold"), padx=20, pady=6)
        convert_btn.pack(side="right")

    def _mode_changed(self):
        self._set_state("normal" if self.mode.get() == "retarget" else "disabled")

    def _set_state(self, state):
        for w in self.cf.winfo_children():
            if isinstance(w, tk.Checkbutton):
                w.configure(state=state)
        self.custom.configure(state=state)

    def _cancel(self):
        self.result = None
        self.destroy()

    def _convert(self):
        if self.mode.get() == "universal":
            self.result = "universal"
        else:
            sel = [n for n, v in self.pvars.items() if v.get()]
            c = self.custom.get().strip()
            if c:
                sel.extend(p.strip() for p in c.split(",") if p.strip())
            if not sel:
                messagebox.showwarning("No Printers", "Select at least one printer.", parent=self)
                return
            self.result = sel
        self.destroy()


# --- Compare Dialog ---

class CompareDialog(tk.Toplevel):
    """Side-by-side comparison of two profiles, grouped by section."""

    def __init__(self, parent, theme, profile_a, profile_b):
        super().__init__(parent)
        self.theme = theme
        self.title("Compare Profiles")
        self.configure(bg=theme.bg)
        self.geometry(f"{_DLG_COMPARE_WIDTH}x{_DLG_COMPARE_HEIGHT}")
        self.minsize(_DLG_COMPARE_MIN_WIDTH, _DLG_COMPARE_MIN_HEIGHT)
        self.transient(parent)
        self._build(profile_a, profile_b)

    def _build(self, profile_a, profile_b):
        theme = self.theme

        # ── Header: two profile name columns ──
        header_frame = tk.Frame(self, bg=theme.bg)
        header_frame.pack(fill="x", padx=16, pady=(10, 4))
        # Left name
        tk.Label(header_frame, text=profile_a.name, bg=theme.bg, fg=theme.accent,
                 font=(UI_FONT, 13, "bold")).pack(side="left")
        # Centered "vs"
        tk.Label(header_frame, text="  vs  ", bg=theme.bg, fg=theme.fg2,
                 font=(UI_FONT, 12)).pack(side="left")
        # Right name
        tk.Label(header_frame, text=profile_b.name, bg=theme.bg, fg=theme.warning,
                 font=(UI_FONT, 13, "bold")).pack(side="left")

        # ── Find differences and group by section ──
        all_keys = set(profile_a.data.keys()) | set(profile_b.data.keys())
        all_keys -= _IDENTITY_KEYS
        diffs = {}
        for k in all_keys:
            value_a = profile_a.data.get(k)
            value_b = profile_b.data.get(k)
            if value_a != value_b:
                diffs[k] = (value_a, value_b)

        # Build section lookup from layout
        layout = FILAMENT_LAYOUT if profile_a.profile_type == "filament" else PROCESS_LAYOUT
        key_to_label = {}
        key_to_group = {}  # key -> "Tab > Section"
        for tab_name, sections in layout.items():
            for sec_name, params in sections.items():
                for json_key, ui_label in params:
                    key_to_label[json_key] = ui_label
                    key_to_group[json_key] = f"{tab_name} \u203a {sec_name}"

        # Group diffs by section
        grouped = {}
        for key in sorted(diffs.keys(), key=lambda k: (key_to_group.get(k, "zzz"), k)):
            group = key_to_group.get(key, "Other")
            if group not in grouped:
                grouped[group] = []
            grouped[group].append(key)

        diff_count = len(diffs)
        tk.Label(self, text=f"{diff_count} parameter{'s' if diff_count != 1 else ''} differ",
                 bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 11)).pack(anchor="w", padx=16, pady=(0, 6))

        # ── Column headers (fixed above scroll) ──
        col_hdr = tk.Frame(self, bg=theme.bg4)
        col_hdr.pack(fill="x", padx=16)
        tk.Label(col_hdr, text="Parameter", bg=theme.bg4, fg=theme.fg,
                 font=(UI_FONT, 11, "bold"), anchor="w",
                 padx=8, pady=4).pack(side="left", fill="x", expand=True)
        tk.Label(col_hdr, text="Left", bg=theme.bg4, fg=theme.accent,
                 font=(UI_FONT, 11, "bold"), width=18, anchor="w",
                 padx=4, pady=4).pack(side="left")
        tk.Label(col_hdr, text="Right", bg=theme.bg4, fg=theme.warning,
                 font=(UI_FONT, 11, "bold"), width=18, anchor="w",
                 padx=4, pady=4).pack(side="left")
        tk.Label(col_hdr, text="Change", bg=theme.bg4, fg=theme.fg2,
                 font=(UI_FONT, 11, "bold"), width=8, anchor="w",
                 padx=4, pady=4).pack(side="left")

        # ── Scrollable content ──
        container = tk.Frame(self, bg=theme.bg)
        container.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        canvas = tk.Canvas(container, bg=theme.bg2, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, bg=theme.bg2)
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window_id = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window_id, width=e.width))

        # Scroll helper — bind to widget and all children
        def _bind_scroll_recursive(widget):
            _bind_scroll(widget, canvas)
            for child in widget.winfo_children():
                _bind_scroll_recursive(child)

        # ── Render grouped sections ──
        row_idx = 0
        for group_name, keys in grouped.items():
            # Section header
            sec_hdr = tk.Frame(body, bg=theme.bg2)
            sec_hdr.pack(fill="x", pady=(8, 2))
            bar = tk.Frame(sec_hdr, bg=theme.accent, width=3)
            bar.pack(side="left", fill="y", padx=(0, 8))
            tk.Label(sec_hdr, text=group_name, bg=theme.bg2, fg=theme.fg,
                     font=(UI_FONT, 12, "bold"), padx=4).pack(side="left")

            for key in keys:
                value_a, value_b = diffs[key]
                bg = theme.bg2 if row_idx % 2 == 0 else theme.bg3
                row = tk.Frame(body, bg=bg)
                row.pack(fill="x")

                label = key_to_label.get(key, key)
                va_str = self._fmt(value_a, key=key)
                vb_str = self._fmt(value_b, key=key)
                delta = self._delta(value_a, value_b)

                tk.Label(row, text=label, bg=bg, fg=theme.fg, font=(UI_FONT, 12),
                         anchor="w", padx=10, pady=3).pack(side="left", fill="x", expand=True)
                # Left value
                va_fg = theme.accent if value_a is not None else theme.fg3
                tk.Label(row, text=va_str, bg=bg, fg=va_fg, font=(UI_FONT, 12),
                         width=18, anchor="w", padx=4).pack(side="left")
                # Right value
                vb_fg = theme.warning if value_b is not None else theme.fg3
                tk.Label(row, text=vb_str, bg=bg, fg=vb_fg, font=(UI_FONT, 12),
                         width=18, anchor="w", padx=4).pack(side="left")
                # Delta
                delta_fg = theme.converted if delta != "\u2014" else theme.fg3
                tk.Label(row, text=delta, bg=bg, fg=delta_fg, font=(UI_FONT, 11),
                         width=8, anchor="w", padx=4).pack(side="left")
                row_idx += 1

        if not diffs:
            tk.Label(body, text="These profiles are identical.",
                     bg=theme.bg2, fg=theme.fg2, font=(UI_FONT, 13), pady=30).pack()

        _bind_scroll_recursive(body)

    def _fmt(self, v, key=None):
        if v is None:
            return "(not set)"
        if isinstance(v, list):
            unique = list(dict.fromkeys(str(x) for x in v))
            if len(unique) == 1:
                raw = unique[0]
                if key and key in ENUM_VALUES:
                    return _get_enum_human_label(key, raw)
                return raw
            return ", ".join(str(x) for x in v)
        if isinstance(v, bool):
            return "Yes" if v else "No"
        s = str(v)
        if key and key in ENUM_VALUES:
            return _get_enum_human_label(key, s)
        return s[:_VALUE_TRUNCATE_SHORT] + "..." if len(s) > _VALUE_TRUNCATE_SHORT else s

    def _delta(self, a, b):
        """Compute a human-readable delta between two values."""
        try:
            float_a = float(a[0] if isinstance(a, list) else a)
            float_b = float(b[0] if isinstance(b, list) else b)
            if float_a == 0:
                return f"+{float_b}" if float_b != 0 else "—"
            pct = ((float_b - float_a) / abs(float_a)) * 100
            sign = "+" if pct > 0 else ""
            return f"{sign}{pct:.0f}%"
        except (TypeError, ValueError, IndexError):
            return "—"


# --- Detail Panel — BambuStudio-style tabbed viewer ---

class ProfileDetailPanel(tk.Frame):
    """Renders a profile's settings using BambuStudio's exact tab/section layout."""

    def __init__(self, parent, theme):
        super().__init__(parent, bg=theme.bg2)
        self.theme = theme
        self.current_profile = None
        self._tab_buttons = []
        self._current_tab = None
        self._edit_vars = {}  # key -> (StringVar, original_value)
        self._undo_stack = []  # list of (key, old_value) for undo
        self._pre_edit_modified = None  # snapshot of profile.modified before first edit
        self._param_order = []  # ordered list of (key, container, fg_color) for Tab nav
        self._header_frame = None
        self._show_placeholder()

        # Bind Cmd+Z / Ctrl+Z for undo
        mod_key = "Command" if platform.system() == "Darwin" else "Control"
        parent.winfo_toplevel().bind(f"<{mod_key}-z>", self._on_undo)

    def _show_placeholder(self, text=None):
        for w in self.winfo_children():
            w.destroy()
        theme = self.theme
        if text:
            tk.Label(self, text=text, bg=theme.bg2, fg=theme.fg2, font=(UI_FONT, 13)).pack(pady=40)
        else:
            # Empty state with centered message and actions
            container = tk.Frame(self, bg=theme.bg2)
            container.place(relx=0.5, rely=0.4, anchor="center")
            tk.Label(container, text="\u2699", bg=theme.bg2, fg=theme.fg3,
                     font=(UI_FONT, 28)).pack()
            tk.Label(container, text="No profile selected", bg=theme.bg2, fg=theme.fg2,
                     font=(UI_FONT, 14)).pack(pady=(4, 8))
            actions = tk.Frame(container, bg=theme.bg2)
            actions.pack()
            imp_lbl = tk.Label(actions, text="Import files", bg=theme.bg2, fg=theme.accent,
                               font=(UI_FONT, 13, "bold"), cursor="hand2")
            imp_lbl.pack(side="left", padx=(0, 6))
            imp_lbl.bind("<Enter>", lambda e: imp_lbl.configure(fg=theme.accent2))
            imp_lbl.bind("<Leave>", lambda e: imp_lbl.configure(fg=theme.accent))
            tk.Label(actions, text="or", bg=theme.bg2, fg=theme.fg2,
                     font=(UI_FONT, 13)).pack(side="left", padx=(0, 6))
            lp_lbl = tk.Label(actions, text="Load System Presets", bg=theme.bg2, fg=theme.accent,
                              font=(UI_FONT, 13, "bold"), cursor="hand2")
            lp_lbl.pack(side="left")
            lp_lbl.bind("<Enter>", lambda e: lp_lbl.configure(fg=theme.accent2))
            lp_lbl.bind("<Leave>", lambda e: lp_lbl.configure(fg=theme.accent))
            # Bind clicks — find the App instance
            def _find_app(widget):
                w = widget
                while w:
                    if isinstance(w, App):
                        return w
                    w = w.master
                return None
            imp_lbl.bind("<Button-1>", lambda e: (_find_app(self) or e) and _find_app(self)._on_import())
            lp_lbl.bind("<Button-1>", lambda e: (_find_app(self) or e) and _find_app(self)._on_load_presets())

    def _on_undo(self, event=None):
        """Undo the last parameter edit."""
        if not self._undo_stack or not self.current_profile:
            return "break"
        key, old_value = self._undo_stack.pop()
        self.current_profile.data[key] = old_value
        if not self._undo_stack and self._pre_edit_modified is not None:
            self.current_profile.modified = self._pre_edit_modified
            self._pre_edit_modified = None
        # Re-render the current tab to show reverted value
        if self._current_tab:
            self._switch_tab(self._current_tab)
        return "break"

    def show_profile(self, profile):
        self._commit_edits()  # Save any pending edits from previous profile
        self.current_profile = profile
        self._edit_vars = {}
        self._undo_stack = []  # Reset undo stack for new profile
        self._pre_edit_modified = None
        self._param_order = []
        for w in self.winfo_children():
            w.destroy()

        theme = self.theme
        layout = FILAMENT_LAYOUT if profile.profile_type == "filament" else PROCESS_LAYOUT

        # Determine which data dict to use for display
        # If resolved_data exists (inheritance resolved), show everything
        self._display_data = profile.resolved_data if profile.resolved_data else profile.data
        self._inherited_keys = profile.inherited_keys if profile.inherited_keys else set()

        # ── Header (compact: 3 rows max) ──
        header_frame = tk.Frame(self, bg=theme.bg2)
        self._header_frame = header_frame
        header_frame.pack(fill="x", padx=10, pady=(6, 0))

        # Row 1: profile name with type prefix (double-click to rename)
        ptype_upper = profile.profile_type.upper()
        self._name_label = tk.Label(header_frame, text=f"{ptype_upper}  \u2022  {profile.name}",
                 bg=theme.bg2, fg=theme.fg, font=(UI_FONT, 17, "bold"), cursor="hand2")
        self._name_label.pack(anchor="w")
        self._name_label.bind("<Double-1>", lambda e: self._start_header_rename())
        _Tooltip(self._name_label, "Double-click to rename")

        # Row 2: status + inheritance + source — one line, plain text
        row2 = tk.Frame(header_frame, bg=theme.bg2)
        row2.pack(fill="x", pady=(2, 0))

        # Status text (colored, no bg box)
        if profile.modified:
            if profile.is_locked:
                status_text = "Re-targeted"
                status_fg = theme.converted
            else:
                status_text = "Universal"
                status_fg = theme.accent
        elif profile.is_locked:
            printers = profile.compatible_printers
            if printers:
                status_text = "Locked"
                status_fg = theme.locked
            else:
                # Locked to a printer profile via printer_settings_id
                psid = profile.data.get("printer_settings_id", "")
                if isinstance(psid, list):
                    psid = psid[0] if psid else ""
                if psid:
                    status_text = f"Locked to {psid}"
                    status_fg = theme.locked
                else:
                    status_text = "Universal"
                    status_fg = theme.accent
        else:
            status_text = "Universal"
            status_fg = theme.accent
        tk.Label(row2, text=status_text, bg=theme.bg2, fg=status_fg,
                 font=(UI_FONT, 13, "bold")).pack(side="left")

        # Separator dot + inheritance + source
        info_parts = []
        if profile.inherits:
            inherit_str = f"from {profile.inherits}"
            if not profile.resolved_data:
                inherit_str += " (unresolved)"
            info_parts.append(inherit_str)
        info_parts.append(profile.source_label)
        if info_parts:
            tk.Label(row2, text="  \u00b7  " + "  \u00b7  ".join(info_parts),
                     bg=theme.bg2, fg=theme.fg2, font=(UI_FONT, 13)).pack(side="left")

        # Row 3: parameter count summary (compact)
        display_keys = set(self._display_data.keys()) - _IDENTITY_KEYS
        override_count = len(set(profile.data.keys()) - _IDENTITY_KEYS)
        inherited_count = len(self._inherited_keys)
        known_layout = _ALL_FILAMENT_KEYS if profile.profile_type == "filament" else _ALL_PROCESS_KEYS

        count_parts = [f"{len(display_keys)} parameters"]
        if inherited_count > 0:
            count_parts.append(f"{override_count} overrides")
            count_parts.append(f"{inherited_count} inherited")
        info_parts_unknown = set(display_keys) - known_layout - _IDENTITY_KEYS
        if info_parts_unknown:
            count_parts.append(f"{len(info_parts_unknown)} unrecognized")
        tk.Label(header_frame, text=" \u00b7 ".join(count_parts), bg=theme.bg2, fg=theme.fg2,
                 font=(UI_FONT, 12)).pack(anchor="w", pady=(1, 0))

        # ── Sub-tab bar ──
        tab_bar = tk.Frame(self, bg=theme.bg2)
        tab_bar.pack(fill="x", padx=10, pady=(6, 0))

        self._tab_buttons = []
        self._current_tab = None
        tab_names = list(layout.keys())

        for tab_name in tab_names:
            btn = tk.Label(tab_bar, text=tab_name, bg=theme.bg3, fg=theme.fg,
                           font=(UI_FONT, 13), padx=10, pady=4, cursor="hand2",
                           highlightbackground=theme.border, highlightthickness=1)
            btn.pack(side="left", padx=(0, 2))
            btn.bind("<Button-1>", lambda e, tn=tab_name: self._switch_tab(tn))
            self._tab_buttons.append((tab_name, btn))

        # Separator below tabs
        tk.Frame(self, bg=theme.border, height=1).pack(fill="x", padx=8, pady=(2, 0))

        # ── Content area ──
        content_container = tk.Frame(self, bg=theme.param_bg)
        content_container.pack(fill="both", expand=True)

        self._content_canvas = tk.Canvas(content_container, bg=theme.param_bg, highlightthickness=0)
        self._content_sb = ttk.Scrollbar(content_container, orient="vertical",
                                          command=self._content_canvas.yview)
        self._content_frame = tk.Frame(self._content_canvas, bg=theme.param_bg)
        self._content_frame.bind("<Configure>",
                                  lambda e: self._content_canvas.configure(
                                      scrollregion=self._content_canvas.bbox("all")))
        self._canvas_window = self._content_canvas.create_window(
            (0, 0), window=self._content_frame, anchor="nw")
        self._content_canvas.configure(yscrollcommand=self._content_sb.set)
        self._content_canvas.pack(side="left", fill="both", expand=True)
        self._content_sb.pack(side="right", fill="y")

        self._content_canvas.bind("<Configure>",
                                   lambda e: self._content_canvas.itemconfig(
                                       self._canvas_window, width=e.width))
        # Scroll binding — bind to canvas and also recursively bind to content
        # frame children after each tab switch (see _bind_scroll_recursive)
        _bind_scroll(self._content_canvas, self._content_canvas)

        if tab_names:
            self._switch_tab(tab_names[0])

    def _switch_tab(self, tab_name):
        theme = self.theme
        self._current_tab = tab_name
        self._param_order = []  # Reset navigation order for new tab

        for tn, btn in self._tab_buttons:
            if tn == tab_name:
                btn.configure(fg=theme.accent_fg, bg=theme.accent2, font=(UI_FONT, 13, "bold"),
                              highlightbackground=theme.accent2)
            else:
                btn.configure(fg=theme.fg, bg=theme.bg3, font=(UI_FONT, 13),
                              highlightbackground=theme.border)

        for w in self._content_frame.winfo_children():
            w.destroy()

        profile = self.current_profile
        layout = FILAMENT_LAYOUT if profile.profile_type == "filament" else PROCESS_LAYOUT
        sections = layout.get(tab_name, {})

        display_data = self._display_data
        has_content = False
        if sections:
            for section_name, params in sections.items():
                if self._render_section(section_name, params, display_data):
                    has_content = True

        # On the last tab, show discovered (unrecognized) keys
        tab_names = list(layout.keys())
        if tab_name == tab_names[-1]:
            known = set()
            for secs in layout.values():
                for ps in secs.values():
                    for k, _ in ps:
                        known.add(k)
            known.update(_IDENTITY_KEYS)
            extra = {k: v for k, v in display_data.items() if k not in known}
            if extra:
                has_content = True
                # Humanize raw JSON keys: "adaptive_layer_height" → "Adaptive layer height"
                humanized = [(k, k.replace("_", " ").capitalize()) for k in sorted(extra)]
                self._render_section(
                    "Unrecognized parameters",
                    humanized,
                    display_data,
                    discovered=True
                )

        if not has_content:
            if sections:
                tk.Label(self._content_frame,
                         text="(No overrides in this tab — values inherited from parent)",
                         bg=theme.param_bg, fg=theme.fg2, font=(UI_FONT, 13)).pack(pady=20)
            else:
                tk.Label(self._content_frame, text="(No settings in this tab)",
                         bg=theme.param_bg, fg=theme.fg2, font=(UI_FONT, 13)).pack(pady=20)

        # Bind scroll events to all child widgets so scrolling works everywhere
        self._bind_scroll_recursive(self._content_frame)

    def _bind_scroll_recursive(self, widget):
        """Recursively bind scroll events to all children of a widget."""
        _bind_scroll(widget, self._content_canvas)
        for child in widget.winfo_children():
            self._bind_scroll_recursive(child)

    def _render_section(self, section_name, params, data, discovered=False):
        """Render a section. Returns True if any params were shown."""
        theme = self.theme

        # Check if any params exist in data first
        visible = [(k, l) for k, l in params if k in data]
        if not visible:
            return False

        # Section header with left accent bar
        section_header = tk.Frame(self._content_frame, bg=theme.param_bg)
        section_header.pack(fill="x", padx=10, pady=(10, 3))
        accent_bar = tk.Frame(section_header, bg=theme.warning if discovered else theme.accent, width=3)
        accent_bar.pack(side="left", fill="y", padx=(0, 8))
        fg = theme.warning if discovered else theme.btn_fg
        tk.Label(section_header, text=section_name, bg=theme.param_bg, fg=fg,
                 font=(UI_FONT, 15, "bold")).pack(side="left")

        for json_key, ui_label in visible:
            value = data[json_key]
            self._render_param(ui_label, json_key, value, discovered=discovered)

        return True

    def _get_raw_enum_str(self, value):
        """Extract the raw string for enum lookup, unwrapping single-element lists."""
        # BambuStudio stores per-extruder enum arrays where all elements are identical.
        # Unwrap to a single string for enum lookup when the array is uniform.
        if isinstance(value, list):
            unique = list(dict.fromkeys(str(v) for v in value))
            if len(unique) == 1:
                return unique[0]
        return str(value) if not isinstance(value, list) else None

    def _render_param(self, label, key, value, discovered=False):
        theme = self.theme
        is_inherited = key in self._inherited_keys

        row = tk.Frame(self._content_frame, bg=theme.param_bg)
        row.pack(fill="x", padx=14, pady=2)
        row.columnconfigure(0, minsize=_LABEL_COL_WIDTH)
        row.columnconfigure(1, weight=1)

        # Label column — bold for overrides, regular for inherited
        label_fg = theme.fg2 if is_inherited else theme.fg
        label_font = (UI_FONT, 13) if is_inherited else (UI_FONT, 13, "bold")
        lbl = tk.Label(row, text=label, bg=theme.param_bg, fg=label_fg, font=label_font,
                       anchor="w", width=0)
        lbl.grid(row=0, column=0, sticky="w", padx=(0, 12))
        # Tooltip for unrecognized params: show raw JSON key
        if discovered:
            _Tooltip(lbl, f"JSON key: {key}")

        display = self._format_value(value, key=key)

        # Check if this is an enum parameter that should get a dropdown
        raw_str = self._get_raw_enum_str(value)
        is_enum = key in ENUM_VALUES and raw_str is not None

        if key.endswith("_gcode") or key == "post_process" or key == "filament_notes":
            mono = ("Menlo", 13) if platform.system() == "Darwin" else ("Consolas", 13)
            txt = tk.Text(row, bg=theme.bg3, fg=theme.fg, font=mono,
                          height=min(8, max(2, str(value).count("\n") + 1)), width=40,
                          highlightbackground=theme.border, highlightthickness=1, wrap="word")
            txt.insert("1.0", str(value) if value else "")
            txt.grid(row=0, column=1, sticky="ew", padx=(4, 0))
            self._edit_vars[key] = (txt, value, "text")
        elif is_enum:
            self._render_enum_dropdown(row, key, value, raw_str, is_inherited)
        else:
            val_fg = theme.fg2 if is_inherited else theme.fg
            # Editable value with subtle background affordance
            val_frame = tk.Frame(row, bg=theme.edit_bg, highlightbackground=theme.border,
                                 highlightthickness=1, padx=4, pady=1)
            val_frame.grid(row=0, column=1, sticky="ew", padx=(4, 0))
            val_lbl = tk.Label(val_frame, text=display, bg=theme.edit_bg, fg=val_fg,
                               font=(UI_FONT, 13), anchor="w", cursor="xterm")
            val_lbl.pack(fill="x")
            # Click to edit
            val_lbl.bind("<Button-1>",
                         lambda e, r=val_frame, l=val_lbl, k=key, v=value, fg=val_fg:
                             self._activate_edit(r, l, k, v, fg))
            val_frame.bind("<Button-1>",
                           lambda e, r=val_frame, l=val_lbl, k=key, v=value, fg=val_fg:
                               self._activate_edit(r, l, k, v, fg))
            self._edit_vars[key] = (None, value, "label")
            self._param_order.append((key, val_frame, val_fg))

    def _render_enum_dropdown(self, row, key, original_value, raw_str, is_inherited):
        """Render a styled dropdown for an enum parameter."""
        theme = self.theme
        known_pairs = ENUM_VALUES[key]

        # Build human labels list; ensure current value is included
        human_labels = [hl for _, hl in known_pairs]
        known_json_vals = {jv for jv, _ in known_pairs}

        current_label = _get_enum_human_label(key, raw_str)
        extra_label_to_json = {}
        if raw_str not in known_json_vals:
            # Unknown value — append humanized label; remember the reverse mapping
            human_labels.append(current_label)
            extra_label_to_json[current_label] = raw_str

        value_var = tk.StringVar(value=current_label)
        # Fit dropdown width to longest option text
        max_len = max((len(hl) for hl in human_labels), default=10)
        cb_width = max(max_len + 2, 12)
        combobox = ttk.Combobox(row, textvariable=value_var, values=human_labels,
                          state="readonly", style="Param.TCombobox",
                          font=(UI_FONT, 13), width=cb_width)
        combobox.grid(row=0, column=1, sticky="w", padx=(4, 0))

        def _on_enum_change(event=None):
            selected_label = value_var.get()
            # Use sentinel to correctly handle empty-string JSON values
            _sentinel = object()
            known_reverse = _ENUM_LABEL_TO_JSON.get(key, {})
            new_json_val = known_reverse.get(selected_label, _sentinel)
            if new_json_val is _sentinel:
                new_json_val = extra_label_to_json.get(selected_label, selected_label)
            if isinstance(original_value, list):
                new_val = [new_json_val] * len(original_value)
            else:
                new_val = new_json_val
            if new_val != original_value:
                if self._pre_edit_modified is None:
                    self._pre_edit_modified = self.current_profile.modified
                self._undo_stack.append((key, original_value))
                self.current_profile.data[key] = new_val
                self.current_profile.modified = True
                self._edit_vars[key] = (value_var, new_val, "combo")

        combobox.bind("<<ComboboxSelected>>", _on_enum_change)
        self._edit_vars[key] = (value_var, original_value, "combo")


    def _activate_edit(self, container, label_widget, key, original_value, fg_color):
        """Replace a value label with an editable Entry on click."""
        theme = self.theme
        label_widget.destroy()
        # Update container border to signal active editing
        container.configure(highlightbackground=theme.accent)

        display = self._format_value(original_value, key=key)
        value_var = tk.StringVar(value=display)
        entry = tk.Entry(container, textvariable=value_var, bg=theme.edit_bg, fg=fg_color,
                         font=(UI_FONT, 13), insertbackground=theme.fg,
                         highlightthickness=0, relief="flat")
        entry.pack(fill="x")
        entry.focus_set()
        entry.select_range(0, "end")

        self._edit_vars[key] = (value_var, original_value, "entry")

        def finish_edit(event=None):
            self._commit_single(key)
            new_val = self.current_profile.data.get(key, original_value)
            new_display = self._format_value(new_val, key=key)
            entry.destroy()
            container.configure(highlightbackground=theme.border)
            new_lbl = tk.Label(container, text=new_display, bg=theme.edit_bg, fg=fg_color,
                               font=(UI_FONT, 13), anchor="w", cursor="xterm")
            new_lbl.pack(fill="x")
            new_lbl.bind("<Button-1>",
                         lambda e, r=container, l=new_lbl, k=key, v=new_val, f=fg_color:
                             self._activate_edit(r, l, k, v, f))
            container.bind("<Button-1>",
                           lambda e, r=container, l=new_lbl, k=key, v=new_val, f=fg_color:
                               self._activate_edit(r, l, k, v, f))
            self._edit_vars[key] = (None, new_val, "label")

        def tab_next(event=None):
            finish_edit()
            # Find next editable param and activate it
            idx = next((i for i, (k, *_) in enumerate(self._param_order) if k == key), -1)
            if idx >= 0 and idx + 1 < len(self._param_order):
                next_key, next_container, next_fg = self._param_order[idx + 1]
                next_val = self.current_profile.data.get(next_key)
                if next_val is not None:
                    children = next_container.winfo_children()
                    if children:
                        self._activate_edit(next_container, children[0],
                                            next_key, next_val, next_fg)
            return "break"

        entry.bind("<Return>", finish_edit)
        entry.bind("<Tab>", tab_next)
        entry.bind("<FocusOut>", finish_edit)
        entry.bind("<Escape>", lambda e: finish_edit())

    def _commit_single(self, key):
        """Commit a single edited value back to the profile data."""
        if not self.current_profile or key not in self._edit_vars:
            return
        var_or_widget, original, kind = self._edit_vars[key]
        if kind == "entry":
            new_str = var_or_widget.get()
        elif kind == "text":
            new_str = var_or_widget.get("1.0", "end-1c")
        else:
            return

        new_val = self._parse_edit(new_str, original)
        if new_val != original:
            if self._pre_edit_modified is None:
                self._pre_edit_modified = self.current_profile.modified
            self._undo_stack.append((key, original))
            self.current_profile.data[key] = new_val
            self.current_profile.modified = True
            self._edit_vars[key] = (var_or_widget, new_val, kind)

    def _commit_edits(self):
        """Commit all pending edits back to the current profile."""
        if not self.current_profile:
            return
        for key in list(self._edit_vars):
            self._commit_single(key)

    @staticmethod
    def _parse_edit(text: str, original):
        """Convert edited text back to the appropriate Python type,
        matching the original value's type."""
        text = text.strip()
        if isinstance(original, bool):
            return text.lower() in ("yes", "true", "1")
        if isinstance(original, int):
            try:
                return int(text)
            except ValueError:
                try:
                    return int(float(text))
                except ValueError:
                    return original
        if isinstance(original, float):
            try:
                return float(text)
            except ValueError:
                return original
        if isinstance(original, list):
            # If user entered a single value, wrap in list matching original length
            parts = [s.strip() for s in text.split(",")]
            result = []
            for i, part in enumerate(parts):
                ref = original[i] if i < len(original) else original[0] if original else ""
                if isinstance(ref, int):
                    try:
                        result.append(int(part))
                    except ValueError:
                        result.append(ref)
                elif isinstance(ref, float):
                    try:
                        result.append(float(part))
                    except ValueError:
                        result.append(ref)
                else:
                    result.append(part)
            # Pad shorter input to original length using last entered value.
            # Guard: if all parts failed to parse, result may be empty — don't crash.
            if result and len(result) < len(original):
                result.extend([result[-1]] * (len(original) - len(result)))
            return result
        return text

    @staticmethod
    def _format_value(value, key=None):
        if isinstance(value, list):
            # Collapse identical array entries (BambuStudio stores per-extruder)
            unique = list(dict.fromkeys(str(v) for v in value))
            if len(unique) == 1:
                raw = unique[0]
                if key and key in ENUM_VALUES:
                    return _get_enum_human_label(key, raw)
                return raw
            return ", ".join(str(v) for v in value)
        elif isinstance(value, bool):
            return "Yes" if value else "No"
        elif value is None:
            return "N/A"
        value_str = str(value)
        if key and key in ENUM_VALUES:
            return _get_enum_human_label(key, value_str)
        return value_str[:_VALUE_TRUNCATE_LONG] + "..." if len(value_str) > _VALUE_TRUNCATE_LONG else value_str

    def _start_header_rename(self):
        """Replace the profile name label with an editable Entry on double-click."""
        if not self.current_profile:
            return
        theme = self.theme
        profile = self.current_profile
        ptype_upper = profile.profile_type.upper()

        self._name_label.destroy()
        # Get the header frame (parent of the label)
        header_frame = self._header_frame

        name_frame = tk.Frame(header_frame, bg=theme.bg2)
        name_frame.pack(anchor="w", fill="x")

        prefix = tk.Label(name_frame, text=f"{ptype_upper}  \u2022  ",
                          bg=theme.bg2, fg=theme.fg, font=(UI_FONT, 17, "bold"))
        prefix.pack(side="left")

        name_var = tk.StringVar(value=profile.name)
        entry = tk.Entry(name_frame, textvariable=name_var, bg=theme.bg3, fg=theme.fg,
                         insertbackground=theme.fg, font=(UI_FONT, 17, "bold"),
                         highlightbackground=theme.accent, highlightthickness=1,
                         relief="flat")
        entry.pack(side="left", fill="x", expand=True)
        entry.focus_set()
        entry.select_range(0, "end")

        def _finish(event=None):
            new_name = name_var.get().strip()
            if new_name and new_name != profile.name:
                profile.data["name"] = new_name
                profile.modified = True
            # Rebuild: destroy the edit frame, re-create the label
            name_frame.destroy()
            self._name_label = tk.Label(header_frame, text=f"{ptype_upper}  \u2022  {profile.name}",
                     bg=theme.bg2, fg=theme.fg, font=(UI_FONT, 17, "bold"), cursor="hand2")
            # Insert at top of header
            self._name_label.pack(anchor="w", before=header_frame.winfo_children()[0] if header_frame.winfo_children() else None)
            self._name_label.bind("<Double-1>", lambda e: self._start_header_rename())

        def _cancel(event=None):
            name_frame.destroy()
            self._name_label = tk.Label(header_frame, text=f"{ptype_upper}  \u2022  {profile.name}",
                     bg=theme.bg2, fg=theme.fg, font=(UI_FONT, 17, "bold"), cursor="hand2")
            self._name_label.pack(anchor="w", before=header_frame.winfo_children()[0] if header_frame.winfo_children() else None)
            self._name_label.bind("<Double-1>", lambda e: self._start_header_rename())

        entry.bind("<Return>", _finish)
        entry.bind("<FocusOut>", _finish)
        entry.bind("<Escape>", _cancel)


# --- Profile List Panel (reusable for each top-level tab) ---

class ProfileListPanel(tk.Frame):
    """Left panel with a list of profiles and a detail viewer on the right."""

    def __init__(self, parent, theme, profile_type, app):
        super().__init__(parent, bg=theme.bg)
        self.theme = theme
        self.profile_type = profile_type  # "process" or "filament"
        self.app = app
        self.profiles = []

        self._build()

    def _build(self):
        theme = self.theme

        paned = tk.PanedWindow(self, orient="horizontal", bg=theme.border,
                                sashwidth=4, sashrelief="flat",
                                opaqueresize=True)
        paned.pack(fill="both", expand=True)

        # ── Left: profile list ──
        left = tk.Frame(paned, bg=theme.bg2)
        paned.add(left, minsize=320, width=480)

        # ── Filter row ──
        filter_frame = tk.Frame(left, bg=theme.bg3, highlightbackground=theme.border, highlightthickness=1)
        filter_frame.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(filter_frame, text="\u2315", bg=theme.bg3, fg=theme.fg3, font=(UI_FONT, 14),
                 padx=6).pack(side="left")
        self._filter_var = tk.StringVar()
        self._filter = tk.Entry(filter_frame, textvariable=self._filter_var, bg=theme.bg3, fg=theme.fg,
                                insertbackground=theme.fg, highlightthickness=0,
                                font=(UI_FONT, 13), relief="flat", bd=0)
        self._filter.pack(side="left", fill="x", expand=True, ipady=4)
        self._filter.insert(0, "Filter...")
        self._filter.configure(fg=theme.placeholder_fg, font=(UI_FONT, 13, "italic"))
        self._filter.bind("<FocusIn>", self._filter_in)
        self._filter.bind("<FocusOut>", self._filter_out)
        self._placeholder = True

        # ── Group-by dropdown ──
        group_options = {
            "No grouping": "none",
            "Printer": "printer",
            "Manufacturer": "manufacturer",
            "Status": "status",
        }
        self._group_labels = list(group_options.keys())
        self._group_values = list(group_options.values())
        self._group_var = tk.StringVar(value=self._group_labels[0])
        self._group_by = "none"

        group_frame = tk.Frame(left, bg=theme.bg2)
        group_frame.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(group_frame, text="Group:", bg=theme.bg2, fg=theme.fg3,
                 font=(UI_FONT, 13)).pack(side="left", padx=(2, 6))
        group_cb = ttk.Combobox(group_frame, textvariable=self._group_var,
                                values=self._group_labels,
                                state="readonly", style="Param.TCombobox",
                                font=(UI_FONT, 13), width=16)
        group_cb.pack(side="left")
        group_cb.bind("<<ComboboxSelected>>", self._on_group_change)

        # ── Treeview (must exist before trace) ──
        tree_frame = tk.Frame(left, bg=theme.bg2)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        self.tree = ttk.Treeview(tree_frame, columns=("name", "status", "origin"),
                                  show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=24, minwidth=24, stretch=False)
        self.tree.heading("name", text="Profile Name")
        self.tree.heading("status", text="Status")
        self.tree.heading("origin", text="Origin")
        self.tree.column("name", width=220, minwidth=120)
        self.tree.column("status", width=120, minwidth=100, stretch=False)
        self.tree.column("origin", width=90, minwidth=60)
        # Tag styles for alternating rows and colored status
        self.tree.tag_configure("row_even", background=theme.bg2)
        self.tree.tag_configure("row_odd", background=theme.bg3)
        self.tree.tag_configure("status_universal", foreground=theme.accent)
        self.tree.tag_configure("status_locked", foreground=theme.locked)
        self.tree.tag_configure("status_converted", foreground=theme.converted)
        self.tree.tag_configure("group_header", background=theme.bg,
                                 foreground=theme.btn_fg, font=(UI_FONT, 11, "bold"))
        self._collapsed_groups = set()  # Track which groups are collapsed

        tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click_rename)

        # ── Treeview hover tooltip (shows full name + double-click hint) ──
        self._tree_tip = None
        self._tree_tip_after = None
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", self._on_tree_leave)

        # ── Right-click context menu ──
        if platform.system() == "Darwin":
            self.tree.bind("<Button-2>", self._on_context_menu)
            self.tree.bind("<Control-Button-1>", self._on_context_menu)
        else:
            self.tree.bind("<Button-3>", self._on_context_menu)

        # ── Action rows below treeview ──
        # Row 1: secondary actions (left) + utility (right)
        action_row1 = tk.Frame(left, bg=theme.bg2)
        action_row1.pack(fill="x", padx=6, pady=(0, 2))
        _make_btn(action_row1, "Remove from list",
                  lambda: self.app._on_remove(),
                  bg=theme.bg4, fg=theme.fg2,
                  font=(UI_FONT, 10), padx=6, pady=3).pack(side="left", padx=(0, 3))
        _make_btn(action_row1, "Clear list",
                  lambda: self.app._on_clear_list(),
                  bg=theme.bg4, fg=theme.warning,
                  font=(UI_FONT, 10), padx=6, pady=3).pack(side="left", padx=(0, 3))
        _make_btn(action_row1, "Show Folder",
                  lambda: self.app._on_show_folder(),
                  bg=theme.bg4, fg=theme.btn_fg,
                  font=(UI_FONT, 10), padx=6, pady=3).pack(side="right", padx=(0, 3))
        _make_btn(action_row1, "Compare",
                  lambda: self.app._on_compare(),
                  bg=theme.bg4, fg=theme.btn_fg,
                  font=(UI_FONT, 10), padx=6, pady=3).pack(side="right", padx=(0, 3))

        # Thin separator between secondary and primary actions
        tk.Frame(left, bg=theme.border, height=1).pack(fill="x", padx=6, pady=(2, 2))

        # Row 2: primary convert actions
        action_row2 = tk.Frame(left, bg=theme.bg2)
        action_row2.pack(fill="x", padx=6, pady=(0, 4))
        _make_btn(action_row2, "Convert Selected",
                  lambda: self.app._on_convert(),
                  bg=theme.accent2, fg=theme.accent_fg,
                  font=(UI_FONT, 11, "bold"),
                  padx=8, pady=4).pack(side="right", padx=(0, 4))
        _make_btn(action_row2, "Convert All",
                  lambda: self.app._on_convert_all(),
                  bg=theme.convert_all_bg, fg=theme.btn_fg,
                  font=(UI_FONT, 11, "bold"), padx=8, pady=4).pack(side="right", padx=(0, 4))

        # ── Right: detail panel ──
        self.detail = ProfileDetailPanel(paned, t)
        paned.add(self.detail, minsize=300)

        # Register filter trace now that tree exists
        self._filter_var.trace_add("write", lambda *a: self._refresh_list())

    def _filter_in(self, e):
        if self._placeholder:
            self._filter.delete(0, "end")
            self._filter.configure(fg=self.theme.fg, font=(UI_FONT, 13))
            self._placeholder = False

    def _filter_out(self, e):
        if not self._filter_var.get():
            self._filter.insert(0, "Filter...")
            self._filter.configure(fg=self.theme.placeholder_fg, font=(UI_FONT, 13, "italic"))
            self._placeholder = True

    def _on_group_change(self, event=None):
        idx = self._group_labels.index(self._group_var.get())
        self._group_by = self._group_values[idx]
        self._collapsed_groups.clear()
        self._refresh_list()

    def _on_clear(self):
        if self.profiles:
            self.profiles.clear()
            self._refresh_list()
            self.detail._show_placeholder()
            self.app._update_status("List cleared.")

    def add_profiles(self, new_profiles):
        self.profiles.extend(new_profiles)
        self._refresh_list()

    def get_selected_profiles(self):
        result = []
        for iid in self.tree.selection():
            s = str(iid)
            if s.startswith("_grp_"):
                # Group header selected — select all children
                for child in self.tree.get_children(iid):
                    idx = int(child)
                    # Guard: defensive against stale IIDs if a refresh races with selection
                    # (single-threaded tkinter makes true races impossible, but belt-and-suspenders).
                    if idx < len(self.profiles):
                        result.append(self.profiles[idx])
            else:
                idx = int(s)
                # Guard: defensive against stale IIDs if a refresh races with selection
                # (single-threaded tkinter makes true races impossible, but belt-and-suspenders).
                if idx < len(self.profiles):
                    result.append(self.profiles[idx])
        return result

    def remove_selected(self):
        indices = set()
        for iid in self.tree.selection():
            s = str(iid)
            if s.startswith("_grp_"):
                for child in self.tree.get_children(iid):
                    indices.add(int(child))
            else:
                indices.add(int(s))
        for i in sorted(indices, reverse=True):
            if i < len(self.profiles):
                self.profiles.pop(i)
        self._refresh_list()
        self.detail._show_placeholder()

    def _on_delete_from_disk(self):
        """Delete selected profiles' source files from disk with confirmation."""
        selected = self.get_selected_profiles()
        if not selected:
            return
        # Collect unique file paths
        paths = []
        for profile in selected:
            if profile.source_path and os.path.isfile(profile.source_path):
                if profile.source_path not in [x[1] for x in paths]:
                    paths.append((profile.name, profile.source_path))

        if not paths:
            messagebox.showinfo("Nothing to delete",
                                "No source files found on disk for the selected profiles.")
            return

        # Build confirmation message
        count = len(paths)
        if count == 1:
            name, fpath = paths[0]
            msg = (f"Permanently delete this file?\n\n"
                   f"  {os.path.basename(fpath)}\n\n"
                   f"Location: {os.path.dirname(fpath)}\n\n"
                   f"This cannot be undone.")
        else:
            file_list = "\n".join(f"  \u2022 {os.path.basename(fp)}" for _, fp in paths[:8])
            if count > 8:
                file_list += f"\n  ... and {count - 8} more"
            msg = (f"Permanently delete {count} files?\n\n"
                   f"{file_list}\n\n"
                   f"This cannot be undone.")

        confirmed = messagebox.askyesno("Delete from Disk", msg, icon="warning")
        if not confirmed:
            return

        deleted = 0
        errors = []
        for name, fpath in paths:
            try:
                os.remove(fpath)
                deleted += 1
            except OSError as e:
                errors.append(f"{os.path.basename(fpath)}: {e.strerror}")

        # Also remove from list
        self.remove_selected()

        if errors:
            messagebox.showwarning("Some files could not be deleted",
                                   "\n".join(errors))
        else:
            self.app._update_status(f"Deleted {deleted} file{'s' if deleted != 1 else ''} from disk.")

    def select_all(self):
        all_items = []
        for child in self.tree.get_children():
            s = str(child)
            if s.startswith("_grp_"):
                all_items.extend(self.tree.get_children(child))
            else:
                all_items.append(child)
        if all_items:
            self.tree.selection_set(all_items)

    def _insert_profile_row(self, parent_iid, profile_idx, profile, row_idx):
        """Insert a single profile row into the treeview."""
        status, status_tag = self._profile_status(profile)
        alt_tag = "row_even" if row_idx % 2 == 0 else "row_odd"
        self.tree.insert(parent_iid, "end", iid=str(profile_idx),
                         values=(profile.name, status, profile.origin or "\u2014"),
                         tags=(alt_tag, status_tag))

    def _refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        filter_text = self._filter_var.get().lower()
        if filter_text == "filter...":
            filter_text = ""

        # Build filtered list with original indices
        visible = []
        for i, profile in enumerate(self.profiles):
            if filter_text and filter_text not in f"{profile.name} {profile.origin} {profile.source_label}".lower():
                continue
            visible.append((i, profile))

        group_by = self._group_by

        # Show/hide tree column (expand/collapse indicators)
        if group_by == "none":
            self.tree.column("#0", width=0, minwidth=0)
        else:
            self.tree.column("#0", width=24, minwidth=24)

        if group_by == "none":
            # Flat list — no grouping
            row_idx = 0
            for i, profile in visible:
                self._insert_profile_row("", i, profile, row_idx)
                row_idx += 1
        else:
            # Grouped — collect into buckets preserving order
            groups = {}
            group_order = []
            for i, profile in visible:
                key = profile.group_key(group_by)
                if key not in groups:
                    groups[key] = []
                    group_order.append(key)
                groups[key].append((i, profile))

            row_idx = 0
            for gname in group_order:
                items = groups[gname]
                gid = f"_grp_{gname}"
                is_open = gname not in self._collapsed_groups
                count = len(items)
                self.tree.insert("", "end", iid=gid, open=is_open,
                                 text="",
                                 values=(f"{gname}  ({count})", "", ""),
                                 tags=("group_header",))
                for i, profile in items:
                    self._insert_profile_row(gid, i, profile, row_idx)
                    row_idx += 1

        # Auto-select the first profile item (skip group headers)
        first_profile = self._first_profile_item()
        if first_profile:
            self.tree.selection_set(first_profile)
            self._on_select()

    @staticmethod
    def _profile_status(p):
        """Return (status_text, status_tag) for a profile."""
        if p.modified:
            return ("Converted", "status_converted")
        elif p.is_locked:
            if p.compatible_printers:
                return ("Locked", "status_locked")
            else:
                return ("Locked to profile", "status_locked")
        else:
            return ("Universal", "status_universal")

    def _first_profile_item(self):
        """Find the first non-group-header item in the tree."""
        for child in self.tree.get_children():
            iid = str(child)
            if iid.startswith("_grp_"):
                # It's a group — get its first child
                sub = self.tree.get_children(child)
                if sub:
                    return sub[0]
            else:
                return child
        return None

    def _on_select(self, event=None):
        sel = self.tree.selection()
        # Filter out group headers for profile-level logic
        profile_sel = [s for s in sel if not str(s).startswith("_grp_")]

        if len(profile_sel) == 1:
            idx = int(profile_sel[0])
            if idx < len(self.profiles):
                self.detail.show_profile(self.profiles[idx])
        elif len(profile_sel) > 1:
            self.detail._show_placeholder(
                f"{len(profile_sel)} profiles selected.\n\nUse 'Convert Selected' to modify\nor select exactly 2 for 'Compare'.")
        elif len(sel) == 1 and str(sel[0]).startswith("_grp_"):
            # Group header selected — toggle collapse
            gid = str(sel[0])
            gname = gid[5:]  # strip "_grp_" prefix
            if self.tree.item(gid, "open"):
                self._collapsed_groups.add(gname)
                self.tree.item(gid, open=False)
            else:
                self._collapsed_groups.discard(gname)
                self.tree.item(gid, open=True)
        else:
            self.detail._show_placeholder()

    def _on_context_menu(self, event):
        """Show right-click context menu on the treeview."""
        theme = self.theme
        # Select the item under cursor if not already selected
        item = self.tree.identify_row(event.y)
        if item:
            current = self.tree.selection()
            if item not in current:
                self.tree.selection_set(item)
                self._on_select()

        sel = self.tree.selection()
        if not sel:
            return

        menu = tk.Menu(self, tearoff=0, bg=theme.bg3, fg=theme.fg,
                       activebackground=theme.accent2, activeforeground=theme.accent_fg,
                       font=(UI_FONT, 12))

        count = len(sel)
        menu.add_command(label=f"Export {count} profile{'s' if count > 1 else ''}...",
                         command=self.app._on_export)

        # Install to Slicer submenu
        slicers = self.app.detected_slicers
        if slicers:
            install_menu = tk.Menu(menu, tearoff=0, bg=theme.bg3, fg=theme.fg,
                                   activebackground=theme.accent2, activeforeground=theme.accent_fg,
                                   font=(UI_FONT, 12))
            for name, path in slicers.items():
                install_menu.add_command(
                    label=name,
                    command=lambda n=name, p=path: self.app._on_install_to_slicer(n, p))
            menu.add_cascade(label="Install to Slicer", menu=install_menu)

        menu.add_separator()
        # Only show Rename for single profile selection (not group headers)
        profile_sel = [s for s in sel if not str(s).startswith("_grp_")]
        if len(profile_sel) == 1:
            menu.add_command(label="Rename", command=self._rename_selected)
        if count == 2:
            menu.add_command(label="Compare", command=self.app._on_compare)
        menu.add_command(label="Duplicate", command=self.app._on_create_from_profile)
        menu.add_command(label="Show Folder", command=self.app._on_show_folder)
        menu.add_separator()
        menu.add_command(label="Remove from list", command=self.app._on_remove)
        menu.add_command(label="Delete from disk...", command=lambda: self._on_delete_from_disk())

        menu.tk_popup(event.x_root, event.y_root)

    def _on_double_click_rename(self, event):
        """Double-click a profile row to rename it."""
        item = self.tree.identify_row(event.y)
        if not item or str(item).startswith("_grp_"):
            return
        idx = int(item)
        if idx < len(self.profiles):
            self._start_inline_rename(item, idx)
        return "break"  # Prevent default expand/collapse behavior

    def _on_tree_motion(self, event):
        """Show tooltip with full profile name on hover."""
        item = self.tree.identify_row(event.y)
        if self._tree_tip_after:
            self.tree.after_cancel(self._tree_tip_after)
            self._tree_tip_after = None
        if self._tree_tip:
            self._tree_tip.destroy()
            self._tree_tip = None
        if not item:
            return
        iid = str(item)
        if iid.startswith("_grp_"):
            return
        idx = int(iid)
        if idx >= len(self.profiles):
            return
        profile = self.profiles[idx]
        tip_text = profile.name
        def _show():
            if self._tree_tip:
                self._tree_tip.destroy()
            x = self.tree.winfo_rootx() + event.x + 16
            y = self.tree.winfo_rooty() + event.y + 20
            tooltip_window = tk.Toplevel(self.tree)
            tooltip_window.wm_overrideredirect(True)
            tooltip_window.wm_geometry(f"+{x}+{y}")
            tk.Label(tooltip_window, text=f"{tip_text}\n(double-click to rename)",
                     bg="#333333", fg="#ededed", font=(UI_FONT, 11),
                     padx=8, pady=4, relief="solid", bd=1, justify="left").pack()
            self._tree_tip = tooltip_window
        self._tree_tip_after = self.tree.after(_TREE_TOOLTIP_DELAY_MS, _show)

    def _on_tree_leave(self, event):
        if self._tree_tip_after:
            self.tree.after_cancel(self._tree_tip_after)
            self._tree_tip_after = None
        if self._tree_tip:
            self._tree_tip.destroy()
            self._tree_tip = None

    def _rename_selected(self):
        """Rename the single selected profile."""
        sel = [s for s in self.tree.selection() if not str(s).startswith("_grp_")]
        if len(sel) != 1:
            return
        idx = int(sel[0])
        if idx < len(self.profiles):
            self._start_inline_rename(sel[0], idx)

    def _start_inline_rename(self, iid, idx):
        """Show an inline Entry widget over the profile name in the treeview."""
        theme = self.theme
        profile = self.profiles[idx]

        # Get the bounding box of the "name" column for this item
        try:
            bbox = self.tree.bbox(iid, column="name")
        except Exception:
            return
        if not bbox:
            return
        x, y, w, h = bbox

        name_var = tk.StringVar(value=profile.name)
        entry = tk.Entry(self.tree, textvariable=name_var, bg=theme.bg3, fg=theme.fg,
                         insertbackground=theme.fg, font=(UI_FONT, 12),
                         highlightbackground=theme.accent, highlightthickness=1,
                         relief="flat")
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, "end")

        def _finish(event=None):
            new_name = name_var.get().strip()
            entry.destroy()
            if new_name and new_name != profile.name:
                profile.data["name"] = new_name
                profile.modified = True
                self._refresh_list()
                # Re-select and show updated profile
                try:
                    self.tree.selection_set(str(idx))
                except Exception:
                    pass
                self._on_select()

        def _cancel(event=None):
            entry.destroy()

        entry.bind("<Return>", _finish)
        entry.bind("<FocusOut>", _finish)
        entry.bind("<Escape>", _cancel)


# --- Main Application ---

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.theme = Theme(dark=True)  # Always teal dark
        self.detected_slicers = SlicerDetector.find_all()
        self.preset_index = PresetIndex()  # For resolving inheritance

        # Build preset index from all detected slicers
        for name, path in self.detected_slicers.items():
            self.preset_index.build(path, name)

        self.title(APP_NAME)
        self.geometry(f"{_WIN_WIDTH}x{_WIN_HEIGHT}")
        self.minsize(1000, 600)
        self.configure(bg=self.theme.bg)

        self._configure_styles()
        self._build_menu()
        self._build_ui()
        self._update_status("Ready. Open profiles or extract from .3mf to get started.")

    def _configure_styles(self):
        theme = self.theme
        style = ttk.Style(self)
        available = style.theme_names()
        if "clam" in available:
            style.theme_use("clam")
        style.configure(".", background=theme.bg, foreground=theme.fg)
        style.configure("TFrame", background=theme.bg)
        style.configure("TLabel", background=theme.bg, foreground=theme.fg)
        style.configure("Treeview", background=theme.bg2, foreground=theme.fg,
                         fieldbackground=theme.bg2, rowheight=_TREE_ROW_HEIGHT)
        style.map("Treeview",
                   background=[("selected", theme.sel)],
                   foreground=[("selected", theme.fg)])
        style.configure("Treeview.Heading", background=theme.bg4, foreground=theme.fg,
                         font=(UI_FONT, 12, "bold"), relief="flat", padding=(6, 4))
        style.map("Treeview.Heading",
                   background=[("active", theme.bg3)])
        # Combobox for enum parameter dropdowns
        style.configure("Param.TCombobox",
                         fieldbackground=theme.bg3, background=theme.bg3,
                         foreground=theme.fg, arrowcolor=theme.fg2,
                         borderwidth=1, relief="flat")
        style.map("Param.TCombobox",
                   fieldbackground=[("readonly", theme.bg3)],
                   foreground=[("readonly", theme.fg)],
                   background=[("readonly", theme.bg3)])
        # Style the dropdown list itself
        self.option_add("*TCombobox*Listbox.background", theme.bg3)
        self.option_add("*TCombobox*Listbox.foreground", theme.fg)
        self.option_add("*TCombobox*Listbox.selectBackground", theme.accent2)
        self.option_add("*TCombobox*Listbox.selectForeground", theme.accent_fg)
        self.option_add("*TCombobox*Listbox.font", (UI_FONT, 13))

        style.configure("TNotebook", background=theme.bg, borderwidth=0)
        style.configure("TNotebook.Tab", background=theme.bg4, foreground=theme.fg2,
                         padding=(18, 8), font=(UI_FONT, 12))
        style.map("TNotebook.Tab",
                   background=[("selected", theme.accent2)],
                   foreground=[("selected", theme.accent_fg)],
                   padding=[("selected", (18, 8))])  # Same padding so selected tab doesn't shrink

    def _build_menu(self):
        menubar = tk.Menu(self, bg=self.theme.bg3, fg=self.theme.fg)
        file_menu = tk.Menu(menubar, tearoff=0, bg=self.theme.bg3, fg=self.theme.fg)
        mod_key = "Cmd" if platform.system() == "Darwin" else "Ctrl"

        file_menu.add_command(label="Import (JSON, 3MF)...", command=self._on_import,
                              accelerator=f"{mod_key}+O")
        file_menu.add_command(label="Load System Presets from Slicers", command=self._on_load_presets)
        file_menu.add_separator()
        file_menu.add_command(label="Export Selected...", command=self._on_export,
                              accelerator=f"{mod_key}+E")
        if self.detected_slicers:
            exp = tk.Menu(file_menu, tearoff=0, bg=self.theme.bg3, fg=self.theme.fg)
            for name, path in self.detected_slicers.items():
                exp.add_command(label=f"Export to {name}...",
                                command=lambda p=path, n=name: self._on_export_to_slicer(n, p))
            file_menu.add_cascade(label="Export to Slicer", menu=exp)

        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0, bg=self.theme.bg3, fg=self.theme.fg)
        edit_menu.add_command(label="Select All", command=self._on_select_all,
                              accelerator=f"{mod_key}+A")
        menubar.add_cascade(label="Edit", menu=edit_menu)

        help_menu = tk.Menu(menubar, tearoff=0, bg=self.theme.bg3, fg=self.theme.fg)
        help_menu.add_command(label="About", command=self._on_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)
        mod_key = "Command" if platform.system() == "Darwin" else "Control"
        self.bind(f"<{mod_key}-o>", lambda e: self._on_import())
        self.bind(f"<{mod_key}-e>", lambda e: self._on_export())
        self.bind(f"<{mod_key}-a>", lambda e: self._on_select_all())

    def _build_ui(self):
        theme = self.theme

        # ── Status bar (pack first so it stays at bottom) ──
        self.status_var = tk.StringVar()
        status_frame = tk.Frame(self, bg=theme.bg)
        status_frame.pack(fill="x", side="bottom")
        self._count_var = tk.StringVar()
        tk.Label(status_frame, textvariable=self._count_var, anchor="w", bg=theme.bg, fg=theme.fg2,
                 font=(UI_FONT, 12), padx=12, pady=4).pack(side="left")
        tk.Label(status_frame, textvariable=self.status_var, anchor="w", bg=theme.bg, fg=theme.fg3,
                 font=(UI_FONT, 12), padx=6, pady=4).pack(side="left", fill="x", expand=True)
        if self.detected_slicers:
            tk.Label(status_frame, text=f"Detected: {', '.join(self.detected_slicers.keys())}",
                     bg=theme.bg, fg=theme.fg3, font=(UI_FONT, 12), padx=12).pack(side="right")

        # ── Toolbar row (above notebook) ──
        toolbar_row = tk.Frame(self, bg=theme.bg)
        toolbar_row.pack(fill="x", side="top")

        # Tab labels on the left (custom drawn so toolbar shares the row)
        self._tab_var = tk.StringVar(value="process")
        tab_frame = tk.Frame(toolbar_row, bg=theme.bg)
        tab_frame.pack(side="left", padx=(4, 0), pady=(4, 0))

        self._process_tab = _make_btn(tab_frame, "  Process  ",
                  lambda: self._switch_tab("process"),
                  bg=theme.accent2, fg=theme.accent_fg,
                  font=(UI_FONT, 13, "bold"), padx=14, pady=6)
        self._process_tab.pack(side="left", padx=(0, 2))

        self._filament_tab = _make_btn(tab_frame, "  Filament  ",
                  lambda: self._switch_tab("filament"),
                  bg=theme.bg4, fg=theme.btn_fg,
                  font=(UI_FONT, 13), padx=14, pady=6)
        self._filament_tab.pack(side="left")

        # Toolbar buttons on the right
        toolbar = tk.Frame(toolbar_row, bg=theme.bg)
        toolbar.pack(side="right", padx=(0, 8), pady=(4, 0))

        btn_font = (UI_FONT, 12)
        btn_pad = 10

        _make_btn(toolbar, "Import (JSON, 3MF)",
                  self._on_import,
                  bg=theme.bg4, fg=theme.btn_fg, font=btn_font,
                  padx=btn_pad, pady=5).pack(side="left", padx=(0, 4))

        _make_btn(toolbar, "Load System Presets",
                  self._on_load_presets,
                  bg=theme.bg4, fg=theme.btn_fg, font=btn_font,
                  padx=btn_pad, pady=5).pack(side="left", padx=(0, 4))

        _make_btn(toolbar, "Export",
                  self._on_export,
                  bg=theme.bg4, fg=theme.btn_fg, font=btn_font,
                  padx=btn_pad, pady=5).pack(side="right", padx=(0, 4))

        # ── Content area: stacked frames (manual tab switching) ──
        self._content_area = tk.Frame(self, bg=theme.bg)
        self._content_area.pack(fill="both", expand=True)

        self.process_panel = ProfileListPanel(self._content_area, t, "process", self)
        self.filament_panel = ProfileListPanel(self._content_area, t, "filament", self)

        # Show process panel by default
        self.process_panel.pack(fill="both", expand=True)
        self._current_tab = "process"

    def _switch_tab(self, tab_name):
        """Switch between Process and Filament tabs."""
        theme = self.theme
        if tab_name == self._current_tab:
            return
        if tab_name == "process":
            self.filament_panel.pack_forget()
            self.process_panel.pack(fill="both", expand=True)
            self._process_tab.configure(bg=theme.accent2, fg=theme.accent_fg,
                                         font=(UI_FONT, 13, "bold"))
            self._filament_tab.configure(bg=theme.bg4, fg=theme.btn_fg,
                                          font=(UI_FONT, 13))
        else:
            self.process_panel.pack_forget()
            self.filament_panel.pack(fill="both", expand=True)
            self._filament_tab.configure(bg=theme.accent2, fg=theme.accent_fg,
                                          font=(UI_FONT, 13, "bold"))
            self._process_tab.configure(bg=theme.bg4, fg=theme.btn_fg,
                                         font=(UI_FONT, 13))
        self._current_tab = tab_name

    def _active_panel(self):
        return self.process_panel if self._current_tab == "process" else self.filament_panel

    # ── Actions ──

    def _on_import(self):
        """Import profiles from .json files or extract from .3mf projects."""
        paths = filedialog.askopenfilenames(
            title="Import Profiles (JSON or .3mf)",
            filetypes=[("All supported", "*.json *.3mf"), ("JSON profiles", "*.json"),
                       ("3MF projects", "*.3mf"), ("All", "*.*")])
        if paths:
            self._load_files([(p, None, "") for p in paths])

    def _on_load_presets(self):
        """Load user presets from all detected slicers at once."""
        if not self.detected_slicers:
            messagebox.showinfo("No Slicers Found",
                                "No slicer installations were detected.\n\n"
                                "Supported: BambuStudio, OrcaSlicer, PrusaSlicer")
            return
        pairs = []
        for name, path in self.detected_slicers.items():
            presets = SlicerDetector.find_user_presets(path)
            for ptype, files in presets.items():
                for fp in files:
                    pairs.append((fp, ptype, name))  # include slicer name
        if not pairs:
            self._update_status("No user presets found in detected slicers.")
            return
        self._load_files(pairs)
        names = ", ".join(self.detected_slicers.keys())
        self._update_status(f"Loaded {len(pairs)} preset(s) from {names}.")

    def _on_clear_list(self):
        """Clear profiles from the active panel."""
        self._active_panel()._on_clear()

    def _load_files(self, path_hint_tuples):
        """Load files. Each entry is (path, type_hint) or (path, type_hint, origin)."""
        loaded_p, loaded_f, resolved_count, errors = 0, 0, 0, []
        all_new = []
        for item in path_hint_tuples:
            path = item[0]
            type_hint = item[1] if len(item) > 1 else None
            origin = item[2] if len(item) > 2 else ""
            try:
                profiles = ProfileEngine.load_file(path, type_hint)
                for profile in profiles:
                    if origin:
                        profile.origin = origin
                all_new.extend(profiles)
            except Exception as e:
                errors.append(f"{os.path.basename(path)}: {e}")

        # Add to index for cross-referencing, then resolve inheritance
        self.preset_index.add_profiles(all_new)
        for profile in all_new:
            if profile.inherits:
                self.preset_index.resolve(profile)
                if profile.resolved_data:
                    resolved_count += 1

        # Sort into panels
        for profile in all_new:
            if profile.profile_type == "process":
                self.process_panel.add_profiles([profile])
                loaded_p += 1
            elif profile.profile_type == "filament":
                self.filament_panel.add_profiles([profile])
                loaded_f += 1
            else:
                self.process_panel.add_profiles([profile])
                loaded_p += 1

        if errors:
            messagebox.showwarning("Some Files Failed",
                                   f"Loaded {loaded_p + loaded_f} profiles. Errors:\n\n" + "\n".join(errors))

        total = len(self.process_panel.profiles) + len(self.filament_panel.profiles)
        status = f"Loaded {loaded_p} process, {loaded_f} filament. {total} total."
        if resolved_count:
            status += f" Resolved inheritance for {resolved_count}."
        self._update_status(status)

    def _on_convert(self):
        panel = self._active_panel()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo("No Selection", "Select profiles to convert.")
            return
        dlg = ConvertDialog(self, self.theme, len(selected))
        if dlg.result is None:
            return
        for profile in selected:
            if dlg.result == "universal":
                profile.make_universal()
            else:
                profile.retarget(dlg.result)
        panel._refresh_list()
        panel._on_select()
        self._update_status(f"Converted {len(selected)} profile(s).")

    def _on_convert_all(self):
        panel = self._active_panel()
        all_profiles = panel.profiles
        if not all_profiles:
            messagebox.showinfo("No Profiles", "No profiles loaded to convert.")
            return
        dlg = ConvertDialog(self, self.theme, len(all_profiles))
        if dlg.result is None:
            return
        for profile in all_profiles:
            if dlg.result == "universal":
                profile.make_universal()
            else:
                profile.retarget(dlg.result)
        panel._refresh_list()
        panel._on_select()
        self._update_status(f"Converted all {len(all_profiles)} profile(s).")

    def _on_compare(self):
        panel = self._active_panel()
        selected = panel.get_selected_profiles()
        if len(selected) != 2:
            messagebox.showinfo("Select Two", "Select exactly 2 profiles to compare.")
            return
        CompareDialog(self, self.theme, selected[0], selected[1])

    def _on_export(self):
        # Commit any pending edits in the detail panel
        panel = self._active_panel()
        if hasattr(panel, 'detail'):
            panel.detail._commit_edits()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo("No Selection", "Select profiles to export.")
            return
        dlg = ExportDialog(self, self.theme, len(selected),
                           detected_slicers=self.detected_slicers)
        if dlg.result is None:
            return

        # Handle "Install to Slicer" from the export dialog
        if dlg.result == "slicer" and dlg.slicer_target:
            sname, spath = dlg.slicer_target
            self._on_install_to_slicer(sname, spath)
            return

        flatten = dlg.flatten

        if len(selected) == 1:
            # Single profile: save-as dialog with filename choice
            profile = selected[0]
            fp = filedialog.asksaveasfilename(
                title="Export Profile",
                initialfile=profile.suggested_filename(),
                defaultextension=".json",
                filetypes=[("JSON profile", "*.json"), ("All", "*.*")])
            if fp:
                try:
                    with open(fp, "w", encoding="utf-8") as f:
                        f.write(profile.to_json(flatten=flatten))
                    mode_note = " (flattened)" if flatten else ""
                    self._update_status(f"Exported{mode_note}: {os.path.basename(fp)}")
                except Exception as e:
                    messagebox.showerror("Export Error", str(e))
        else:
            # Multiple profiles: choose directory, then each gets a save-as dialog
            out = filedialog.askdirectory(title="Choose Export Directory")
            if out:
                self._do_export(selected, out, flatten=flatten)

    def _on_export_to_slicer(self, name, path):
        panel = self._active_panel()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo("No Selection", "Select profiles to export.")
            return
        base = SlicerDetector.get_export_dir(path)
        if messagebox.askyesno("Export", f"Export {len(selected)} to {name}?\n{base}"):
            self._do_export(selected, base, organize=True)

    def _on_install_to_slicer(self, slicer_name, slicer_path):
        """Install selected profiles directly into a slicer's user preset directory."""
        panel = self._active_panel()
        if hasattr(panel, 'detail'):
            panel.detail._commit_edits()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo("No Selection", "Select profiles to install.")
            return

        export_base = SlicerDetector.get_export_dir(slicer_path)
        count = len(selected)
        profiles_word = "profile" if count == 1 else "profiles"

        # Build a descriptive summary for the confirmation
        names = [profile.name for profile in selected[:3]]
        summary = ", ".join(names)
        if count > 3:
            summary += f", and {count - 3} more"

        if not messagebox.askyesno(
                f"Install to {slicer_name}",
                f"Install {count} {profiles_word} to {slicer_name}?\n\n"
                f"{summary}\n\n"
                f"Destination: {export_base}\n\n"
                f"Profiles will be organized into subfolders by type\n"
                f"(process/, filament/) and will appear in {slicer_name}\n"
                f"after restarting it."):
            return

        self._do_export(selected, export_base, organize=True, quiet=True)
        msg = (f"Installed {count} {profiles_word} to {slicer_name}. "
               f"Restart {slicer_name} to see them.")
        self._update_status(msg)
        messagebox.showinfo(f"Installed to {slicer_name}", msg)

    def _do_export(self, profiles, out_dir, organize=False, flatten=False, quiet=False):
        exported, errors = 0, []
        for profile in profiles:
            try:
                dest_dir = (os.path.join(out_dir, profile.profile_type)
                     if organize and profile.profile_type != "unknown" else out_dir)
                os.makedirs(dest_dir, exist_ok=True)
                fp = os.path.join(dest_dir, profile.suggested_filename())
                counter = 1
                base, ext = os.path.splitext(fp)
                while os.path.exists(fp):
                    fp = f"{base}_{counter}{ext}"
                    counter += 1
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(profile.to_json(flatten=flatten))
                exported += 1
            except Exception as e:
                errors.append(f"{profile.name}: {e}")
        if errors:
            messagebox.showwarning("Partial Export",
                                   f"Exported {exported}, errors:\n\n" + "\n".join(errors))
        elif not quiet:
            messagebox.showinfo("Export Complete", f"Exported {exported} profile(s) to:\n{out_dir}")
        if not quiet:
            mode_note = " (flattened, no inheritance)" if flatten else ""
            self._update_status(f"Exported {exported} profile(s){mode_note}.")

    def _on_remove(self):
        self._active_panel().remove_selected()

    def _on_create_from_profile(self):
        """Create a new profile based on the selected one."""
        panel = self._active_panel()
        selected = panel.get_selected_profiles()
        if len(selected) != 1:
            messagebox.showinfo("Select One", "Select exactly 1 profile to create from.")
            return
        source = selected[0]
        # Ask user for a name
        dlg = tk.Toplevel(self)
        dlg.title("Create from Profile")
        dlg.configure(bg=self.theme.bg)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        dlg.geometry("+%d+%d" % (self.winfo_rootx() + 120, self.winfo_rooty() + 120))

        theme = self.theme
        tk.Label(dlg, text="New profile name:", bg=theme.bg, fg=theme.fg,
                 font=(UI_FONT, 11)).pack(padx=16, pady=(12, 4), anchor="w")
        name_var = tk.StringVar(value=f"{source.name} (copy)")
        entry = tk.Entry(dlg, textvariable=name_var, bg=theme.bg3, fg=theme.fg,
                         font=(UI_FONT, 12), insertbackground=theme.fg,
                         highlightbackground=theme.accent, highlightthickness=1,
                         width=40)
        entry.pack(padx=16, pady=(0, 8))
        entry.select_range(0, "end")
        entry.focus_set()

        result = {"name": None}

        def on_ok(event=None):
            n = name_var.get().strip()
            if n:
                result["name"] = n
                dlg.destroy()

        def on_cancel(event=None):
            dlg.destroy()

        btn_row = tk.Frame(dlg, bg=theme.bg)
        btn_row.pack(fill="x", padx=16, pady=(0, 12))
        _make_btn(btn_row, "Create", on_ok,
                  bg=theme.accent2, fg=theme.accent_fg,
                  font=(UI_FONT, 10, "bold"), padx=12, pady=4).pack(side="right")
        _make_btn(btn_row, "Cancel", on_cancel,
                  bg=theme.bg4, fg=theme.btn_fg,
                  font=(UI_FONT, 10), padx=8, pady=4).pack(side="right", padx=(0, 4))

        entry.bind("<Return>", on_ok)
        entry.bind("<Escape>", on_cancel)
        dlg.wait_window()

        if result["name"]:
            # Deep copy the source profile's data
            new_data = deepcopy(source.resolved_data if source.resolved_data else source.data)
            new_data["name"] = result["name"]
            # Remove identity keys that tie it to the original
            for k in ("setting_id", "updated_time", "user_id", "instantiation"):
                new_data.pop(k, None)
            new_profile = Profile(new_data, source.source_path, source.source_type,
                                  type_hint=source.type_hint, origin=source.origin)
            panel.add_profiles([new_profile])
            self._update_status(f"Created '{result['name']}' from '{source.name}'.")

    def _on_select_all(self):
        self._active_panel().select_all()

    def _on_about(self):
        messagebox.showinfo("About",
                            f"{APP_NAME} v{APP_VERSION}\n\n"
                            "Removes artificial printer-compatibility restrictions\n"
                            "from 3D printer slicer profiles.\n\n"
                            "Mirrors BambuStudio's settings layout.\n"
                            "Supports BambuStudio, OrcaSlicer, PrusaSlicer.")

    def _update_status(self, msg=""):
        if msg:
            self.status_var.set(f"[{datetime.now().strftime('%H:%M:%S')}]  {msg}")
        np = len(self.process_panel.profiles)
        nf = len(self.filament_panel.profiles)
        self._count_var.set(f"{np} process, {nf} filament")

    def _on_show_folder(self):
        """Open the source folder of the currently selected profile."""
        panel = self._active_panel()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo("No Selection", "Select a profile to show its folder.")
            return
        profile = selected[0]
        folder = os.path.dirname(profile.source_path)
        if os.path.isdir(folder):
            if platform.system() == "Darwin":
                subprocess.Popen(["open", folder])
            elif platform.system() == "Windows":
                subprocess.Popen(["explorer", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        else:
            messagebox.showinfo("Folder Not Found",
                                f"Source folder not found:\n{folder}")


# --- Entry Point ---
if __name__ == "__main__":
    app = App()
    app.mainloop()
