"""Tests for profile_toolkit.providers_pkg — online profile providers."""

import json
import tempfile
import time
import unittest.mock as mock
from pathlib import Path
from urllib.error import URLError

from profile_toolkit.providers_pkg.base import OnlineProfileEntry, OnlineProvider
from profile_toolkit.providers_pkg.manufacturers import (
    PolymakerProvider,
    ColorFabbProvider,
    PrusaResearchProvider,
)
from profile_toolkit.providers_pkg.databases import (
    _make_entry,
    SimplyPrintDBProvider,
    OrcaSlicerLibraryProvider,
    BambuStudioOfficialProvider,
)
from profile_toolkit.providers_pkg.community import (
    CommunityPresetsProvider,
    SantanachiaProvider,
    DgaucheFilamentLibProvider,
)

# ---------------------------------------------------------------------------
# OnlineProfileEntry
# ---------------------------------------------------------------------------


class TestOnlineProfileEntry:
    def test_defaults(self):
        e = OnlineProfileEntry(name="Test")
        assert e.name == "Test"
        assert e.nozzle == "0.4"
        assert e.selected is False
        assert e.metadata == {}

    def test_all_fields(self):
        e = OnlineProfileEntry(
            name="PLA",
            material="PLA",
            brand="Polymaker",
            printer="X1C",
            slicer="OrcaSlicer",
            url="https://example.com/pla.json",
            description="desc",
            provider_id="polymaker",
            metadata={"key": "val"},
        )
        assert e.brand == "Polymaker"
        assert e.metadata["key"] == "val"


# ---------------------------------------------------------------------------
# OnlineProvider base class — pure methods
# ---------------------------------------------------------------------------


class TestOnlineProviderSourceHint:
    def test_github_url(self):
        p = OnlineProvider()
        p.website = "https://github.com/Polymaker3D/Polymaker-Preset/tree/main"
        assert p.source_hint == "github.com/Polymaker3D"

    def test_non_github(self):
        p = OnlineProvider()
        p.website = "https://example.com/profiles"
        assert p.source_hint == "example.com"

    def test_empty(self):
        p = OnlineProvider()
        p.website = ""
        assert p.source_hint == ""


class TestSuggestFilename:
    def test_json_url(self):
        p = OnlineProvider()
        entry = OnlineProfileEntry(
            name="My Profile", url="https://example.com/file.json"
        )
        result = p._suggest_filename(entry)
        assert result == "My_Profile.json"

    def test_bbsflmt_url(self):
        p = OnlineProvider()
        entry = OnlineProfileEntry(name="Test", url="https://example.com/file.bbsflmt")
        assert p._suggest_filename(entry).endswith(".bbsflmt")

    def test_ini_url(self):
        p = OnlineProvider()
        entry = OnlineProfileEntry(name="Test", url="https://example.com/file.ini")
        assert p._suggest_filename(entry).endswith(".ini")

    def test_sanitizes_unsafe_chars(self):
        p = OnlineProvider()
        entry = OnlineProfileEntry(
            name='Bad/Name:"chars', url="https://example.com/f.json"
        )
        result = p._suggest_filename(entry)
        assert "/" not in result
        assert '"' not in result
        assert ":" not in result

    def test_truncates_long_names(self):
        p = OnlineProvider()
        entry = OnlineProfileEntry(name="A" * 300, url="https://example.com/f.json")
        result = p._suggest_filename(entry)
        assert len(result) <= 205  # 200 + ext


class TestValidateProfileContent:
    def test_valid_json(self):
        p = OnlineProvider()
        data = b'{"name": "test"}'
        p._validate_profile_content(data, "test.json")  # should not raise

    def test_invalid_json_raises(self):
        import pytest

        p = OnlineProvider()
        with pytest.raises(ValueError, match="not valid JSON"):
            p._validate_profile_content(b"not json", "test.json")

    def test_invalid_utf8_raises(self):
        import pytest

        p = OnlineProvider()
        with pytest.raises(ValueError, match="not valid UTF-8"):
            p._validate_profile_content(b"\xff\xfe", "test.json")

    def test_ini_skips_json_check(self):
        p = OnlineProvider()
        p._validate_profile_content(b"key = value", "test.ini")  # should not raise

    def test_bbsflmt_validated_as_json(self):
        p = OnlineProvider()
        data = b'{"filament_type": "PLA"}'
        p._validate_profile_content(data, "test.bbsflmt")  # should not raise


class TestReport:
    def test_with_callback(self):
        p = OnlineProvider()
        msgs = []
        p._status_fn = msgs.append
        p._report("hello")
        assert msgs == ["hello"]

    def test_without_callback(self):
        p = OnlineProvider()
        p._status_fn = None
        p._report("hello")  # should not raise


class TestSslIsDegraded:
    def test_default_false(self):
        # Reset to known state
        OnlineProvider._ssl_degraded_flag = False
        assert OnlineProvider.ssl_is_degraded() is False


# ---------------------------------------------------------------------------
# Catalog cache round-trip
# ---------------------------------------------------------------------------


class TestCatalogCache:
    def test_save_and_load(self):
        p = PolymakerProvider()
        entries = [
            OnlineProfileEntry(
                name="PLA Test",
                material="PLA",
                brand="Polymaker",
                url="https://example.com/pla.json",
                provider_id="polymaker",
            )
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(
                OnlineProvider, "_cache_dir", return_value=Path(tmpdir)
            ):
                p._save_catalog_cache(entries)
                loaded = p._load_catalog_cache()
                assert loaded is not None
                assert len(loaded) == 1
                assert loaded[0].name == "PLA Test"
                assert loaded[0].material == "PLA"

    def test_stale_cache_returns_none(self):
        p = PolymakerProvider()
        entries = [OnlineProfileEntry(name="Old", url="https://example.com/old.json")]
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(
                OnlineProvider, "_cache_dir", return_value=Path(tmpdir)
            ):
                p._save_catalog_cache(entries)
                # Backdate the cache file
                cache_path = p._catalog_cache_path()
                data = json.loads(cache_path.read_text())
                data["timestamp"] = time.time() - (25 * 3600)  # 25 hours ago
                cache_path.write_text(json.dumps(data))

                loaded = p._load_catalog_cache()
                assert loaded is None

    def test_missing_cache_returns_none(self):
        p = PolymakerProvider()
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(
                OnlineProvider, "_cache_dir", return_value=Path(tmpdir)
            ):
                assert p._load_catalog_cache() is None


# ---------------------------------------------------------------------------
# _make_entry (databases.py helper)
# ---------------------------------------------------------------------------


class TestMakeEntry:
    def test_basic(self):
        e = _make_entry(
            fname="Prusament PLA",
            url="https://example.com/pla.json",
            slicer="OrcaSlicer",
            provider_id="test",
            description="Test DB",
        )
        assert e.name == "Prusament PLA"
        assert e.material == "PLA"
        assert e.slicer == "OrcaSlicer"

    def test_with_at_machine(self):
        e = _make_entry(
            fname="Generic PLA @BBL X1C 0.4 nozzle",
            url="https://example.com/pla.json",
            slicer="BambuStudio",
            provider_id="test",
            description="Test",
        )
        assert e.printer == "X1 Carbon"
        assert e.nozzle == "0.4"

    def test_default_brand(self):
        e = _make_entry(
            fname="Unknown Filament",
            url="https://example.com/f.json",
            slicer="OrcaSlicer",
            provider_id="test",
            description="Test",
            default_brand="FallbackBrand",
        )
        assert e.brand == "FallbackBrand"

    def test_guesses_brand(self):
        e = _make_entry(
            fname="Polymaker PLA Pro",
            url="https://example.com/f.json",
            slicer="OrcaSlicer",
            provider_id="test",
            description="Test",
        )
        assert e.brand == "Polymaker"


# ---------------------------------------------------------------------------
# PrusaResearchProvider — pure methods
# ---------------------------------------------------------------------------


class TestPrusaScanFilamentNames:
    def test_parses_sections(self):
        raw = (
            b"[filament:Prusament PLA]\n"
            b"filament_type = PLA\n"
            b"[filament:Generic PETG]\n"
            b"filament_type = PETG\n"
        )
        p = PrusaResearchProvider()
        names = p._scan_filament_names(raw)
        assert "Generic PETG" in names
        assert "Prusament PLA" in names

    def test_skips_abstract(self):
        raw = b"[filament:*common*]\nsome = value\n[filament:Real PLA]\ntype = PLA\n"
        p = PrusaResearchProvider()
        names = p._scan_filament_names(raw)
        assert "*common*" not in names
        assert "Real PLA" in names

    def test_empty(self):
        p = PrusaResearchProvider()
        assert p._scan_filament_names(b"") == []

    def test_no_filament_sections(self):
        raw = b"[printer:MK4]\nbed_shape = ...\n"
        p = PrusaResearchProvider()
        assert p._scan_filament_names(raw) == []


class TestPrusaExtractBrand:
    def test_known_brand(self):
        p = PrusaResearchProvider()
        assert p._extract_brand("Polymaker PLA Pro") == "Polymaker"

    def test_prusament(self):
        p = PrusaResearchProvider()
        assert p._extract_brand("Prusament PLA") == "Prusament"

    def test_generic(self):
        p = PrusaResearchProvider()
        assert p._extract_brand("Generic PLA") == "Generic"

    def test_unknown_uses_first_word(self):
        p = PrusaResearchProvider()
        assert p._extract_brand("SomeBrand Special Filament") == "SomeBrand"

    def test_empty(self):
        p = PrusaResearchProvider()
        assert p._extract_brand("") == ""


class TestPrusaClearCache:
    def test_clears_internal_caches(self):
        p = PrusaResearchProvider()
        p._cached_raw = b"some data"
        p._cached_sections = {"filaments": {}}
        with mock.patch.object(OnlineProvider, "clear_cache"):
            p.clear_cache()
        assert p._cached_raw is None
        assert p._cached_sections is None


# ---------------------------------------------------------------------------
# Provider _fetch_catalog_online — mocked network
# ---------------------------------------------------------------------------


def _github_tree_response(files: list[str]) -> dict:
    """Build a mock GitHub git/trees response."""
    return {
        "tree": [
            {"type": "blob", "path": p, "url": f"https://api.github.com/{p}"}
            for p in files
        ],
        "truncated": False,
    }


class TestPolymakerFetchCatalog:
    def test_parses_tree(self):
        tree = _github_tree_response(
            [
                "preset/PLA/BBL/A1/BambuStudio/Polymaker PLA Pro.json",
                "preset/PETG/BBL/X1C/OrcaSlicer/Polymaker PETG.json",
                "README.md",  # should be ignored
            ]
        )
        p = PolymakerProvider()
        with mock.patch.object(p, "_fetch_json", return_value=tree):
            entries = p._fetch_catalog_online()
        assert len(entries) == 2
        materials = {e.material for e in entries}
        assert "PLA" in materials
        assert "PETG" in materials
        assert all(e.brand == "Polymaker" for e in entries)

    def test_network_error_returns_empty(self):
        p = PolymakerProvider()
        with mock.patch.object(p, "_fetch_json", side_effect=URLError("timeout")):
            entries = p._fetch_catalog_online()
        assert entries == []


class TestColorFabbFetchCatalog:
    def test_parses_tree(self):
        tree = _github_tree_response(
            [
                "BambuStudio/filament/nGen @BBL A1 0.4 nozzle.json",
                "OrcaSlicer/filament/HT @BBL X1C 0.6 nozzle.json",
                "OrcaSlicer/process/should_skip.json",
            ]
        )
        p = ColorFabbProvider()
        with mock.patch.object(p, "_fetch_json", return_value=tree):
            entries = p._fetch_catalog_online()
        assert len(entries) == 2
        assert all(e.brand == "colorFabb" for e in entries)


class TestSimplyPrintFetchCatalog:
    def test_parses_tree(self):
        tree = _github_tree_response(
            [
                "profiles/BambuStudio/filament/Generic PLA @BBL A1 0.4 nozzle.json",
                "profiles/OrcaSlicer/filament/eSUN PETG.json",
                "profiles/BambuStudio/process/should_be_ignored.json",
            ]
        )
        p = SimplyPrintDBProvider()
        with mock.patch.object(p, "_fetch_json", return_value=tree):
            entries = p._fetch_catalog_online()
        # Only filament files should be included
        assert len(entries) == 2


class TestOrcaSlicerLibraryFetchCatalog:
    def test_parses_tree(self):
        tree = _github_tree_response(
            [
                "resources/profiles/BBL/filament/Generic PLA.json",
                "resources/profiles/BBL/filament/Generic PETG.json",
                "resources/profiles/BBL/machine/should_skip.json",
            ]
        )
        p = OrcaSlicerLibraryProvider()
        with mock.patch.object(p, "_fetch_json", return_value=tree):
            entries = p._fetch_catalog_online()
        assert len(entries) == 2


class TestBambuStudioOfficialFetchCatalog:
    def test_parses_tree(self):
        # _fetch_git_tree already filters to filament prefix, returns matching nodes
        nodes = [
            {
                "type": "blob",
                "path": "resources/profiles/BBL/filament/Bambu PLA Basic.json",
            },
            {"type": "blob", "path": "resources/profiles/BBL/filament/Bambu PETG.json"},
        ]
        p = BambuStudioOfficialProvider()
        with mock.patch.object(p, "_fetch_git_tree", return_value=nodes):
            entries = p._fetch_catalog_online()
        assert len(entries) == 2
        assert entries[0].material == "PLA"


class TestPrusaFetchCatalog:
    def test_parses_bundle_names(self):
        raw_bundle = (
            b"[filament:Prusament PLA]\n"
            b"filament_type = PLA\n"
            b"compatible_printers = MK4S 0.4\n"
            b"\n"
            b"[filament:Generic PETG]\n"
            b"filament_type = PETG\n"
        )
        p = PrusaResearchProvider()
        with mock.patch.object(p, "_fetch_bundle_raw", return_value=raw_bundle):
            entries = p._fetch_catalog_online()
        assert len(entries) == 2
        names = {e.name for e in entries}
        assert "Prusament PLA" in names
        assert "Generic PETG" in names


class TestCommunityPresetsFetchCatalog:
    def test_parses_tree(self):
        p = CommunityPresetsProvider()
        # _fetch_git_tree filters to "filament" prefix, only filament nodes returned
        tree_nodes = [
            {"type": "blob", "path": "filament/Polymaker PLA @BBL A1 0.4 nozzle.json"},
            {"type": "blob", "path": "filament/eSUN PETG.json"},
        ]
        with mock.patch.object(p, "_fetch_git_tree", return_value=tree_nodes):
            entries = p._fetch_catalog_online()
        assert len(entries) == 2


class TestSantanachiaFetchCatalog:
    def test_parses_tree(self):
        tree = _github_tree_response(
            [
                "Polymaker/A1/PLA Pro.json",
                "eSUN/PETG.bbsflmt",
                ".github/README.md",  # skip
            ]
        )
        p = SantanachiaProvider()
        with mock.patch.object(p, "_fetch_json", return_value=tree):
            entries = p._fetch_catalog_online()
        assert len(entries) == 2


class TestDgaucheFetchCatalog:
    def test_parses_tree(self):
        tree = _github_tree_response(
            [
                "A1/Polymaker PLA.json",
                "X1C/eSUN PETG.bbsflmt",
            ]
        )
        p = DgaucheFilamentLibProvider()
        with mock.patch.object(p, "_fetch_json", return_value=tree):
            entries = p._fetch_catalog_online()
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    def test_all_providers_exist(self):
        from profile_toolkit.providers_pkg import ALL_PROVIDERS

        assert len(ALL_PROVIDERS) >= 8
        ids = {p.id for p in ALL_PROVIDERS}
        assert "polymaker" in ids
        assert "prusaresearch" in ids
        assert "colorfabb" in ids
        assert "simplyprint" in ids
        assert "orcalibrary" in ids

    def test_all_have_id_and_name(self):
        from profile_toolkit.providers_pkg import ALL_PROVIDERS

        for p in ALL_PROVIDERS:
            assert p.id, f"Provider missing id: {p}"
            assert p.name, f"Provider missing name: {p}"

    def test_unique_ids(self):
        from profile_toolkit.providers_pkg import ALL_PROVIDERS

        ids = [p.id for p in ALL_PROVIDERS]
        assert len(ids) == len(set(ids)), f"Duplicate provider IDs: {ids}"
