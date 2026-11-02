#!/usr/bin/env python3
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
loader = importlib.machinery.SourceFileLoader("steam_language", str(ROOT/"guest/layer/usr/lib/steamac/steam-language"))
spec = importlib.util.spec_from_loader(loader.name,loader)
m = importlib.util.module_from_spec(spec);loader.exec_module(m)


class LanguageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.registry = self.home/".steam/registry.vdf"

    def test_first_start_japanese_and_no_login_fields(self):
        self.assertEqual(m.seed(self.home,"steamac.setup_language=ja"),"initial-language-seeded")
        values=m.VDF["vdf_entries"](self.registry.read_text())[0]
        self.assertEqual(values[tuple(k.lower() for k in m.REGISTRY_LANGUAGE_PATH)][0],"japanese")
        self.assertEqual(len(values),1)

    def test_all_supported_languages(self):
        for code,expected in m.LANGUAGES.items():
            with tempfile.TemporaryDirectory() as directory:
                home=Path(directory);m.seed(home,"steamac.setup_language="+code)
                self.assertIn(expected,(home/".steam/registry.vdf").read_text())

    def test_existing_manual_language_and_unrelated_bytes_kept(self):
        self.registry.parent.mkdir()
        original='"Registry" { "HKCU" { "Software" { "Valve" { "Steam" { "language" "german" "Other" "keep" } } } } }'
        self.registry.write_text(original)
        self.assertEqual(m.seed(self.home,"steamac.setup_language=ja"),"existing-settings-preserved")
        self.assertEqual(self.registry.read_text(),original)

    def test_existing_steam_install_not_reconfigured(self):
        config=self.home/".local/share/Steam/config/config.vdf"
        config.parent.mkdir(parents=True);config.write_text('"InstallConfigStore" {}')
        self.assertEqual(m.seed(self.home,"steamac.setup_language=ja"),"existing-settings-preserved")
        self.assertFalse(self.registry.exists())

    def test_later_language_edit_wins(self):
        m.seed(self.home,"steamac.setup_language=ja")
        text=self.registry.read_text().replace('"japanese"','"english"');self.registry.write_text(text)
        self.assertEqual(m.seed(self.home,"steamac.setup_language=ru"),"already-initialized")
        self.assertEqual(self.registry.read_text(),text)

    def test_unsupported_or_missing_flag_leaves_no_files(self):
        self.assertEqual(m.seed(self.home,"steamac.setup_language=de"),"no-supported-language")
        self.assertEqual(list(self.home.iterdir()),[])

    def test_malformed_registry_not_overwritten(self):
        self.registry.parent.mkdir();self.registry.write_text('"Registry" { broken')
        with self.assertRaises(ValueError):m.seed(self.home,"steamac.setup_language=ja")
        self.assertEqual(self.registry.read_text(),'"Registry" { broken')


if __name__ == "__main__":unittest.main()
