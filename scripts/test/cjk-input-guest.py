#!/usr/bin/python3
"""Exercise all three actual SteamOS engines in dedicated IBus test contexts."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import gi

gi.require_version('IBus', '1.0')
gi.require_version('Gio', '2.0')
from gi.repository import IBus, Gio

helpers = runpy.run_path(str(Path(__file__).with_name('japanese-input-test')))
pump = helpers['pump']


def conversion(bus, engine, reading, expected, toggle):
    bus.set_global_engine(engine)
    pump(0.2)
    context = bus.create_input_context('steamac-cjk-test-'+engine)
    context.set_capabilities(int(IBus.Capabilite.PREEDIT_TEXT | IBus.Capabilite.LOOKUP_TABLE |
                                 IBus.Capabilite.FOCUS))
    committed = []
    preedit = []
    trace = []
    context.connect('commit-text', lambda ctx, text: committed.append(text.get_text()))
    context.connect('update-preedit-text', lambda ctx, text, cursor, visible: preedit.append(text.get_text()))
    context.connect('update-property', lambda ctx, prop: trace.append(('property', prop.get_key(), int(prop.get_state()))))
    context.focus_in()
    context.set_engine(engine)
    context.set_content_type(int(IBus.InputPurpose.FREE_FORM), 0)
    pump(1)
    assert context.get_engine().get_name() == engine, engine+' unavailable'

    def key(name, flags=0):
        # Keep one input focus while typing, like a real text field.
        pump(0.03)
        value = IBus.keyval_from_name(name) if len(name) > 1 else ord(name)
        # Hangul 1.5.5 maps physical evdev codes; keycode 0 is not a keyboard event.
        codes = {'a':30, 'g':34, 'k':37, 's':31, 'r':19, 'm':50, 'f':33, 'Return':28, 'space':57}
        code = codes.get(name, 0) if engine == 'hangul' else 0
        handled = context.process_key_event(value, code, flags)
        context.process_key_event(value, code, flags | int(IBus.ModifierType.RELEASE_MASK))
        pump()
        current = context.get_engine()
        trace.append((name, flags, bool(handled), current.get_name() if current else None,
                      preedit[-1:], ''.join(committed)))
        return handled

    assert not key('a') or ''.join(committed) == 'a', engine+' did not start in Latin mode'
    committed.clear()
    key(*toggle)
    for char in reading:
        key(char)
    key('space' if engine == 'pinyin' else 'Return')
    pump(0.5)
    result = ''.join(committed).strip()
    assert expected in result, engine+' conversion failed: '+repr(result)+' keys='+repr(trace)
    committed.clear()
    key(*toggle)
    assert not key('a') or ''.join(committed) == 'a', engine+' did not return to Latin mode'
    context.focus_out()
    context.destroy()
    return {'conversion': result, 'initial_latin': True, 'return_to_latin': True}


def main():
    IBus.init()
    bus = IBus.Bus.new()
    assert bus.is_connected()
    language = next((w.split('=', 1)[1] for w in Path('/proc/cmdline').read_text().split()
                     if w.startswith('steamac.input_language=')), 'latin')
    display_language = next((w.split('=', 1)[1] for w in Path('/proc/cmdline').read_text().split()
                            if w.startswith('steamac.setup_language=')), None)
    base = 'xkb:jp::jpn' if 'steamac.keyboard=jis' in Path('/proc/cmdline').read_text().split() else 'xkb:us::eng'
    selected = {'ja': 'anthy', 'ko': 'hangul', 'zh-Hans': 'pinyin'}.get(language, base)
    active = subprocess.check_output(['ibus', 'engine'], text=True).strip()
    assert active == selected, f'First-run engine {active} != {selected}'
    general = Gio.Settings.new('org.freedesktop.ibus.general')
    hotkey = Gio.Settings.new('org.freedesktop.ibus.general.hotkey')
    hangul = Gio.Settings.new('org.freedesktop.ibus.engine.hangul')
    print('CJK_INPUT_SETTINGS '+json.dumps({'hangul_switch':hangul.get_string('switch-keys'),
          'hangul_initial':hangul.get_string('initial-input-mode'), 'trigger':list(hotkey.get_strv('trigger')),
          'triggers':list(hotkey.get_strv('triggers'))}), flush=True)
    binary = Path('/usr/lib/ibus/ibus-engine-hangul').read_bytes()
    print('HANGUL_BACKEND '+repr([word for word in [b'engine/Hangul', b'SwitchKeys',
          b'InitialInputMode', b'org.freedesktop.ibus.engine.hangul', b'switch-keys'] if word in binary]), flush=True)
    assert {'anthy', 'pinyin', 'hangul'}.issubset(general.get_strv('preload-engines'))
    assert '<Control>period' in hotkey.get_strv('triggers')
    chinese = conversion(bus, 'pinyin', 'nihao', '你好', ('Shift_L', 0))
    korean = conversion(bus, 'hangul', 'gksrmf', '한글',
                        ('space', int(IBus.ModifierType.CONTROL_MASK)))
    bus.set_global_engine('anthy')
    pump(0.2)
    japanese = helpers['test_engine']()
    # A later launch must preserve edited shortcuts, engine order and current selection.
    custom = ['hangul', 'pinyin', 'anthy']
    general.set_strv('preload-engines', custom)
    hotkey.set_strv('triggers', ['<Alt>space'])
    hangul.set_string('switch-keys', 'Hangul,Shift+space')
    Gio.Settings.sync()
    subprocess.run(['ibus', 'engine', 'pinyin'], check=True)
    before = subprocess.check_output(['ibus', 'engine'], text=True).strip()
    subprocess.run(['/usr/lib/steamac/keyboard-setup'], check=True)
    subprocess.run(['/usr/lib/steamac/keyboard-session'], check=True)
    assert list(general.get_strv('preload-engines')) == custom
    assert list(hotkey.get_strv('triggers')) == ['<Alt>space']
    assert hangul.get_string('switch-keys') == 'Hangul,Shift+space'
    assert subprocess.check_output(['ibus', 'engine'], text=True).strip() == before
    result = {'detected_mac_input_source': language, 'display_language': display_language, 'first_engine': active,
              'japanese': japanese, 'chinese': chinese, 'korean': korean,
              'user_edits_preserved': True, 'xwaylands': helpers['test_xwaylands'](),
              'guest_refresh_hz': helpers['test_refresh']()}
    print('JAPANESE_INPUT_RESULT '+json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
