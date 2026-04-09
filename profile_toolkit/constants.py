# Layout definitions, enum maps, recommendation ranges, named constants

import platform
import re


# --- Application & Platform Identification ---

APP_NAME = "Profile Toolkit"
APP_VERSION = "2.2.0"

# Cross-platform UI font family
_PLATFORM = platform.system()
if _PLATFORM == "Darwin":
    UI_FONT = "SF Pro"          # San Francisco (macOS 10.11+)
elif _PLATFORM == "Windows":
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
_TOOLTIP_BORDER_COLOR = "#4A4A51"  # _Tooltip border — blue-gray (Orca-aligned)
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
HTTP_USER_AGENT = "Mozilla/5.0 (compatible; ProfileToolkit/2.2.0)"


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
        # Reserved — BambuStudio has this tab but no parameters are defined yet.
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
del _tab_sections, _params, _key, _label

# Identity/meta keys: profile bookkeeping fields shown in the header,
# not as editable parameters. Excluded from tab layout and diff views.
# Criteria: keys that identify or version the profile itself, rather than
# describe printer/filament settings. Add new keys here if they should
# never appear in the parameter tabs or diff comparisons.
_IDENTITY_KEYS = {
    "name", "type", "inherits", "from", "setting_id",
    "compatible_printers", "compatible_printers_condition",
    "printer_settings_id", "version", "is_custom_defined",
    "instantiation", "user_id", "updated_time",
}

# Keys that strongly indicate a filament profile
_FILAMENT_SIGNAL_KEYS = frozenset({
    "filament_type", "nozzle_temperature", "filament_flow_ratio",
    "fan_min_speed", "fan_max_speed", "filament_retraction_length",
    "nozzle_temperature_initial_layer", "cool_plate_temp", "hot_plate_temp",
    "filament_max_volumetric_speed", "filament_density", "filament_colour",
    "filament_vendor", "filament_cost",
})

# Keys that strongly indicate a process/print profile
_PROCESS_SIGNAL_KEYS = frozenset({
    "layer_height", "wall_loops", "sparse_infill_density",
    "support_type", "print_speed",
})

# Keys that identify any profile data (either type)
_PROFILE_SIGNAL_KEYS = _FILAMENT_SIGNAL_KEYS | _PROCESS_SIGNAL_KEYS | frozenset({
    "compatible_printers", "inherits", "from",
})

# --- Smart Recommendations Knowledge Base ---
# Static knowledge base of recommended ranges per material.
# Structure: RECOMMENDATIONS[json_key] = {
#   "info": str,   # general info text for the ⓘ popup (material-independent)
#   "ranges": {material: {"min": float, "max": float, "typical": float, "notes": str}, ...}
# }
# Materials: PLA, PETG, ABS, ASA, TPU, PA, PC, PLA-CF, PETG-CF, PA-CF
# "General" is the fallback when material is unknown.

RECOMMENDATIONS = {
    # ── Quality Tab ──
    "layer_height": {
        "info": "Layer height controls detail vs speed tradeoff. Thicker layers = stronger parts (more bonding area), thinner = more detail. Speed relationship: Speed (mm/s) = Volumetric Flow / layer_height / line_width.",
        "sources": [
            {"label": "Sloyd.ai Layer Height Guide", "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide"},
            {"label": "Ellis3DP Max Volumetric Flow", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/determining_max_volumetric_flow_rate.html"},
            {"label": "Prusa Composite Materials", "url": "https://help.prusa3d.com/article/composite-materials-filled-with-carbon-kevlar-or-glass_167387"},
            {"label": "Simplify3D CF Guide", "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/"},
        ],
        "ranges": {
            "PLA":     {"min": 0.1, "max": 0.3, "typical": 0.2, "notes": "Lower for detail, higher for speed", "sources": [{"label": "Sloyd.ai Layer Height Guide", "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide"}]},
            "PETG":    {"min": 0.1, "max": 0.3, "typical": 0.2, "sources": [{"label": "Sloyd.ai Layer Height Guide", "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide"}]},
            "ABS":     {"min": 0.2, "max": 0.3, "typical": 0.2, "sources": [{"label": "Sloyd.ai Layer Height Guide", "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide"}]},
            "TPU":     {"min": 0.2, "max": 0.3, "typical": 0.2, "notes": "0.05 mm possible for fine details", "sources": [{"label": "Sloyd.ai Layer Height Guide", "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide"}]},
            "PA":      {"min": 0.2, "max": 0.4, "typical": 0.2, "notes": "Broader range reduces warping", "sources": [{"label": "Sloyd.ai Layer Height Guide", "url": "https://www.sloyd.ai/blog/material-specific-layer-height-settings-guide"}]},
            "PC":      {"min": 0.2, "max": 0.3, "typical": 0.2},
            "PLA-CF":  {"min": 0.2, "max": 0.3, "typical": 0.2, "notes": "Minimum 0.2 mm to reduce clogging", "sources": [{"label": "Prusa Composite Materials", "url": "https://help.prusa3d.com/article/composite-materials-filled-with-carbon-kevlar-or-glass_167387"}, {"label": "Simplify3D CF Guide", "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/"}]},
            "PETG-CF": {"min": 0.2, "max": 0.3, "typical": 0.2, "notes": "Minimum 0.2 mm to reduce clogging", "sources": [{"label": "Prusa Composite Materials", "url": "https://help.prusa3d.com/article/composite-materials-filled-with-carbon-kevlar-or-glass_167387"}, {"label": "Simplify3D CF Guide", "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/"}]},
            "PA-CF":   {"min": 0.2, "max": 0.3, "typical": 0.2, "notes": "Minimum 0.2 mm to reduce clogging", "sources": [{"label": "Prusa Composite Materials", "url": "https://help.prusa3d.com/article/composite-materials-filled-with-carbon-kevlar-or-glass_167387"}, {"label": "Simplify3D CF Guide", "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/"}]},
            "General": {"min": 0.1, "max": 0.3, "typical": 0.2},
        },
    },
    "initial_layer_print_height": {
        "info": "First layer height. Thicker first layers are less sensitive to bed leveling errors. Ellis3DP recommends ≥0.25 mm, especially on larger printers.",
        "sources": [
            {"label": "Ellis3DP First Layer Squish", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/first_layer_squish.html"},
        ],
        "ranges": {
            "General": {"min": 0.2, "max": 0.35, "typical": 0.28},
        },
    },
    "line_width": {
        "info": "Standard: match nozzle diameter (0.4 mm for 0.4 mm nozzle). Misconception: two 0.4 mm perimeters ≠ 0.8 mm wall. Actual Slic3r formula: spacing = width − layer_height × (1 − π/4).",
        "sources": [
            {"label": "Ellis3DP Misconceptions", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html"},
        ],
        "ranges": {
            "General": {"min": 0.35, "max": 0.55, "typical": 0.42},
        },
    },
    "initial_layer_line_width": {
        "info": "Set to ≥120% of nozzle diameter for first layer. Wider first layer improves bed adhesion.",
        "sources": [
            {"label": "Ellis3DP First Layer Squish", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/first_layer_squish.html"},
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
            {"label": "Ellis3DP Misconceptions", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html"},
        ],
        "ranges": {
            "General": {"min": -0.2, "max": 0.2, "typical": 0.0},
        },
    },

    # ── Strength Tab ──
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
    "sparse_infill_density": {
        "info": "10–20% for decorative parts, 20–40% general use, 50%+ structural. PC: >25% recommended for small/medium objects.",
        "ranges": {
            "PLA":     {"min": 10, "max": 60, "typical": 20},
            "PETG":    {"min": 10, "max": 60, "typical": 20},
            "ABS":     {"min": 15, "max": 60, "typical": 25},
            "PC":      {"min": 25, "max": 60, "typical": 30, "notes": ">25% recommended for small/medium objects", "sources": [{"label": "Prusa Polycarbonate", "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812"}]},
            "General": {"min": 10, "max": 60, "typical": 20},
        },
    },

    # ── Speed Tab ──
    "initial_layer_speed": {
        "info": "Typically 50–70% of normal print speed. Slower = better adhesion. Too slow on some materials (PETG) can cause elephant's foot.",
        "ranges": {
            "General": {"min": 20, "max": 60, "typical": 40},
        },
    },
    "outer_wall_speed": {
        "info": "Outer wall speed is the primary quality-affecting speed parameter. Material-dependent — TPU needs very slow speeds.",
        "sources": [
            {"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"},
            {"label": "Sovol3D Temp Guide 2026", "url": "https://www.sovol3d.com/blogs/news/3d-print-nozzle-temperature-guide-for-materials-2026"},
            {"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"},
            {"label": "All3DP PETG Settings", "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/"},
            {"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"},
            {"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"},
            {"label": "All3DP ASA", "url": "https://all3dp.com/2/3d-printing-asa/"},
            {"label": "Overture TPU Guide", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"},
            {"label": "Prusa Flexible Materials", "url": "https://help.prusa3d.com/article/flexible-materials_2057"},
            {"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"},
            {"label": "All3DP Printing Temperatures", "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/"},
            {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"},
            {"label": "Simplify3D Carbon Fiber Guide", "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/"},
        ],
        "ranges": {
            "PLA":     {"min": 50,  "max": 200, "typical": 70, "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}, {"label": "Sovol3D Temp Guide 2026", "url": "https://www.sovol3d.com/blogs/news/3d-print-nozzle-temperature-guide-for-materials-2026"}]},
            "PETG":    {"min": 40,  "max": 100, "typical": 55, "sources": [{"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"}, {"label": "All3DP PETG Settings", "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/"}]},
            "ABS":     {"min": 40,  "max": 200, "typical": 55, "sources": [{"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"}, {"label": "Sovol3D Temp Guide 2026", "url": "https://www.sovol3d.com/blogs/news/3d-print-nozzle-temperature-guide-for-materials-2026"}]},
            "ASA":     {"min": 30,  "max": 200, "typical": 50, "sources": [{"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"}, {"label": "All3DP ASA", "url": "https://all3dp.com/2/3d-printing-asa/"}]},
            "TPU":     {"min": 15,  "max": 40,  "typical": 25, "notes": "CRITICAL: slow speeds mandatory", "sources": [{"label": "Overture TPU Guide", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"}, {"label": "Prusa Flexible Materials", "url": "https://help.prusa3d.com/article/flexible-materials_2057"}]},
            "PA":      {"min": 25,  "max": 60,  "typical": 45, "sources": [{"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"}, {"label": "All3DP Printing Temperatures", "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/"}]},
            "PC":      {"min": 20,  "max": 200, "typical": 40, "sources": [{"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"}, {"label": "Sovol3D Temp Guide 2026", "url": "https://www.sovol3d.com/blogs/news/3d-print-nozzle-temperature-guide-for-materials-2026"}]},
            "PLA-CF":  {"min": 25,  "max": 60,  "typical": 40, "notes": "25–50% slower than base PLA", "sources": [{"label": "Simplify3D Carbon Fiber Guide", "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/"}]},
            "General": {"min": 30,  "max": 200, "typical": 60},
        },
    },
    "inner_wall_speed": {
        "info": "Can typically be 25–50% faster than outer wall speed since not visible. Same material constraints apply.",
        "ranges": {
            "TPU":     {"min": 20,  "max": 50,  "typical": 35},
            "General": {"min": 50,  "max": 300, "typical": 100},
        },
    },
    "sparse_infill_speed": {
        "info": "Can be fastest print move (not visible). Limited by max volumetric speed of hotend, not quality. Speed = volumetric_flow / layer_height / line_width.",
        "sources": [
            {"label": "Ellis3DP Max Volumetric Flow", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/determining_max_volumetric_flow_rate.html"},
        ],
        "ranges": {
            "TPU":     {"min": 20,  "max": 50,  "typical": 30},
            "General": {"min": 50,  "max": 300, "typical": 150},
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
            "TPU":     {"min": 100, "max": 150, "typical": 120},
            "General": {"min": 120, "max": 300, "typical": 200},
        },
    },
    "default_acceleration": {
        "info": "Tune accelerations FIRST, then speeds (Ellis3DP). Apply ~15% safety margin below tested maximums. Common ranges 500–5000 mm/s², tested up to 10000.",
        "sources": [
            {"label": "Ellis3DP Max Speeds & Accelerations", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/determining_max_speeds_accels.html"},
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

    # ── Support Tab ──
    "support_threshold_angle": {
        "info": "Angle from vertical below which supports generate. 45° is a common default. Material-dependent: PLA handles steeper overhangs better with cooling.",
        "ranges": {
            "General": {"min": 30, "max": 60, "typical": 45},
        },
    },
    "support_top_z_distance": {
        "info": "Standard: 1 layer height. Water-soluble supports (PVA/BVOH): 0 mm for perfect interface. TPU supports: 0.3 mm Z-spacing.",
        "ranges": {
            "TPU":     {"min": 0.2, "max": 0.4, "typical": 0.3, "notes": "0.3 mm Z-spacing recommended", "sources": [{"label": "Prusa Prusament TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"}]},
            "General": {"min": 0.1, "max": 0.3, "typical": 0.2, "sources": [{"label": "Prusa Water-Soluble (PVA/BVOH)", "url": "https://help.prusa3d.com/article/water-soluble-bvoh-pva_167012"}]},
        },
    },

    # ── Others Tab ──
    "brim_width": {
        "info": "HIPS: recommended for small contact areas. PP: 5–10 mm depending on model size. ABS/ASA: helps with warping on unenclosed printers.",
        "ranges": {
            "ABS":     {"min": 3, "max": 10, "typical": 5, "notes": "Helps with warping"},
            "ASA":     {"min": 3, "max": 10, "typical": 5, "notes": "Helps with warping"},
            "PP":      {"min": 5, "max": 10, "typical": 8, "notes": "Needed for adhesion", "sources": [{"label": "Prusa Polypropylene", "url": "https://help.prusa3d.com/article/polypropylene-pp_167126"}]},
            "General": {"min": 0, "max": 10, "typical": 3},
        },
    },

    # ── Filament Parameters ──
    "filament_flow_ratio": {
        "info": "Starting range: 0.92–0.98 for most filaments. Tune for perfect TOP SURFACE appearance, NOT dimensional accuracy. If uncertain between two values, pick the higher one. Must be tuned per filament brand/type minimum.",
        "sources": [
            {"label": "Ellis3DP Extrusion Multiplier", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/extrusion_multiplier.html"},
            {"label": "Ellis3DP Misconceptions", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html"},
        ],
        "ranges": {
            "General": {"min": 0.9, "max": 1.0, "typical": 0.96},
        },
    },
    "nozzle_temperature": {
        "info": "Hotter = better layer adhesion but more stringing/oozing. All-metal hotend required above ~240°C. Temperature tuning: adjust 5°C at a time.",
        "sources": [
            {"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"},
            {"label": "Prusa PLA", "url": "https://help.prusa3d.com/article/pla_2062"},
            {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"},
            {"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"},
            {"label": "Prusa PETG", "url": "https://help.prusa3d.com/article/petg_2059"},
            {"label": "MatterHackers PETG", "url": "https://www.matterhackers.com/news/how-to-succeed-when-printing-with-petg-filament"},
            {"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"},
            {"label": "Prusa ABS", "url": "https://help.prusa3d.com/article/abs_2058"},
            {"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"},
            {"label": "Prusa ASA", "url": "https://help.prusa3d.com/article/asa_1809"},
            {"label": "All3DP ASA", "url": "https://all3dp.com/2/3d-printing-asa/"},
            {"label": "Prusa Prusament TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"},
            {"label": "Overture TPU Guide", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"},
            {"label": "Prusa Polyamide", "url": "https://help.prusa3d.com/article/polyamide-nylon_167188"},
            {"label": "All3DP Temps", "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/"},
            {"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"},
            {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"},
            {"label": "Prusa PC", "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812"},
            {"label": "Nobufil PLA-CF Guide", "url": "https://www.nobufil.com/en/post/3d-printing-with-pla-cf-filament"},
            {"label": "Simplify3D CF Guide", "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/"},
            {"label": "Prusa HIPS", "url": "https://help.prusa3d.com/article/hips_167118"},
            {"label": "Prusa PVB", "url": "https://help.prusa3d.com/article/pvb_196708"},
            {"label": "Prusa Water-Soluble (PVA/BVOH)", "url": "https://help.prusa3d.com/article/water-soluble-bvoh-pva_167012"},
            {"label": "Prusa CPE", "url": "https://help.prusa3d.com/article/cpe_166877"},
            {"label": "Prusa Polypropylene", "url": "https://help.prusa3d.com/article/polypropylene-pp_167126"},
            {"label": "colorFabb LW-PLA Guide", "url": "https://colorfabb.com/blog/post/how-to-print-with-colorfabb-lw-pla"},
            {"label": "colorFabb XT Guide", "url": "https://colorfabb.com/blog/post/how-to-print-with-colorfabb_xt"},
            {"label": "colorFabb HT Guide", "url": "https://colorfabb.com/blog/post/how-to-print-with-colorfabb_ht"},
            {"label": "eSUN PLA+ TDS", "url": "https://www.esun3d.com/uploads/eSUN_PLA+-Filament_TDS_V4.0.pdf"},
            {"label": "Teaching Tech Calibration", "url": "https://teachingtechyt.github.io/calibration.html"},
            {"label": "Obico OrcaSlicer Calibration", "url": "https://www.obico.io/blog/orcaslicer-comprehensive-calibration-guide/"},
        ],
        "ranges": {
            "PLA":     {"min": 190, "max": 230, "typical": 210, "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}, {"label": "Prusa PLA", "url": "https://help.prusa3d.com/article/pla_2062"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "PETG":    {"min": 220, "max": 260, "typical": 240, "sources": [{"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"}, {"label": "Prusa PETG", "url": "https://help.prusa3d.com/article/petg_2059"}, {"label": "MatterHackers PETG", "url": "https://www.matterhackers.com/news/how-to-succeed-when-printing-with-petg-filament"}]},
            "ABS":     {"min": 220, "max": 270, "typical": 250, "sources": [{"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"}, {"label": "Prusa ABS", "url": "https://help.prusa3d.com/article/abs_2058"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "ASA":     {"min": 230, "max": 270, "typical": 255, "sources": [{"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"}, {"label": "Prusa ASA", "url": "https://help.prusa3d.com/article/asa_1809"}, {"label": "All3DP ASA", "url": "https://all3dp.com/2/3d-printing-asa/"}]},
            "TPU":     {"min": 210, "max": 250, "typical": 228, "sources": [{"label": "Prusa Prusament TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"}, {"label": "Overture TPU Guide", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "PA":      {"min": 240, "max": 300, "typical": 270, "sources": [{"label": "Prusa Polyamide", "url": "https://help.prusa3d.com/article/polyamide-nylon_167188"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}, {"label": "All3DP Temps", "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/"}]},
            "PC":      {"min": 250, "max": 310, "typical": 275, "sources": [{"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"}, {"label": "Prusa PC", "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "PLA-CF":  {"min": 200, "max": 240, "typical": 225, "notes": "Base +10–20°C", "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}, {"label": "Nobufil PLA-CF Guide", "url": "https://www.nobufil.com/en/post/3d-printing-with-pla-cf-filament"}, {"label": "Simplify3D CF Guide", "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/"}]},
            "PETG-CF": {"min": 240, "max": 270, "typical": 250, "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}]},
            "PA-CF":   {"min": 260, "max": 300, "typical": 280, "sources": [{"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"}]},
            "General": {"min": 190, "max": 310, "typical": 230},
        },
    },
    "nozzle_temperature_initial_layer": {
        "info": "Typically same as nozzle temp or 5°C higher for adhesion. Prusa PLA: 215°C first layer. Some filaments benefit from slightly lower first layer temp to reduce elephant's foot.",
        "ranges": {
            "PLA":     {"min": 195, "max": 235, "typical": 215},
            "PETG":    {"min": 225, "max": 260, "typical": 240},
            "ABS":     {"min": 225, "max": 275, "typical": 255},
            "ASA":     {"min": 235, "max": 270, "typical": 260},
            "TPU":     {"min": 215, "max": 255, "typical": 230},
            "PA":      {"min": 245, "max": 305, "typical": 275},
            "PC":      {"min": 255, "max": 315, "typical": 280},
            "General": {"min": 195, "max": 315, "typical": 235},
        },
    },
    "cool_plate_temp": {
        "info": "Bed temperature for Cool Plate (other layers). Material-dependent — ABS/ASA need high bed temps for adhesion without warping.",
        "sources": [
            {"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"},
            {"label": "Prusa PLA", "url": "https://help.prusa3d.com/article/pla_2062"},
            {"label": "Hatchbox Guides", "url": "https://www.hatchbox3d.com/pages/guides"},
            {"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"},
            {"label": "Prusa PETG", "url": "https://help.prusa3d.com/article/petg_2059"},
            {"label": "All3DP PETG", "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/"},
            {"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"},
            {"label": "Prusa ABS", "url": "https://help.prusa3d.com/article/abs_2058"},
            {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"},
            {"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"},
            {"label": "Prusa ASA", "url": "https://help.prusa3d.com/article/asa_1809"},
            {"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"},
            {"label": "Prusa Prusament TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"},
            {"label": "Overture TPU", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"},
            {"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"},
            {"label": "Prusa Polyamide", "url": "https://help.prusa3d.com/article/polyamide-nylon_167188"},
            {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"},
            {"label": "Prusa PC", "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812"},
            {"label": "Prusa HIPS", "url": "https://help.prusa3d.com/article/hips_167118"},
            {"label": "Prusa PVB", "url": "https://help.prusa3d.com/article/pvb_196708"},
            {"label": "Prusa Water-Soluble", "url": "https://help.prusa3d.com/article/water-soluble-bvoh-pva_167012"},
            {"label": "Prusa CPE", "url": "https://help.prusa3d.com/article/cpe_166877"},
            {"label": "Prusa Polypropylene", "url": "https://help.prusa3d.com/article/polypropylene-pp_167126"},
            {"label": "colorFabb XT Guide", "url": "https://colorfabb.com/blog/post/how-to-print-with-colorfabb_xt"},
            {"label": "colorFabb HT Guide", "url": "https://colorfabb.com/blog/post/how-to-print-with-colorfabb_ht"},
            {"label": "eSUN PLA+ TDS", "url": "https://www.esun3d.com/uploads/eSUN_PLA+-Filament_TDS_V4.0.pdf"},
        ],
        "ranges": {
            "PLA":     {"min": 25,  "max": 65,  "typical": 58, "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}, {"label": "Prusa PLA", "url": "https://help.prusa3d.com/article/pla_2062"}, {"label": "Hatchbox Guides", "url": "https://www.hatchbox3d.com/pages/guides"}]},
            "PETG":    {"min": 60,  "max": 90,  "typical": 80, "sources": [{"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"}, {"label": "Prusa PETG", "url": "https://help.prusa3d.com/article/petg_2059"}, {"label": "All3DP PETG", "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/"}]},
            "ABS":     {"min": 80,  "max": 110, "typical": 100, "sources": [{"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"}, {"label": "Prusa ABS", "url": "https://help.prusa3d.com/article/abs_2058"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "ASA":     {"min": 75,  "max": 110, "typical": 105, "sources": [{"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"}, {"label": "Prusa ASA", "url": "https://help.prusa3d.com/article/asa_1809"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "TPU":     {"min": 25,  "max": 75,  "typical": 50, "sources": [{"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"}, {"label": "Prusa Prusament TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"}, {"label": "Overture TPU", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"}]},
            "PA":      {"min": 25,  "max": 110, "typical": 90, "sources": [{"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"}, {"label": "Prusa Polyamide", "url": "https://help.prusa3d.com/article/polyamide-nylon_167188"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "PC":      {"min": 90,  "max": 150, "typical": 115, "sources": [{"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"}, {"label": "Prusa PC", "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "General": {"min": 25,  "max": 150, "typical": 60},
        },
    },
    "hot_plate_temp": {
        "info": "Bed temperature for Smooth PEI / High Temp Plate (other layers).",
        "sources": [
            {"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"},
            {"label": "Prusa PLA", "url": "https://help.prusa3d.com/article/pla_2062"},
            {"label": "Hatchbox Guides", "url": "https://www.hatchbox3d.com/pages/guides"},
            {"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"},
            {"label": "Prusa PETG", "url": "https://help.prusa3d.com/article/petg_2059"},
            {"label": "All3DP PETG", "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/"},
            {"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"},
            {"label": "Prusa ABS", "url": "https://help.prusa3d.com/article/abs_2058"},
            {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"},
            {"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"},
            {"label": "Prusa ASA", "url": "https://help.prusa3d.com/article/asa_1809"},
            {"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"},
            {"label": "Prusa Prusament TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"},
            {"label": "Overture TPU", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"},
            {"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"},
            {"label": "Prusa Polyamide", "url": "https://help.prusa3d.com/article/polyamide-nylon_167188"},
            {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"},
            {"label": "Prusa PC", "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812"},
            {"label": "Prusa HIPS", "url": "https://help.prusa3d.com/article/hips_167118"},
            {"label": "Prusa PVB", "url": "https://help.prusa3d.com/article/pvb_196708"},
            {"label": "Prusa Water-Soluble", "url": "https://help.prusa3d.com/article/water-soluble-bvoh-pva_167012"},
            {"label": "Prusa CPE", "url": "https://help.prusa3d.com/article/cpe_166877"},
            {"label": "Prusa Polypropylene", "url": "https://help.prusa3d.com/article/polypropylene-pp_167126"},
            {"label": "colorFabb XT Guide", "url": "https://colorfabb.com/blog/post/how-to-print-with-colorfabb_xt"},
            {"label": "colorFabb HT Guide", "url": "https://colorfabb.com/blog/post/how-to-print-with-colorfabb_ht"},
            {"label": "eSUN PLA+ TDS", "url": "https://www.esun3d.com/uploads/eSUN_PLA+-Filament_TDS_V4.0.pdf"},
        ],
        "ranges": {
            "PLA":     {"min": 25,  "max": 65,  "typical": 58, "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}, {"label": "Prusa PLA", "url": "https://help.prusa3d.com/article/pla_2062"}, {"label": "Hatchbox Guides", "url": "https://www.hatchbox3d.com/pages/guides"}]},
            "PETG":    {"min": 60,  "max": 90,  "typical": 80, "sources": [{"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"}, {"label": "Prusa PETG", "url": "https://help.prusa3d.com/article/petg_2059"}, {"label": "All3DP PETG", "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/"}]},
            "ABS":     {"min": 80,  "max": 110, "typical": 100, "sources": [{"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"}, {"label": "Prusa ABS", "url": "https://help.prusa3d.com/article/abs_2058"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "ASA":     {"min": 75,  "max": 110, "typical": 105, "sources": [{"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"}, {"label": "Prusa ASA", "url": "https://help.prusa3d.com/article/asa_1809"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "TPU":     {"min": 25,  "max": 75,  "typical": 50, "sources": [{"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"}, {"label": "Prusa Prusament TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"}, {"label": "Overture TPU", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"}]},
            "PA":      {"min": 25,  "max": 110, "typical": 90, "sources": [{"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"}, {"label": "Prusa Polyamide", "url": "https://help.prusa3d.com/article/polyamide-nylon_167188"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "PC":      {"min": 90,  "max": 150, "typical": 115, "sources": [{"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"}, {"label": "Prusa PC", "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "General": {"min": 25,  "max": 150, "typical": 60},
        },
    },
    "textured_plate_temp": {
        "info": "Bed temperature for Textured PEI Plate (other layers).",
        "sources": [
            {"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"},
            {"label": "Prusa PLA", "url": "https://help.prusa3d.com/article/pla_2062"},
            {"label": "Hatchbox Guides", "url": "https://www.hatchbox3d.com/pages/guides"},
            {"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"},
            {"label": "Prusa PETG", "url": "https://help.prusa3d.com/article/petg_2059"},
            {"label": "All3DP PETG", "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/"},
            {"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"},
            {"label": "Prusa ABS", "url": "https://help.prusa3d.com/article/abs_2058"},
            {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"},
            {"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"},
            {"label": "Prusa ASA", "url": "https://help.prusa3d.com/article/asa_1809"},
            {"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"},
            {"label": "Prusa Prusament TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"},
            {"label": "Overture TPU", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"},
            {"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"},
            {"label": "Prusa Polyamide", "url": "https://help.prusa3d.com/article/polyamide-nylon_167188"},
            {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"},
            {"label": "Prusa PC", "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812"},
            {"label": "Prusa HIPS", "url": "https://help.prusa3d.com/article/hips_167118"},
            {"label": "Prusa PVB", "url": "https://help.prusa3d.com/article/pvb_196708"},
            {"label": "Prusa Water-Soluble", "url": "https://help.prusa3d.com/article/water-soluble-bvoh-pva_167012"},
            {"label": "Prusa CPE", "url": "https://help.prusa3d.com/article/cpe_166877"},
            {"label": "Prusa Polypropylene", "url": "https://help.prusa3d.com/article/polypropylene-pp_167126"},
            {"label": "colorFabb XT Guide", "url": "https://colorfabb.com/blog/post/how-to-print-with-colorfabb_xt"},
            {"label": "colorFabb HT Guide", "url": "https://colorfabb.com/blog/post/how-to-print-with-colorfabb_ht"},
            {"label": "eSUN PLA+ TDS", "url": "https://www.esun3d.com/uploads/eSUN_PLA+-Filament_TDS_V4.0.pdf"},
        ],
        "ranges": {
            "PLA":     {"min": 25,  "max": 65,  "typical": 58, "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}, {"label": "Prusa PLA", "url": "https://help.prusa3d.com/article/pla_2062"}, {"label": "Hatchbox Guides", "url": "https://www.hatchbox3d.com/pages/guides"}]},
            "PETG":    {"min": 60,  "max": 90,  "typical": 80, "sources": [{"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"}, {"label": "Prusa PETG", "url": "https://help.prusa3d.com/article/petg_2059"}, {"label": "All3DP PETG", "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/"}]},
            "ABS":     {"min": 80,  "max": 110, "typical": 100, "sources": [{"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"}, {"label": "Prusa ABS", "url": "https://help.prusa3d.com/article/abs_2058"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "ASA":     {"min": 75,  "max": 110, "typical": 105, "sources": [{"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"}, {"label": "Prusa ASA", "url": "https://help.prusa3d.com/article/asa_1809"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "TPU":     {"min": 25,  "max": 75,  "typical": 50, "sources": [{"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"}, {"label": "Prusa Prusament TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"}, {"label": "Overture TPU", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"}]},
            "PA":      {"min": 25,  "max": 110, "typical": 90, "sources": [{"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"}, {"label": "Prusa Polyamide", "url": "https://help.prusa3d.com/article/polyamide-nylon_167188"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "PC":      {"min": 90,  "max": 150, "typical": 115, "sources": [{"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"}, {"label": "Prusa PC", "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "General": {"min": 25,  "max": 150, "typical": 60},
        },
    },
    "eng_plate_temp": {
        "info": "Bed temperature for Engineering Plate (other layers).",
        "sources": [
            {"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"},
            {"label": "Prusa PLA", "url": "https://help.prusa3d.com/article/pla_2062"},
            {"label": "Hatchbox Guides", "url": "https://www.hatchbox3d.com/pages/guides"},
            {"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"},
            {"label": "Prusa PETG", "url": "https://help.prusa3d.com/article/petg_2059"},
            {"label": "All3DP PETG", "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/"},
            {"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"},
            {"label": "Prusa ABS", "url": "https://help.prusa3d.com/article/abs_2058"},
            {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"},
            {"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"},
            {"label": "Prusa ASA", "url": "https://help.prusa3d.com/article/asa_1809"},
            {"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"},
            {"label": "Prusa Prusament TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"},
            {"label": "Overture TPU", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"},
            {"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"},
            {"label": "Prusa Polyamide", "url": "https://help.prusa3d.com/article/polyamide-nylon_167188"},
            {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"},
            {"label": "Prusa PC", "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812"},
            {"label": "Prusa HIPS", "url": "https://help.prusa3d.com/article/hips_167118"},
            {"label": "Prusa PVB", "url": "https://help.prusa3d.com/article/pvb_196708"},
            {"label": "Prusa Water-Soluble", "url": "https://help.prusa3d.com/article/water-soluble-bvoh-pva_167012"},
            {"label": "Prusa CPE", "url": "https://help.prusa3d.com/article/cpe_166877"},
            {"label": "Prusa Polypropylene", "url": "https://help.prusa3d.com/article/polypropylene-pp_167126"},
            {"label": "colorFabb XT Guide", "url": "https://colorfabb.com/blog/post/how-to-print-with-colorfabb_xt"},
            {"label": "colorFabb HT Guide", "url": "https://colorfabb.com/blog/post/how-to-print-with-colorfabb_ht"},
            {"label": "eSUN PLA+ TDS", "url": "https://www.esun3d.com/uploads/eSUN_PLA+-Filament_TDS_V4.0.pdf"},
        ],
        "ranges": {
            "PLA":     {"min": 25,  "max": 65,  "typical": 58, "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}, {"label": "Prusa PLA", "url": "https://help.prusa3d.com/article/pla_2062"}, {"label": "Hatchbox Guides", "url": "https://www.hatchbox3d.com/pages/guides"}]},
            "PETG":    {"min": 60,  "max": 90,  "typical": 80, "sources": [{"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"}, {"label": "Prusa PETG", "url": "https://help.prusa3d.com/article/petg_2059"}, {"label": "All3DP PETG", "url": "https://all3dp.com/2/petg-print-settings-how-to-find-the-best-settings-for-petg/"}]},
            "ABS":     {"min": 80,  "max": 110, "typical": 100, "sources": [{"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"}, {"label": "Prusa ABS", "url": "https://help.prusa3d.com/article/abs_2058"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "ASA":     {"min": 75,  "max": 110, "typical": 105, "sources": [{"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"}, {"label": "Prusa ASA", "url": "https://help.prusa3d.com/article/asa_1809"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "TPU":     {"min": 25,  "max": 75,  "typical": 50, "sources": [{"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"}, {"label": "Prusa Prusament TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"}, {"label": "Overture TPU", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"}]},
            "PA":      {"min": 25,  "max": 110, "typical": 90, "sources": [{"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"}, {"label": "Prusa Polyamide", "url": "https://help.prusa3d.com/article/polyamide-nylon_167188"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "PC":      {"min": 90,  "max": 150, "typical": 115, "sources": [{"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"}, {"label": "Prusa PC", "url": "https://help.prusa3d.com/article/polycarbonate-pc_165812"}, {"label": "OrcaSlicer Material Temps", "url": "https://www.orcaslicer.com/wiki/material_settings/filament/material_temperatures"}]},
            "General": {"min": 25,  "max": 150, "typical": 60},
        },
    },
    "filament_max_volumetric_speed": {
        "info": "Hotend-dependent. Larger nozzles = higher flow rates. Hardened steel nozzles may need higher temps or lower flow. Apply safety margin below tested maximum.",
        "sources": [
            {"label": "Obico OrcaSlicer Calibration", "url": "https://www.obico.io/blog/orcaslicer-comprehensive-calibration-guide/"},
            {"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"},
            {"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"},
            {"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"},
            {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"},
            {"label": "Ellis3DP Max Volumetric Flow", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/determining_max_volumetric_flow_rate.html"},
        ],
        "ranges": {
            "PLA":     {"min": 10,  "max": 25,  "typical": 16.75, "sources": [{"label": "Obico OrcaSlicer Calibration", "url": "https://www.obico.io/blog/orcaslicer-comprehensive-calibration-guide/"}]},
            "PETG":    {"min": 10,  "max": 20,  "typical": 14.5, "sources": [{"label": "Obico OrcaSlicer Calibration", "url": "https://www.obico.io/blog/orcaslicer-comprehensive-calibration-guide/"}, {"label": "Polymaker PolyLite PETG", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/petg/polylite-tm-petg"}]},
            "ABS":     {"min": 12,  "max": 24,  "typical": 17, "sources": [{"label": "Obico OrcaSlicer Calibration", "url": "https://www.obico.io/blog/orcaslicer-comprehensive-calibration-guide/"}, {"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"}]},
            "ASA":     {"min": 12,  "max": 20,  "typical": 16, "sources": [{"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"}]},
            "PC":      {"min": 8,   "max": 16,  "typical": 12, "sources": [{"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"}]},
            "General": {"min": 8,   "max": 25,  "typical": 15, "sources": [{"label": "Ellis3DP Max Volumetric Flow", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/determining_max_volumetric_flow_rate.html"}]},
        },
    },

    # ── Cooling Tab ──
    "close_fan_the_first_x_layers": {
        "info": "PLA: 1 layer off. PETG: 2–3 layers off then ramp up. ABS/ASA: all layers off if unenclosed. Running max fan from layer 1 ruins bed adhesion.",
        "sources": [
            {"label": "MatterHackers PETG", "url": "https://www.matterhackers.com/news/how-to-succeed-when-printing-with-petg-filament"},
            {"label": "Ellis3DP Cooling", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html"},
        ],
        "ranges": {
            "PLA":     {"min": 1, "max": 1, "typical": 1},
            "PETG":    {"min": 2, "max": 3, "typical": 3},
            "ABS":     {"min": 1, "max": 5, "typical": 3},
            "ASA":     {"min": 1, "max": 5, "typical": 3},
            "General": {"min": 1, "max": 3, "typical": 1},
        },
    },
    "fan_min_speed": {
        "info": "Minimum fan speed threshold. Constant fan speeds recommended — varying speeds cause inconsistent layers and banding.",
        "sources": [
            {"label": "Ellis3DP Cooling", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html"},
            {"label": "MatterHackers PETG", "url": "https://www.matterhackers.com/news/how-to-succeed-when-printing-with-petg-filament"},
            {"label": "Ellis3DP Misconceptions", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html"},
            {"label": "3DTrcek ASA Guide", "url": "https://3dtrcek.com/en/blog/post/how-to-print-asa-filament-a-practical-guide-for-durable-prints-2"},
            {"label": "Prusa TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"},
            {"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"},
            {"label": "All3DP Temps", "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/"},
            {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"},
            {"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"},
        ],
        "ranges": {
            "PLA":     {"min": 70,  "max": 100, "typical": 80, "sources": [{"label": "Ellis3DP Cooling", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html"}]},
            "PETG":    {"min": 10,  "max": 50,  "typical": 20, "sources": [{"label": "MatterHackers PETG", "url": "https://www.matterhackers.com/news/how-to-succeed-when-printing-with-petg-filament"}, {"label": "Ellis3DP Cooling", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html"}]},
            "ABS":     {"min": 0,   "max": 50,  "typical": 0, "notes": "0% unenclosed, 40%+ enclosed", "sources": [{"label": "Ellis3DP Misconceptions", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html"}, {"label": "Ellis3DP Cooling", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html"}]},
            "ASA":     {"min": 0,   "max": 30,  "typical": 0, "sources": [{"label": "3DTrcek ASA Guide", "url": "https://3dtrcek.com/en/blog/post/how-to-print-asa-filament-a-practical-guide-for-durable-prints-2"}]},
            "TPU":     {"min": 0,   "max": 10,  "typical": 0, "notes": "Keep OFF completely (Prusa)", "sources": [{"label": "Prusa TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"}, {"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"}]},
            "PA":      {"min": 0,   "max": 40,  "typical": 0, "sources": [{"label": "All3DP Temps", "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/"}]},
            "PC":      {"min": 0,   "max": 0,   "typical": 0, "notes": "Avoid active cooling", "sources": [{"label": "All3DP Temps", "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/"}, {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"}]},
            "PLA-CF":  {"min": 70,  "max": 100, "typical": 80, "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}]},
            "General": {"min": 0,   "max": 100, "typical": 50},
        },
    },
    "fan_max_speed": {
        "info": "Maximum fan speed threshold. ABS 'no cooling' ONLY applies to unenclosed printers — enclosed setups often NEED cooling.",
        "sources": [
            {"label": "Ellis3DP Cooling", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html"},
            {"label": "MatterHackers PETG", "url": "https://www.matterhackers.com/news/how-to-succeed-when-printing-with-petg-filament"},
            {"label": "Ellis3DP Misconceptions", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html"},
            {"label": "3DTrcek ASA Guide", "url": "https://3dtrcek.com/en/blog/post/how-to-print-asa-filament-a-practical-guide-for-durable-prints-2"},
            {"label": "Prusa TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"},
            {"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"},
            {"label": "All3DP Temps", "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/"},
            {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"},
            {"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"},
        ],
        "ranges": {
            "PLA":     {"min": 80,  "max": 100, "typical": 100, "sources": [{"label": "Ellis3DP Cooling", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html"}]},
            "PETG":    {"min": 20,  "max": 60,  "typical": 50, "sources": [{"label": "MatterHackers PETG", "url": "https://www.matterhackers.com/news/how-to-succeed-when-printing-with-petg-filament"}, {"label": "Ellis3DP Cooling", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html"}]},
            "ABS":     {"min": 0,   "max": 100, "typical": 0, "notes": "Enclosed: 40–100%", "sources": [{"label": "Ellis3DP Misconceptions", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/misconceptions.html"}, {"label": "Ellis3DP Cooling", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/cooling_and_layer_times.html"}]},
            "ASA":     {"min": 0,   "max": 30,  "typical": 20, "sources": [{"label": "3DTrcek ASA Guide", "url": "https://3dtrcek.com/en/blog/post/how-to-print-asa-filament-a-practical-guide-for-durable-prints-2"}]},
            "TPU":     {"min": 0,   "max": 10,  "typical": 0, "sources": [{"label": "Prusa TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"}, {"label": "Polymaker TPU", "url": "https://wiki.polymaker.com/the-basics/3d-printing-materials/tpu"}]},
            "PA":      {"min": 0,   "max": 40,  "typical": 0, "sources": [{"label": "All3DP Temps", "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/"}]},
            "PC":      {"min": 0,   "max": 0,   "typical": 0, "sources": [{"label": "All3DP Temps", "url": "https://all3dp.com/2/the-best-printing-temperature-for-different-filaments/"}, {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"}]},
            "PLA-CF":  {"min": 80,  "max": 100, "typical": 100, "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}]},
            "General": {"min": 0,   "max": 100, "typical": 70},
        },
    },
    "overhang_fan_speed": {
        "info": "Typically 100% for PLA overhangs. Force cooling for overhangs improves quality on all materials.",
        "ranges": {
            "PLA":     {"min": 80,  "max": 100, "typical": 100},
            "General": {"min": 50,  "max": 100, "typical": 100},
        },
    },

    # ── Setting Overrides: Retraction ──
    "filament_retraction_length": {
        "info": "Direct drive: 0.5–2 mm (hard max 2 mm). Bowden: 1–6 mm. Calibrate in 0.1 mm increments (direct drive) or 0.5 mm (Bowden). Should be calibrated AFTER flow rate and pressure advance.",
        "sources": [
            {"label": "Ellis3DP Retraction", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html"},
            {"label": "Sovol3D Retraction Guide", "url": "https://www.sovol3d.com/blogs/news/adjust-3d-printer-retraction-settings-for-optimal-print-quality"},
            {"label": "Polymaker Travel & Retraction", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/travel-and-retraction"},
            {"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"},
            {"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"},
            {"label": "3DTrcek ASA", "url": "https://3dtrcek.com/en/blog/post/how-to-print-asa-filament-a-practical-guide-for-durable-prints-2"},
            {"label": "Prusa TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"},
            {"label": "Overture TPU", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"},
            {"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"},
            {"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"},
            {"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"},
            {"label": "Simplify3D CF Guide", "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/"},
        ],
        "ranges": {
            "PLA":     {"min": 0.5, "max": 4.0, "typical": 0.8, "notes": "Direct drive: 0.5–1 mm", "sources": [{"label": "Ellis3DP Retraction", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html"}, {"label": "Sovol3D Retraction Guide", "url": "https://www.sovol3d.com/blogs/news/adjust-3d-printer-retraction-settings-for-optimal-print-quality"}]},
            "PETG":    {"min": 1.0, "max": 5.0, "typical": 1.5, "notes": "Exceptionally difficult to get string-free", "sources": [{"label": "Ellis3DP Retraction", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html"}, {"label": "Polymaker Travel & Retraction", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/travel-and-retraction"}]},
            "ABS":     {"min": 1.0, "max": 4.0, "typical": 1.5, "sources": [{"label": "Polymaker PolyLite ABS", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polylite-tm-abs"}, {"label": "Ellis3DP Retraction", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html"}]},
            "ASA":     {"min": 1.0, "max": 3.0, "typical": 1.5, "sources": [{"label": "Polymaker ASA", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/abs-and-asa/polymaker-tm-asa"}, {"label": "3DTrcek ASA", "url": "https://3dtrcek.com/en/blog/post/how-to-print-asa-filament-a-practical-guide-for-durable-prints-2"}]},
            "TPU":     {"min": 0.0, "max": 1.5, "typical": 0.5, "notes": "Minimal; can disable completely", "sources": [{"label": "Prusa TPU 95A", "url": "https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653"}, {"label": "Overture TPU", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"}]},
            "PA":      {"min": 1.0, "max": 6.0, "typical": 3.0, "sources": [{"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"}]},
            "PC":      {"min": 0.5, "max": 3.0, "typical": 1.0, "sources": [{"label": "Polymaker PolyLite PC", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/polycarbonate/polylite-tm-pc"}]},
            "PLA-CF":  {"min": 0.5, "max": 2.0, "typical": 1.0, "notes": "Minimize — fibers clog extruder", "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}, {"label": "Simplify3D CF Guide", "url": "https://www.simplify3d.com/resources/materials-guide/carbon-fiber-filled/"}]},
            "PETG-CF": {"min": 1.0, "max": 5.0, "typical": 3.0, "sources": [{"label": "Polymaker Printing Temperature", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/printing-temperature"}]},
            "PA-CF":   {"min": 1.0, "max": 5.0, "typical": 3.0, "sources": [{"label": "Polymaker Nylon (PA)", "url": "https://wiki.polymaker.com/polymaker-products/polymaker-filaments/prime-materials/nylon-pa"}]},
            "General": {"min": 0.5, "max": 5.0, "typical": 1.5},
        },
    },
    "filament_retraction_speed": {
        "info": "Direct drive: 20–35 mm/s (start at 35). Bowden: 30–50 mm/s. Slower retraction speeds often outperform faster ones.",
        "sources": [
            {"label": "Ellis3DP Retraction", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html"},
            {"label": "Polymaker Travel & Retraction", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/travel-and-retraction"},
            {"label": "Sovol3D Retraction Guide", "url": "https://www.sovol3d.com/blogs/news/adjust-3d-printer-retraction-settings-for-optimal-print-quality"},
            {"label": "Overture TPU Guide", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"},
            {"label": "Prusa Flexible Materials", "url": "https://help.prusa3d.com/article/flexible-materials_2057"},
            {"label": "Teaching Tech Calibration", "url": "https://teachingtechyt.github.io/calibration.html"},
        ],
        "ranges": {
            "TPU":     {"min": 10, "max": 20, "typical": 15, "notes": "Short and slow", "sources": [{"label": "Overture TPU Guide", "url": "https://overture3d.com/blogs/overture-blogs/tpu-filament-print-settings-guide"}, {"label": "Prusa Flexible Materials", "url": "https://help.prusa3d.com/article/flexible-materials_2057"}]},
            "General": {"min": 20, "max": 50, "typical": 30, "sources": [{"label": "Ellis3DP Retraction", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html"}, {"label": "Sovol3D Retraction Guide", "url": "https://www.sovol3d.com/blogs/news/adjust-3d-printer-retraction-settings-for-optimal-print-quality"}, {"label": "Polymaker Travel & Retraction", "url": "https://wiki.polymaker.com/the-basics/3d-slicers/travel-and-retraction"}, {"label": "Teaching Tech Calibration", "url": "https://teachingtechyt.github.io/calibration.html"}]},
        },
    },
    "filament_deretraction_speed": {
        "info": "Typically same as retraction speed. Ellis3DP: test at 30 mm/s for both retract and unretract.",
        "sources": [
            {"label": "Ellis3DP Retraction", "url": "https://ellis3dp.com/Print-Tuning-Guide/articles/retraction.html"},
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
for _plate in ("cool_plate_temp", "hot_plate_temp", "textured_plate_temp", "eng_plate_temp"):
    _il_key = f"{_plate}_initial_layer"
    if _plate in RECOMMENDATIONS and _il_key not in RECOMMENDATIONS:
        RECOMMENDATIONS[_il_key] = {
            "info": RECOMMENDATIONS[_plate]["info"].replace("(other layers)", "(initial layer)"),
            "sources": RECOMMENDATIONS[_plate].get("sources", []),
            "ranges": RECOMMENDATIONS[_plate]["ranges"],
        }
del _plate, _il_key


# --- Enum Value Mappings ---
# Maps JSON parameter values to human-readable labels.

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
_NOZZLE_SIZES = ["0.2", "0.4", "0.6", "0.8", "1.0"]

# All BambuStudio-recognized printer strings.  Used by make_universal() to
# add every known printer so the profile is usable on any BBL machine.
# BambuStudio treats compatible_printers as a whitelist — an empty list means
# "compatible with nothing", NOT "compatible with everything".
_ALL_BBL_PRINTERS = [
    f"Bambu Lab {model} {nz} nozzle"
    for model in [
        "X1 Carbon", "X1", "X1E", "P1S", "P1P", "P2S",
        "A1", "A1 mini",
        "H2C", "H2D", "H2D Pro", "H2S",
    ]
    for nz in ["0.2", "0.4", "0.6", "0.8"]
]

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
