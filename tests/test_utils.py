"""Tests for profile_toolkit.utils — pure functions."""

from profile_toolkit.utils import (
    nil_to_zero,
    user_error,
    detect_material,
    lighten_color,
    guess_material,
    guess_brand,
    parse_printer_nozzle,
    humanize_enum_value,
    check_value_range,
)


class TestNilToZero:
    def test_none(self):
        assert nil_to_zero(None) == 0

    def test_empty_string(self):
        assert nil_to_zero("") == 0

    def test_nil_string(self):
        assert nil_to_zero("nil") == 0

    def test_passthrough_int(self):
        assert nil_to_zero(42) == 42

    def test_passthrough_float(self):
        assert nil_to_zero(3.14) == 3.14


class TestUserError:
    def test_basic(self):
        msg = user_error("Load failed", "file not found")
        assert "Load failed" in msg
        assert "file not found" in msg

    def test_with_tip(self):
        msg = user_error("Oops", "err", tip="Try again")
        assert "Try again" in msg


class TestDetectMaterial:
    def test_filament_type_field(self):
        assert detect_material({"filament_type": "PLA"}) == "PLA"

    def test_filament_type_list(self):
        assert detect_material({"filament_type": ["PETG"]}) == "PETG"

    def test_name_fallback(self):
        assert detect_material({"name": "Prusament PLA"}) == "PLA"

    def test_cf_variant(self):
        assert detect_material({"filament_type": "PLA-CF"}) == "PLA-CF"

    def test_petg_cf(self):
        assert detect_material({"filament_type": "PETG CF"}) == "PETG-CF"

    def test_pa_cf(self):
        assert detect_material({"filament_type": "PA6-CF"}) == "PA-CF"

    def test_nylon(self):
        assert detect_material({"filament_type": "NYLON"}) == "PA"

    def test_empty(self):
        assert detect_material({}) == "General"

    def test_none(self):
        assert detect_material(None) == "General"

    def test_tpu(self):
        assert detect_material({"filament_type": "TPU"}) == "TPU"

    def test_abs(self):
        assert detect_material({"filament_type": "ABS"}) == "ABS"

    def test_asa(self):
        assert detect_material({"filament_type": "ASA"}) == "ASA"

    def test_name_pa_word_boundary(self):
        assert detect_material({"name": "Generic PA"}) == "PA"
        assert detect_material({"name": "SPACING Profile"}) == "General"


class TestLightenColor:
    def test_basic(self):
        assert lighten_color("#000000", 10) == "#0a0a0a"

    def test_clamp_255(self):
        assert lighten_color("#ffffff", 10) == "#ffffff"

    def test_invalid_hex(self):
        assert lighten_color("#abc") == "#abc"

    def test_no_hash(self):
        assert lighten_color("red") == "red"


class TestGuessMaterial:
    def test_pla(self):
        assert guess_material("Prusament PLA") == "PLA"

    def test_no_match(self):
        assert guess_material("Generic Profile") == ""


class TestGuessBrand:
    def test_known_brand(self):
        assert guess_brand("Polymaker PLA Pro") == "Polymaker"

    def test_esun(self):
        assert guess_brand("eSUN PETG") == "eSUN"

    def test_unknown(self):
        assert guess_brand("My Custom Filament") == ""

    def test_case_insensitive(self):
        assert guess_brand("POLYMAKER ABS") == "Polymaker"


class TestParsePrinterNozzle:
    def test_bbl_x1c(self):
        printer, nozzle = parse_printer_nozzle("@BBL X1C 0.6 nozzle")
        assert printer == "X1 Carbon"
        assert nozzle == "0.6"

    def test_plain_alias(self):
        printer, nozzle = parse_printer_nozzle("MK4S")
        assert printer == "MK4S"
        assert nozzle == "0.4"

    def test_coreone_hf(self):
        printer, nozzle = parse_printer_nozzle("COREONE HF")
        assert printer == "Core One HF"
        assert nozzle == "0.4"

    def test_nozzle_first(self):
        printer, nozzle = parse_printer_nozzle("0.6 nozzle MINI")
        assert printer == "Mini"
        assert nozzle == "0.6"

    def test_hf_nozzle_first(self):
        printer, nozzle = parse_printer_nozzle("HF0.6")
        assert "HF" in nozzle or "HF" in printer

    def test_at_prefix_stripped(self):
        printer, nozzle = parse_printer_nozzle("@MK4S")
        assert printer == "MK4S"


class TestHumanizeEnumValue:
    def test_camel_case(self):
        assert humanize_enum_value("monotonicLines") == "Monotonic Lines"

    def test_underscore(self):
        assert humanize_enum_value("even_odd") == "Even Odd"

    def test_simple(self):
        assert humanize_enum_value("nearest") == "Nearest"


class TestCheckValueRange:
    def test_unknown_key(self):
        assert check_value_range("nonexistent_key_xyz", 100) is None

    def test_none_value(self):
        assert check_value_range("nozzle_temperature", None) is None

    def test_list_empty(self):
        assert check_value_range("nozzle_temperature", []) is None

    def test_unparseable(self):
        assert check_value_range("nozzle_temperature", "not_a_number") is None
