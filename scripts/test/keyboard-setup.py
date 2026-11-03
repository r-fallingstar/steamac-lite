#!/usr/bin/env python3
"""Pure setup logic: physical layout is separate from Japanese input and user shortcuts."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[2]/'guest/layer/usr/lib/steamac/keyboard-setup'
loader = SourceFileLoader('keyboard_setup', str(path))
module = module_from_spec(spec_from_loader(loader.name, loader))
loader.exec_module(module)


class KeyboardTests(unittest.TestCase):
    def test_jis_and_ansi_have_distinct_punctuation_layouts(self):
        self.assertEqual(module.environment('jis', True)['XKB_DEFAULT_LAYOUT'], 'jp')
        self.assertEqual(module.environment('us', True)['XKB_DEFAULT_LAYOUT'], 'us')

    def test_input_language_does_not_determine_geometry(self):
        self.assertEqual(module.boot_options('LANG=ja_JP.UTF-8 steamac.keyboard=us steamac.japanese_ime=1'),
                         ('us', True))

    def test_explicit_last_option_wins(self):
        self.assertEqual(module.boot_options('steamac.keyboard=jis steamac.keyboard=us steamac.japanese_ime=0'),
                         ('us', False))

    def test_no_shell_values_from_kernel_command_line(self):
        self.assertEqual(module.boot_options('steamac.keyboard=jp;id steamac.japanese_ime=yes'), (None, False))

    def test_disabled_does_not_enable_ime_or_change_layout(self):
        self.assertEqual(module.environment(None, False), {})
        self.assertNotIn('XMODIFIERS', module.environment('us', False))

    def test_shortcuts_keep_unrelated_keys_and_remove_conflict(self):
        current = {'commit': ['Return'], 'on_off': ['Ctrl+J'],
                   'convert_to_char_type_forward': ['Muhenkan', 'F8']}
        original = {k: list(v) for k, v in current.items()}
        changed = module.anthy_shortcuts(current)
        self.assertEqual(current, original)
        self.assertEqual(changed['commit'], ['Return'])
        self.assertEqual(changed['latin_mode'], ['Muhenkan'])
        self.assertEqual(changed['hiragana_mode'], ['Hiragana'])
        self.assertEqual(changed['convert_to_char_type_forward'], ['F8'])
        self.assertIn('Ctrl+space', changed['on_off'])
        self.assertEqual(module.anthy_shortcuts(changed), changed)

    def test_first_input_method_follows_detected_mac_source_not_display_language(self):
        self.assertEqual(module.preferred_engine('steamac.keyboard=jis steamac.input_language=ko'), 'hangul')
        self.assertEqual(module.preferred_engine('steamac.keyboard=us steamac.input_language=zh-Hans'), 'pinyin')
        self.assertEqual(module.preferred_engine('steamac.input_language=ja'), 'anthy')
        self.assertEqual(module.preferred_engine('steamac.input_language=ko;id'), 'xkb:us::eng')

    def test_mac_abc_stays_latin_with_korean_or_chinese_ui(self):
        for ui in ['ja', 'ko', 'zh-Hans']:
            for layout, engine in [('us', 'xkb:us::eng'), ('jis', 'xkb:jp::jpn')]:
                cmdline = f'steamac.setup_language={ui} steamac.keyboard={layout} steamac.input_language=latin'
                self.assertEqual(module.preferred_engine(cmdline), engine)

    def test_unknown_source_does_not_guess_an_ime_from_ui_or_jis_geometry(self):
        self.assertEqual(module.preferred_engine('steamac.setup_language=ko steamac.keyboard=jis'), 'xkb:jp::jpn')
        self.assertEqual(module.preferred_engine('steamac.setup_language=zh-Hans steamac.input_language=ru'), 'xkb:us::eng')

    def test_fresh_engine_order_and_existing_custom_order(self):
        order = module.engine_order(['anthy', 'xkb:jp::jpn'], 'jis', 'hangul', True)
        self.assertEqual(order, ['hangul', 'xkb:jp::jpn', 'anthy', 'pinyin'])
        custom = ['custom-engine', 'pinyin', 'anthy']
        migrated = module.engine_order(custom, 'us', 'hangul', False)
        self.assertEqual(migrated[:len(custom)], custom)
        self.assertEqual(migrated.count('pinyin'), 1)
        self.assertIn('hangul', migrated)
        self.assertIn('xkb:us::eng', migrated)

    def test_nested_desktop_follows_changed_hardware(self):
        jis, managed = module.desktop_layout('[Other]\nKeep=yes\n', 'jis')
        self.assertIn('LayoutList=jp', jis)
        self.assertIn('Keep=yes', jis)
        us, managed = module.desktop_layout(jis, 'us', managed)
        self.assertIn('LayoutList=us', us)

    def test_user_desktop_layout_is_not_overwritten_later(self):
        jis, managed = module.desktop_layout('', 'jis')
        manual = jis.replace('LayoutList=jp', 'LayoutList=de')
        text, next_managed = module.desktop_layout(manual, 'us', managed)
        self.assertEqual(text, manual)
        self.assertIsNone(next_managed)


if __name__ == '__main__':
    unittest.main()
