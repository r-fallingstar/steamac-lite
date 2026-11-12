#!/usr/bin/env python3
"""Small isolated fixtures: no Btrfs, installed Proton, VM, build, or large copy."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    result = importlib.util.module_from_spec(spec)
    loader.exec_module(result)
    return result


m = module("camera_prepare_proton", ROOT / "guest/camera/prepare-proton.py")
setup = module("camera_vrchat_setup", ROOT / "guest/layer/usr/lib/steamac/vrchat-setup")
VDF = runpy.run_path(str(ROOT / "guest/layer/usr/lib/steamac/steam-title-defaults"))
ORIGINAL = '''"InstallConfigStore" { "Software" { "Valve" { "Steam" {
// These settings and all other games must survive unchanged.
"Language" "japanese" "CompatToolMapping" {
"0" { "name" "proton-stable" } "42" { "name" "my-personal-tool" }
"438100" { "name" "proton_experimental" "config" "" "priority" "250" }
} } } } }'''
LOCAL = '"UserLocalConfigStore" { "Other" "keep" }'


class PreparationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.steam = self.base / "Steam"
        self.bundle = self.base / "bundle"
        self.stock = self.steam / "steamapps/common/Proton - Experimental"
        self.target = self.steam / "compatibilitytools.d" / m.DIRECTORY
        self.config = self.steam / "config/config.vdf"
        self.local = self.steam / "userdata/1234/config/localconfig.vdf"
        self.manifest = self.steam / "steamapps/appmanifest_1493710.acf"
        for relative, data in {
            "version": b"experimental-known-x86_64\n",
            m.PE: b"stock PE",
            m.UNIX: b"stock Unix qcap",
            "proton": b"#!/bin/sh\n# stock executable launcher\n",
            "toolmanifest.vdf": b'"manifest" { "require_tool_appid" "3127680" "compatmanager_layer_name" "proton" "arch" "x86_64" }\n',
            "files/bin/wine64": b"stock wine64",
        }.items():
            path = self.stock / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (self.stock / "proton").chmod(0o755)
        (self.stock / "files/bin/wine").symlink_to("wine64")
        # A copied descriptor must be replaced, not retain the stock tool's identity.
        (self.stock / "compatibilitytool.vdf").write_text('"stock-descriptor" {}')
        self.bundle.mkdir()
        (self.bundle / "proton").mkdir()
        (self.bundle / "proton/qcap.dll").write_bytes(b"patched camera PE")
        self.pins = {key: m.digest(self.stock / relative) for relative, key in m.PINS.items()}
        self.pins["patched_pe_sha256"] = m.digest(self.bundle / "proton/qcap.dll")
        (self.bundle / "proton-camera.json").write_text(json.dumps(self.pins))
        VDF["atomic_write"](self.manifest, '"AppState" { "appid" "1493710" "StateFlags" "4" "installdir" "Proton - Experimental" }')
        VDF["atomic_write"](self.config, ORIGINAL)
        VDF["atomic_write"](self.local, LOCAL)
        self.clone_count = 0
        self.messages = []
        self.source_before = self.inventory(self.stock)

    @staticmethod
    def inventory(root):
        return {str(path.relative_to(root)): (os.readlink(path) if path.is_symlink() else path.read_bytes(),
                                              path.lstat().st_mode, path.lstat().st_ino)
                for path in root.rglob("*") if path.is_symlink() or path.is_file()}

    def clone(self, source, destination):
        self.clone_count += 1
        shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True)

    def prepare(self, **kwargs):
        options = dict(bundle=self.bundle, vdf=VDF, clone=self.clone,
                       is_busy=lambda: False, report=self.messages.append)
        options.update(kwargs)
        return m.prepare(self.steam, self.stock, **options)

    def auto(self, **kwargs):
        options = dict(bundle=self.bundle, vdf=VDF, clone=self.clone,
                       is_busy=lambda: False, report=self.messages.append)
        options.update(kwargs)
        return m.auto(self.steam, **options)

    def assert_source_unchanged(self):
        self.assertEqual(self.inventory(self.stock), self.source_before)

    def assert_not_published(self):
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.target.parent.glob(".steamac-camera-stage-*")))
        self.assertEqual(self.config.read_text(), ORIGINAL)
        self.assert_source_unchanged()

    def test_private_snapshot_descriptor_receipt_and_source_isolation(self):
        self.assertEqual(self.auto(), m.NAME)
        self.assertEqual(self.clone_count, 1)
        self.assert_source_unchanged()
        self.assertEqual((self.target / m.PE).read_bytes(), b"patched camera PE")
        for relative in (m.UNIX, "version", "toolmanifest.vdf", "proton", "files/bin/wine64"):
            self.assertEqual((self.target / relative).read_bytes(), (self.stock / relative).read_bytes())
            self.assertFalse(os.path.samestat((self.target / relative).stat(), (self.stock / relative).stat()))
        self.assertEqual((self.target / "proton").stat().st_mode & 0o777, 0o755)
        self.assertEqual(os.readlink(self.target / "files/bin/wine"), "wine64")
        values = VDF["vdf_entries"]((self.target / "compatibilitytool.vdf").read_text())[0]
        prefix = ("compatibilitytools", "compat_tools", m.NAME)
        self.assertEqual(values[(*prefix, "display_name")][0], "Proton Experimental (steamac Camera)")
        self.assertEqual(values[(*prefix, "install_path")][0], ".")
        self.assertEqual(values[(*prefix, "from_oslist")][0], "windows")
        self.assertEqual(values[(*prefix, "to_oslist")][0], "linux")
        receipt = json.loads((self.target / m.RECEIPT).read_text())
        self.assertEqual(receipt["pins"], self.pins)
        self.assertEqual(set(receipt["files"]), set(m.CORE))
        self.assertTrue(m.ready_tool(self.steam))
        self.assertEqual(self.config.read_text().replace(m.NAME, "proton_experimental"), ORIGINAL)
        self.assertEqual((self.config.parent / "steamac-camera-config-before.vdf").read_text(), ORIGINAL)
        self.assertEqual(self.local.read_text(), LOCAL)
        # Either tree can subsequently change without mutating the other.
        (self.stock / "files/bin/wine64").write_bytes(b"new Steam wine")
        self.assertEqual((self.target / "files/bin/wine64").read_bytes(), b"stock wine64")
        (self.target / m.PE).write_bytes(b"private edit")
        self.assertEqual((self.stock / m.PE).read_bytes(), b"stock PE")

    def test_unchanged_reuse_writes_nothing(self):
        self.assertEqual(self.auto(), m.NAME)
        before = self.inventory(self.target)
        stats = {path: path.stat().st_mtime_ns for path in (self.config, self.target / m.RECEIPT,
                                                         self.config.parent / "steamac-camera-config-before.vdf")}
        self.assertEqual(self.auto(), m.NAME)
        self.assertEqual(self.clone_count, 1)
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual({path: path.stat().st_mtime_ns for path in stats}, stats)

    def test_unknown_stock_pins_refuse_first_creation(self):
        for relative in m.PINS:
            with self.subTest(relative=relative):
                path = self.stock / relative
                original = path.read_bytes()
                path.write_bytes(original + b"future version")
                changed = self.inventory(self.stock)
                self.assertIsNone(self.auto())
                self.assertEqual(self.clone_count, 0)
                self.assertFalse(self.target.exists())
                self.assertEqual(self.inventory(self.stock), changed)
                self.assertEqual(self.config.read_text(), ORIGINAL)
                path.write_bytes(original)

    def test_known_copy_survives_unknown_stock_and_changed_bundle(self):
        self.assertEqual(self.auto(), m.NAME)
        before = self.inventory(self.target)
        for relative in (*m.PINS, "toolmanifest.vdf", "proton", "files/bin/wine64"):
            path = self.stock / relative
            path.write_bytes(path.read_bytes() + b"future unknown stock")
        (self.bundle / "proton-camera.json").write_text('{}')
        self.assertTrue(m.ready_tool(self.steam))
        self.assertEqual(self.auto(), m.NAME)
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.clone_count, 1)
        # Re-select a validated snapshot after reverting to the standard choice.
        self.config.write_text(ORIGINAL)
        self.assertEqual(self.auto(), m.NAME)
        self.assertEqual(self.clone_count, 1)

    def test_corrupted_bundle_never_clones(self):
        for key in (*m.PINS.values(), "patched_pe_sha256"):
            with self.subTest(key=key):
                bad = dict(self.pins, **{key: "bad"})
                (self.bundle / "proton-camera.json").write_text(json.dumps(bad))
                self.assertIsNone(self.prepare())
                self.assert_not_published()
        (self.bundle / "proton-camera.json").write_text(json.dumps(self.pins))
        (self.bundle / "proton/qcap.dll").write_bytes(b"corrupted")
        self.assertIsNone(self.prepare())
        self.assertEqual(self.clone_count, 0)
        self.assert_not_published()

    def test_busy_before_prepare_or_auto_does_nothing(self):
        for call in (self.prepare, self.auto):
            self.assertIsNone(call(is_busy=lambda: True))
            self.assert_not_published()
        self.assertEqual(self.clone_count, 0)
        self.assertFalse(self.target.parent.exists())

    def test_busy_prior_copy_is_not_replaced_or_mapped(self):
        self.assertEqual(self.prepare(), m.NAME)
        before = self.inventory(self.target)
        self.assertIsNone(self.auto(is_busy=lambda: True))
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.config.read_text(), ORIGINAL)

    def test_busy_after_clone_discards_stage(self):
        checks = iter((False, True))
        self.assertIsNone(self.prepare(is_busy=lambda: next(checks)))
        self.assert_not_published()

    def test_busy_after_publish_does_not_map(self):
        checks = iter((False, False, False, True))
        self.assertIsNone(self.auto(is_busy=lambda: next(checks)))
        self.assertTrue(m.ready_tool(self.steam))
        self.assertEqual(self.config.read_text(), ORIGINAL)

    def test_custom_mapping_is_preserved_without_a_clone(self):
        for name in ("Proton-GE-personal", "proton-stable", "proton-rtsp-11", m.NAME):
            with self.subTest(name=name):
                custom = ORIGINAL.replace("proton_experimental", name)
                self.config.write_text(custom)
                self.assertIsNone(self.auto())
                self.assertEqual(self.config.read_text(), custom)
                self.assertFalse(self.target.exists())
        self.assertEqual(self.clone_count, 0)
        self.assertEqual(self.local.read_text(), LOCAL)

    def test_custom_choice_wins_even_with_valid_managed_tool(self):
        self.assertEqual(self.prepare(), m.NAME)
        custom = ORIGINAL.replace("proton_experimental", "Proton-GE-personal")
        self.config.write_text(custom)
        before = self.inventory(self.target)
        self.assertIsNone(self.auto())
        self.assertEqual(self.config.read_text(), custom)
        self.assertEqual(self.inventory(self.target), before)

    def test_empty_and_absent_mapping_are_allowed(self):
        for current in ("", None):
            with self.subTest(current=current):
                text = VDF["vdf_set"](ORIGINAL, (*m.MAPPING, "name"), current)
                self.config.write_text(text)
                self.assertEqual(self.auto(), m.NAME)
                self.assertEqual(m.mapping_name(self.config.read_text(), VDF), m.NAME)
        self.assertEqual(self.clone_count, 1)

    def test_failed_clone_leaves_no_published_tool(self):
        def broken(source, stage):
            (stage / "partial-copy").write_bytes(b"partial")
            raise OSError("reflink unsupported")
        self.assertIsNone(self.auto(clone=broken))
        self.assert_not_published()
        self.assertTrue(any("reflink unsupported" in message for message in self.messages))
        self.assertEqual(self.prepare(), m.NAME)  # Clean retry works.

    def test_failed_independent_copy_is_not_retried(self):
        stage = self.base / "empty-stage"
        stage.mkdir()
        with patch.object(m.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "cp")) as run:
            with self.assertRaisesRegex(ValueError, "independent camera runtime copy failed"):
                m.clone_reflink(self.stock, stage)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["cp", "-a", "--reflink=auto", str(self.stock) + "/.", str(stage)])

    def test_low_space_does_not_start_copy(self):
        stage = self.base / "empty-stage"
        stage.mkdir()
        from types import SimpleNamespace
        with patch.object(m.shutil, "disk_usage", return_value=SimpleNamespace(free=0)), \
             patch.object(m.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "not enough space"):
                m.clone_reflink(self.stock, stage)
        run.assert_not_called()
        self.assert_source_unchanged()

    def test_cross_filesystem_is_refused_before_clone(self):
        real_stat = Path.stat
        resolved_stock = self.stock.resolve()
        def stat(path, *args, **kwargs):
            result = real_stat(path, *args, **kwargs)
            if path == resolved_stock:
                fields = list(result)
                fields[2] += 1  # st_dev
                return os.stat_result(fields)
            return result
        with patch.object(Path, "stat", stat):
            self.assertIsNone(self.prepare())
        self.assertEqual(self.clone_count, 0)
        self.assert_not_published()

    def test_hardlink_clone_is_rejected_without_touching_stock(self):
        def hardlinks(source, stage):
            shutil.copytree(source, stage, dirs_exist_ok=True, symlinks=True, copy_function=os.link)
        self.assertIsNone(self.prepare(clone=hardlinks))
        self.assert_not_published()

    def test_external_source_symlink_is_rejected(self):
        (self.stock / "files/bin/escape").symlink_to(self.stock / "proton")
        changed = self.inventory(self.stock)
        self.assertIsNone(self.prepare())
        self.assertFalse(self.target.exists())
        self.assertEqual(self.inventory(self.stock), changed)

    def test_source_cannot_overlap_private_directory(self):
        self.target.parent.symlink_to(self.stock, target_is_directory=True)
        self.assertIsNone(self.prepare())
        self.assert_source_unchanged()
        self.assertFalse((self.stock / ".steamac-camera.lock").exists())

    def test_stock_change_during_clone_is_not_published(self):
        def changing(source, stage):
            self.clone(source, stage)
            (source / "version").write_bytes(b"new download x86_64")
        self.assertIsNone(self.prepare(clone=changing))
        self.assertFalse(self.target.exists())
        self.assertEqual(self.config.read_text(), ORIGINAL)

    def test_mapping_change_during_clone_wins(self):
        custom = ORIGINAL.replace("proton_experimental", "user-change")
        def changing(source, stage):
            self.clone(source, stage)
            self.config.write_text(custom)
        self.assertIsNone(self.auto(clone=changing))
        self.assertEqual(self.config.read_text(), custom)
        self.assertTrue(m.ready_tool(self.steam))

    def test_failed_receipt_or_publication_discards_stage(self):
        write = VDF["atomic_write"]
        def fail_receipt(path, text):
            if path.name == m.RECEIPT:
                raise OSError("receipt failure")
            write(path, text)
        with self.subTest(failure="receipt"):
            self.assertIsNone(self.prepare(vdf=dict(VDF, atomic_write=fail_receipt)))
            self.assert_not_published()
        with self.subTest(failure="rename"), patch.object(m.os, "rename", side_effect=OSError("publish failure")):
            self.assertIsNone(self.prepare())
            self.assert_not_published()

    def test_unowned_or_damaged_existing_tool_is_never_replaced(self):
        self.target.mkdir(parents=True)
        (self.target / "user-data").write_bytes(b"keep me")
        self.assertIsNone(self.prepare())
        self.assertEqual((self.target / "user-data").read_bytes(), b"keep me")
        shutil.rmtree(self.target)
        self.assertEqual(self.prepare(), m.NAME)
        for relative in (*m.CORE, m.RECEIPT):
            with self.subTest(relative=relative):
                path = self.target / relative
                before = path.read_bytes()
                path.write_bytes(b"broken")
                self.assertFalse(m.ready_tool(self.steam))
                self.assertIsNone(self.prepare())
                self.assertEqual(path.read_bytes(), b"broken")
                path.write_bytes(before)
        self.assertEqual(self.clone_count, 1)

    def test_receipt_with_missing_source_pin_is_not_owned(self):
        self.assertEqual(self.prepare(), m.NAME)
        path = self.target / m.RECEIPT
        receipt = json.loads(path.read_text())
        del receipt["pins"]["stock_pe_sha256"]
        path.write_text(json.dumps(receipt))
        self.assertFalse(m.ready_tool(self.steam))
        self.assertIsNone(self.prepare())
        self.assertEqual(self.clone_count, 1)

    def test_fully_ready_external_library_with_quoted_path(self):
        library = self.base / '日本語 "external" Library'
        external = library / "steamapps/common/Proton - Experimental"
        external.parent.mkdir(parents=True)
        self.stock.rename(external)
        self.manifest.rename(library / "steamapps/appmanifest_1493710.acf")
        (self.steam / "steamapps/libraryfolders.vdf").write_text(
            '"libraryfolders" { "1" { "path" ' + VDF["vdf_quote"](str(library)) + ' } }')
        self.assertEqual(m.installed_stock(self.steam, VDF), external)
        self.assertEqual(self.auto(), m.NAME)

    def test_partial_missing_or_unsafe_stock_is_not_used(self):
        original = self.manifest.read_text()
        for text in (original.replace('"4"', '"1026"'), original.replace('Proton - Experimental', '..')):
            self.manifest.write_text(text)
            self.assertIsNone(self.auto())
        self.manifest.unlink()
        self.assertIsNone(self.auto())
        self.assertEqual(self.clone_count, 0)
        self.assert_not_published()

    def test_incomplete_or_wrong_architecture_stock_is_not_used(self):
        (self.stock / "proton").unlink()
        self.assertIsNone(self.prepare())
        (self.stock / "proton").write_bytes(b"restored")
        (self.stock / "version").write_text("experimental-arm64ec")
        self.assertIsNone(self.prepare())
        self.assertEqual(self.clone_count, 0)
        self.assertFalse(self.target.exists())

    def test_guard_checks_steam_fex_and_wine_and_fails_closed(self):
        for code, expected in ((0, True), (1, False), (2, True)):
            with patch.object(m.subprocess, "run", return_value=Mock(returncode=code)) as run:
                self.assertEqual(m.processes_busy(), expected)
                command = run.call_args.args[0]
                self.assertIn("steam", command[-1])
                self.assertIn("FEX.*", command[-1])
                self.assertIn("wine.*", command[-1])
        with patch.object(m.subprocess, "run", side_effect=OSError("no pgrep")):
            self.assertTrue(m.processes_busy())

    def test_invalid_bundle_shape_and_symlink_loop_fail_safely(self):
        (self.bundle / "proton-camera.json").write_text('[]')
        self.assertIsNone(self.auto())
        self.assert_not_published()
        (self.bundle / "proton-camera.json").write_text(json.dumps(self.pins))
        (self.stock / "loop").symlink_to("loop")
        self.assertIsNone(self.auto())
        self.assertFalse(self.target.exists())
        self.assertEqual(self.config.read_text(), ORIGINAL)

    def test_another_preparation_holding_lock_is_not_disturbed(self):
        self.target.parent.mkdir(parents=True)
        with (self.target.parent / ".steamac-camera.lock").open("a") as lock:
            m.fcntl.flock(lock, m.fcntl.LOCK_EX | m.fcntl.LOCK_NB)
            self.assertIsNone(self.prepare())
        self.assertEqual(self.clone_count, 0)
        self.assert_not_published()

    def test_receipt_is_validated_before_publication(self):
        write = VDF["atomic_write"]
        def corrupt_receipt(path, text):
            write(path, '{}' if path.name == m.RECEIPT else text)
        self.assertIsNone(self.prepare(vdf=dict(VDF, atomic_write=corrupt_receipt)))
        self.assert_not_published()

    def test_cli_auto_dispatch_and_fail_open_when_no_steam_config(self):
        with patch.dict(os.environ, {"STEAMAC_STEAM_ROOT": str(self.steam)}), \
                patch.object(m.sys, "argv", ["prepare-proton.py", "--auto"]), \
                patch.object(m, "auto") as auto:
            m.main()
        auto.assert_called_once_with(self.steam)
        self.config.unlink()
        self.assertIsNone(self.auto())
        self.assertFalse(self.target.exists())

    def test_mapping_write_failure_retains_stock_and_ready_private_tool(self):
        write = VDF["atomic_write"]
        def fail_config(path, text):
            if path == self.config:
                raise OSError("mapping write failure")
            write(path, text)
        self.assertIsNone(self.auto(vdf=dict(VDF, atomic_write=fail_config)))
        self.assertEqual(self.config.read_text(), ORIGINAL)
        self.assertTrue(m.ready_tool(self.steam))
        self.assertEqual(self.auto(), m.NAME)
        self.assertEqual(self.clone_count, 1)

    def configure_fixture(self):
        setup.STEAM, setup.STATE = self.steam, self.base / "setup-state"
        setup.STATE.mkdir(exist_ok=True)
        self.eac, self.fex = self.base / "EAC", self.base / "FEX"
        self.eac.mkdir(exist_ok=True)
        self.fex.mkdir(exist_ok=True)
        def prepare(steam, stock, **kwargs):
            return m.prepare(steam, stock, bundle=self.bundle, clone=self.clone,
                             is_busy=lambda: False, report=self.messages.append, **kwargs)
        api = {"prepare": prepare, "ready_tool": m.ready_tool}
        for name, replacement in {
            "camera_api": lambda: api,
            "steam_running": lambda: False,
            "busy": lambda: False,
            "tool": lambda appid: {"1493710": self.stock, "1826330": self.eac, "3127680": self.fex}[appid],
            "install_fex": Mock(),
            "validate_payload": lambda: ({"commit": "fixture-fex"}, None),
        }.items():
            context = patch.object(setup, name, replacement)
            context.start()
            self.addCleanup(context.stop)

    def test_setup_selects_private_tool_and_preserves_custom_launch_flags(self):
        self.configure_fixture()
        launch = setup.launch_options(self.eac) + " --my-custom-flag"
        self.local.write_text(VDF["vdf_set"](LOCAL, setup.LAUNCH, launch))
        setup.configure(self.local)
        self.assertEqual(m.mapping_name(self.config.read_text(), VDF), m.NAME)
        self.assertEqual(setup.value(self.local.read_text(), setup.LAUNCH), launch)
        self.assertFalse(setup.conflicts(self.local))
        self.assertEqual((setup.STATE / "config-backups/1234/config.vdf").read_text(), ORIGINAL)
        setup.configure(self.local)
        self.assertEqual(self.clone_count, 1)
        setup.install_fex.assert_called_with(self.fex)
        self.assert_source_unchanged()

    def test_setup_camera_failure_falls_back_to_standard(self):
        self.configure_fixture()
        (self.bundle / "proton/qcap.dll").write_bytes(b"bad bundle")
        setup.configure(self.local)
        self.assertEqual(m.mapping_name(self.config.read_text(), VDF), "proton_experimental")
        self.assertTrue(setup.compatible_launch(setup.value(self.local.read_text(), setup.LAUNCH)))
        self.assert_source_unchanged()

    def test_setup_keeps_prior_valid_copy_after_stock_update(self):
        self.configure_fixture()
        self.assertEqual(self.prepare(), m.NAME)
        before = self.inventory(self.target)
        (self.stock / "version").write_bytes(b"future-unknown-arm64ec")
        (self.stock / m.UNIX).write_bytes(b"future Unix qcap")
        setup.configure(self.local)
        self.assertEqual(m.mapping_name(self.config.read_text(), VDF), m.NAME)
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.clone_count, 1)
        self.assertEqual(setup.load(setup.STATE / "complete.json")["proton_version"], "experimental-known-x86_64")

    def test_setup_never_changes_custom_proton_even_with_replace(self):
        self.configure_fixture()
        for name in ("user-proton", m.NAME):  # Managed name without ownership is custom too.
            custom = ORIGINAL.replace("proton_experimental", name)
            self.config.write_text(custom)
            for replace in (False, True):
                with self.assertRaisesRegex(RuntimeError, "custom-settings"):
                    setup.configure(self.local, replace=replace)
                self.assertEqual(self.config.read_text(), custom)
                self.assertEqual(self.local.read_text(), LOCAL)
        setup.install_fex.assert_not_called()
        self.assertEqual(self.clone_count, 0)

    def test_setup_preserves_localconfig_replace_policy(self):
        self.configure_fixture()
        launch = 'my-wrapper %command% --flag'
        self.local.write_text(VDF["vdf_set"](LOCAL, setup.LAUNCH, launch))
        with self.assertRaisesRegex(RuntimeError, "custom-settings"):
            setup.configure(self.local)
        setup.configure(self.local, replace=True)
        self.assertTrue(setup.compatible_launch(setup.value(self.local.read_text(), setup.LAUNCH)))
        self.assertEqual(setup.value((setup.STATE / "config-backups/1234/localconfig.vdf").read_text(), setup.LAUNCH), launch)


if __name__ == "__main__":
    unittest.main()
