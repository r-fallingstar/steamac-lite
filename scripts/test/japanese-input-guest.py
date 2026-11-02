#!/usr/bin/python3
"""Run in a test guest: exercise Anthy over IBus and inspect both real Xwaylands.

No game is started, no keystrokes are sent to another application, and no SSH is needed.
"""
import ctypes as C
import json
import os
from pathlib import Path
import re
import subprocess
import time
import gi

gi.require_version('IBus', '1.0')
from gi.repository import IBus, GLib


def pump(seconds=0.1):
    end = time.monotonic()+seconds
    context = GLib.MainContext.default()
    while time.monotonic() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(0.005)


def test_engine():
    print('input-test: connecting to IBus', flush=True)
    IBus.init()
    bus = IBus.Bus.new()
    assert bus.is_connected(), 'IBus not connected'
    print('input-test: IBus connected', flush=True)
    context = bus.create_input_context('steamac-integration-test')
    context.set_capabilities(int(IBus.Capabilite.PREEDIT_TEXT | IBus.Capabilite.LOOKUP_TABLE |
                                 IBus.Capabilite.FOCUS))
    committed = []
    context.connect('commit-text', lambda ctx, text: committed.append(text.get_text()))
    context.focus_in()
    context.set_engine('anthy')
    pump(1)
    assert context.get_engine().get_name() == 'anthy', 'Anthy engine unavailable'
    print('input-test: Anthy context ready', flush=True)

    def key(name, flags=0):
        # Steam creates/focuses its own input contexts while its UI starts. Reassert this
        # dedicated test context so boot-time focus changes cannot drop part of the reading.
        context.focus_in()
        pump(0.03)
        value = IBus.keyval_from_name(name) if len(name) > 1 else ord(name)
        context.process_key_event(value, 0, flags)
        context.process_key_event(value, 0, flags | int(IBus.ModifierType.RELEASE_MASK))
        pump()

    def japanese():
        for char in 'nihongo':
            key(char)
        key('space')
        key('Return')
        pump(0.5)
        result = ''.join(committed)
        assert '日本語' in result, 'Japanese conversion failed: '+repr(result)
        committed.clear()
        return result

    key('Hiragana')
    first = japanese()
    print('input-test: Kana conversion '+first, flush=True)
    # Eisu must be idempotent and return to direct Latin, rather than toggling an engine.
    key('Muhenkan')
    key('Muhenkan')
    result = context.process_key_event(ord('a'), 0, 0)
    pump()
    assert not result or ''.join(committed) == 'a', 'Eisu did not restore direct Latin'
    committed.clear()
    key('space', int(IBus.ModifierType.CONTROL_MASK))
    second = japanese()
    key('Muhenkan')  # leave the test context in direct mode
    context.focus_out()
    context.destroy()
    return {'kana_conversion': first, 'ctrl_space_conversion': second, 'eisu_direct': True}


def test_xwaylands():
    lib = C.CDLL('libX11.so.6')
    lib.XOpenDisplay.argtypes = [C.c_char_p]
    lib.XOpenDisplay.restype = C.c_void_p
    lib.XCloseDisplay.argtypes = [C.c_void_p]
    lib.XDefaultRootWindow.argtypes = [C.c_void_p]
    lib.XDefaultRootWindow.restype = C.c_ulong
    lib.XInternAtom.argtypes = [C.c_void_p, C.c_char_p, C.c_int]
    lib.XInternAtom.restype = C.c_ulong
    lib.XkbKeycodeToKeysym.argtypes = [C.c_void_p, C.c_ubyte, C.c_int, C.c_int]
    lib.XkbKeycodeToKeysym.restype = C.c_ulong
    lib.XGetWindowProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long,
                                      C.c_int, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_int),
                                      C.POINTER(C.c_ulong), C.POINTER(C.c_ulong), C.POINTER(C.c_void_p)]
    lib.XGetSelectionOwner.argtypes = [C.c_void_p, C.c_ulong]
    lib.XGetSelectionOwner.restype = C.c_ulong
    lib.XFree.argtypes = [C.c_void_p]
    layout = 'jp' if 'steamac.keyboard=jis' in Path('/proc/cmdline').read_text().split() else 'us'
    results = []
    for socket in sorted(Path('/tmp/.X11-unix').glob('X[0-9]*')):
        display = ':'+socket.name[1:]
        connection = lib.XOpenDisplay(display.encode())
        assert connection, 'Cannot open '+display
        try:
            # Physical Shift+2 and the key to the right of P differ between JIS and US.
            shift_2 = lib.XkbKeycodeToKeysym(connection, 11, 0, 1)
            after_p = lib.XkbKeycodeToKeysym(connection, 34, 0, 0)
            assert (shift_2, after_p) == ((ord('"'), ord('@')) if layout == 'jp' else (ord('@'), ord('['))), \
                f'{display}: wrong physical punctuation: {shift_2} {after_p}'
            atom = lib.XInternAtom(connection, b'XIM_SERVERS', True)
            actual = C.c_ulong(); fmt = C.c_int(); count = C.c_ulong(); remaining = C.c_ulong(); data = C.c_void_p()
            status = lib.XGetWindowProperty(connection, lib.XDefaultRootWindow(connection), atom, 0, 128,
                                           False, 4, C.byref(actual), C.byref(fmt), C.byref(count),
                                           C.byref(remaining), C.byref(data))
            assert status == 0 and fmt.value == 32 and count.value > 0, display+': no XIM server registered'
            atoms = C.cast(data, C.POINTER(C.c_ulong))
            assert any(lib.XGetSelectionOwner(connection, atoms[i]) for i in range(count.value)), display+': no XIM owner'
            lib.XFree(data)
            results.append({'display': display, 'layout': layout, 'xim_registered': True})
        finally:
            lib.XCloseDisplay(connection)
    assert len(results) >= 2, 'Both Steam and game Xwaylands must be checked'
    return results


def test_refresh():
    output = subprocess.check_output(['xrandr', '--current'], text=True, timeout=10)
    rates = [float(rate) for rate in re.findall(r'([0-9]+\.[0-9]+)\*', output)]
    assert rates and all(abs(rate-60) < 0.2 for rate in rates), 'Guest display is not at 60 Hz: '+output
    return rates


if __name__ == '__main__':
    print('JAPANESE_INPUT_RESULT '+json.dumps({'engine': test_engine(), 'xwaylands': test_xwaylands(),
                                            'guest_refresh_hz': test_refresh()},
                                           ensure_ascii=False), flush=True)
