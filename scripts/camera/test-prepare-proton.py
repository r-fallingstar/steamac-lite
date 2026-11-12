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
from types import SimpleNamespace

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
# Independent fixture spelling of the pinned upstream block. Do not read or
# execute a resident Steam/Proton launcher in this native unit suite.
LAUNCHER = b'''#!/usr/bin/env python3
class Prefix:
    def setup(self):
        if True:
            # add Steam ffmpeg libraries to path
            prepend_to_env_str(g_session.env, ld_path_var, steam_linux_path + "/ubuntu12_64/video/:" + steam_linux_path + "/ubuntu12_32/video/:" + steam_linux_path + "/steamrtarm64/video/", ":")
'''


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
            "proton": LAUNCHER,
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

    def add_video(self, suffix=b""):
        self.policy = {"schema": 1, "policy_version": 1,
                       "source_sha256": m.hashlib.sha256(LAUNCHER).hexdigest()}
        (self.bundle / "video-launcher.json").write_text(json.dumps(self.policy))
        files = {}
        for relative in m.VIDEO:
            path = self.bundle / "proton-video" / Path(relative).name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b"fixture rebuilt codec: " + path.name.encode() + suffix)
            files[relative] = m.digest(path)
        manifest = {"schema": 1, "files": files}
        (self.bundle / "proton-video.json").write_text(json.dumps(manifest))
        return manifest

    def assert_video(self, manifest):
        self.assertTrue(m.ready_tool(self.steam))
        receipt = json.loads((self.target / m.RECEIPT).read_text())
        self.assertEqual(receipt["schema"], 3)
        self.assertEqual(receipt["video"], manifest)
        self.assertEqual(receipt["launcher"]["policy"], self.policy)
        self.assertEqual(receipt["launcher"]["patched_sha256"], m.digest(self.target / "proton"))
        self.assertEqual(m.original_video_launcher((self.target / "proton").read_bytes(),
                                                  receipt["launcher"]), LAUNCHER)
        self.assertEqual(set(receipt["files"]), set(m.CORE) | set(m.VIDEO))
        for relative in m.VIDEO:
            self.assertEqual(m.digest(self.target / relative), manifest["files"][relative])
            self.assertEqual(receipt["files"][relative], manifest["files"][relative])
            self.assertFalse((self.target / relative).is_symlink())
        self.assertEqual((self.target / m.PE).read_bytes(), b"patched camera PE")
        self.assertEqual((self.target / "compatibilitytool.vdf").read_text(), m.DESCRIPTOR)
        self.assertFalse((self.target.parent / m.BACKUP).exists())
        self.assertFalse((self.target.parent / m.CLEANUP).exists())
        self.assertFalse(list(self.target.parent.glob(".steamac-camera-stage-*")))
        self.assertEqual(self.local.read_text(), LOCAL)

    def legacy_video_fixture(self):
        self.assertEqual(self.auto(), m.NAME)
        self.assertEqual(json.loads((self.target / m.RECEIPT).read_text())["schema"], 1)
        return self.inventory(self.target), self.add_video()

    def test_video_first_install_uses_pinned_stock_and_schema3(self):
        manifest = self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assert_source_unchanged()
        self.assertEqual(self.clone_count, 1)

    def test_video_legacy_upgrade_clones_owned_source_without_mutation(self):
        before, manifest = self.legacy_video_fixture()
        config = self.config.read_bytes()
        rename = m.os.rename

        def observe_rename(source, destination):
            if source == self.target:
                self.assertEqual(self.inventory(self.target), before)
            rename(source, destination)

        def clone(source, stage):
            self.assertEqual(source, self.target)
            self.clone(source, stage)
            self.assertEqual(self.inventory(source), before)

        with patch.object(m.os, "rename", side_effect=observe_rename):
            self.assertEqual(self.auto(clone=clone), m.NAME)
        self.assert_video(manifest)
        for relative in m.CORE:
            expected = m.patch_video_launcher(before[relative][0], self.policy) if relative == "proton" else before[relative][0]
            self.assertEqual((self.target / relative).read_bytes(), expected)
            self.assertEqual((self.target / relative).stat().st_mode, before[relative][1])
        old_inodes = {entry[2] for entry in before.values()}
        self.assertTrue(old_inodes.isdisjoint(entry[2] for entry in self.inventory(self.target).values()))
        self.assertEqual(self.config.read_bytes(), config)
        self.assertEqual(self.clone_count, 2)
        self.assert_source_unchanged()

    def test_video_current_snapshot_reuse_changes_no_files_or_times(self):
        manifest = self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        before = self.inventory(self.target)
        stats = {path: path.stat().st_mtime_ns for path in (self.config, self.target / m.RECEIPT)}
        self.assertEqual(self.auto(), m.NAME)
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual({path: path.stat().st_mtime_ns for path in stats}, stats)
        self.assertEqual(self.clone_count, 1)
        self.assert_video(manifest)

    def test_video_update_replaces_all_four_as_one_snapshot(self):
        self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        manifest = self.add_video(b" next payload")
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assertEqual(self.clone_count, 2)
        self.assert_source_unchanged()

    def test_video_owned_upgrade_does_not_require_current_stock_or_camera_bundle(self):
        _, manifest = self.legacy_video_fixture()
        (self.stock / "version").write_bytes(b"new unknown arm64ec stock")
        (self.stock / m.UNIX).write_bytes(b"new stock qcap")
        changed = self.inventory(self.stock)
        (self.bundle / "proton-camera.json").write_text('{}')
        (self.bundle / "proton/qcap.dll").unlink()
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assertEqual(self.inventory(self.stock), changed)
        shutil.rmtree(self.stock)
        self.manifest.unlink()
        manifest = self.add_video(b" no stock installed")
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)

    def test_video_unknown_stock_without_owned_snapshot_is_refused(self):
        self.add_video()
        (self.stock / "version").write_bytes(b"new unknown x86_64")
        before = self.inventory(self.stock)
        self.assertIsNone(self.auto())
        self.assertFalse(self.target.exists())
        self.assertEqual(self.clone_count, 0)
        self.assertEqual(self.inventory(self.stock), before)
        self.assertEqual(self.config.read_text(), ORIGINAL)

    def test_video_missing_manifest_preserves_camera_only_and_existing_video(self):
        (self.bundle / "proton-video").mkdir()
        (self.bundle / "proton-video/unrequested.so").write_bytes(b"ignored")
        self.assertEqual(self.auto(), m.NAME)
        self.assertEqual(json.loads((self.target / m.RECEIPT).read_text())["schema"], 1)
        self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        before = self.inventory(self.target)
        (self.bundle / "proton-video.json").unlink()
        self.assertEqual(self.auto(), m.NAME)
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.clone_count, 2)

    def test_video_manifest_requires_exact_whitelist_and_valid_hashes(self):
        before, manifest = self.legacy_video_fixture()
        bad = [[], {}, dict(manifest, schema=2), dict(manifest, schema=True),
               dict(manifest, extra="unexpected"), dict(manifest, files=[])]
        for key in m.VIDEO:
            missing = dict(manifest["files"])
            del missing[key]
            bad.append(dict(manifest, files=missing))
            for checksum in ("bad", "F" * 64, None):
                bad.append(dict(manifest, files=dict(manifest["files"], **{key: checksum})))
        for key in ("../escape", "files/lib/x86_64-linux-gnu/other.so", "/tmp/escape"):
            bad.append(dict(manifest, files=dict(manifest["files"], **{key: "0" * 64})))
        for value in bad:
            with self.subTest(value=value):
                (self.bundle / "proton-video.json").write_text(json.dumps(value))
                self.assertIsNone(self.auto())
                self.assertEqual(self.inventory(self.target), before)
        (self.bundle / "proton-video.json").write_text('{invalid JSON')
        self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.clone_count, 1)

    def test_video_bad_or_missing_payload_never_clones_or_reuses_legacy_as_current(self):
        before, _ = self.legacy_video_fixture()
        for relative in m.VIDEO:
            path = self.bundle / "proton-video" / Path(relative).name
            original = path.read_bytes()
            for replacement in (b"corrupted", None):
                with self.subTest(relative=relative, replacement=replacement):
                    if replacement is None:
                        path.unlink()
                    else:
                        path.write_bytes(replacement)
                    self.assertIsNone(self.auto())
                    self.assertTrue(m.ready_tool(self.steam))  # Camera predicate stays useful.
                    self.assertEqual(self.inventory(self.target), before)
                    path.write_bytes(original)
        self.assertEqual(self.clone_count, 1)

    def test_video_payload_changed_after_validation_is_not_published(self):
        before, _ = self.legacy_video_fixture()
        def changing(source, stage):
            self.clone(source, stage)
            (self.bundle / "proton-video" / Path(m.VIDEO[-1]).name).write_bytes(b"raced payload")
        self.assertIsNone(self.auto(clone=changing))
        self.assertEqual(self.inventory(self.target), before)
        self.assert_source_unchanged()

    def test_video_receipt_validates_own_manifest_and_all_core_and_video_hashes(self):
        self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        path = self.target / m.RECEIPT
        original = path.read_text()
        receipt = json.loads(original)
        for relative in (*m.CORE, *m.VIDEO):
            with self.subTest(relative=relative):
                file = self.target / relative
                data = file.read_bytes()
                file.write_bytes(b"damaged")
                self.assertFalse(m.ready_tool(self.steam))
                self.assertIsNone(self.auto())
                self.assertEqual(file.read_bytes(), b"damaged")
                file.write_bytes(data)
        bad = []
        value = json.loads(original)
        del value["video"]
        bad.append(value)
        for section in ("files", "video"):
            value = json.loads(original)
            files = value[section] if section == "files" else value[section]["files"]
            files[m.VIDEO[0]] = "0" * 64
            bad.append(value)
            value = json.loads(original)
            files = value[section] if section == "files" else value[section]["files"]
            del files[m.VIDEO[0]]
            bad.append(value)
        for value in bad:
            path.write_text(json.dumps(value))
            self.assertFalse(m.ready_tool(self.steam))
            self.assertIsNone(self.prepare())
        path.write_text(original)
        (self.bundle / "proton-video.json").write_text('{}')
        self.assertTrue(m.ready_tool(self.steam))  # Receipt validation is bundle-independent.
        self.assertIsNone(self.auto())  # A present invalid desired bundle still fails closed.
        self.assertEqual(json.loads(path.read_text()), receipt)

    def test_video_failed_publish_rolls_back_original_owned_snapshot(self):
        before, _ = self.legacy_video_fixture()
        rename = m.os.rename
        def fail_publish(source, destination):
            if source.name == "tool":
                raise OSError("injected upgrade publish failure")
            rename(source, destination)
        with patch.object(m.os, "rename", side_effect=fail_publish):
            self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        self.assertTrue(m.ready_tool(self.steam))
        self.assertFalse((self.target.parent / m.BACKUP).exists())
        self.assert_source_unchanged()
        self.assertEqual(self.auto(), m.NAME)

    def test_video_failed_retirement_or_receipt_leaves_legacy_unchanged(self):
        before, _ = self.legacy_video_fixture()
        with patch.object(m.os, "rename", side_effect=OSError("retire failure")):
            self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        write = VDF["atomic_write"]
        def fail_receipt(path, text):
            if path.name == m.RECEIPT:
                raise OSError("receipt failure")
            write(path, text)
        self.assertIsNone(self.auto(vdf=dict(VDF, atomic_write=fail_receipt)))
        self.assertEqual(self.inventory(self.target), before)
        self.assertFalse((self.target.parent / m.BACKUP).exists())

    def test_video_interrupted_rename_recovers_and_upgrades_on_next_auto(self):
        before, manifest = self.legacy_video_fixture()
        rename = m.os.rename
        def crash(source, destination):
            rename(source, destination)
            if source == self.target:
                raise SystemExit("simulated interruption after retiring old tool")
        with patch.object(m.os, "rename", side_effect=crash), self.assertRaises(SystemExit):
            self.auto()
        backup = self.target.parent / m.BACKUP
        self.assertFalse(self.target.exists())
        self.assertEqual(self.inventory(backup), before)
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assert_source_unchanged()

    def test_video_interrupted_after_publication_keeps_new_tool_and_cleans_owned_backup(self):
        _, manifest = self.legacy_video_fixture()
        rename = m.os.rename
        def crash(source, destination):
            rename(source, destination)
            if source.name == "tool":
                raise SystemExit("simulated interruption after publication")
        with patch.object(m.os, "rename", side_effect=crash), self.assertRaises(SystemExit):
            self.auto()
        before = self.inventory(self.target)
        self.assertTrue(m.valid_snapshot(self.target.parent / m.BACKUP))
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.clone_count, 2)

    def test_video_failed_rollback_retains_owned_backup_for_next_startup(self):
        before, manifest = self.legacy_video_fixture()
        rename = m.os.rename
        backup = self.target.parent / m.BACKUP
        def fail(source, destination):
            if source.name == "tool" or source == backup:
                raise OSError("publish and rollback unavailable")
            rename(source, destination)
        with patch.object(m.os, "rename", side_effect=fail):
            self.assertIsNone(self.auto())
        self.assertFalse(self.target.exists())
        self.assertEqual(self.inventory(backup), before)
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)

    def test_video_recovery_restores_camera_even_when_desired_payload_is_bad(self):
        before, _ = self.legacy_video_fixture()
        self.target.rename(self.target.parent / m.BACKUP)
        (self.bundle / "proton-video.json").write_text('{}')
        self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        self.assertTrue(m.ready_tool(self.steam))

    def test_video_unowned_backup_and_conflicting_target_are_never_removed(self):
        before, _ = self.legacy_video_fixture()
        backup = self.target.parent / m.BACKUP
        backup.mkdir()
        (backup / "user-data").write_bytes(b"do not delete")
        saved = self.inventory(backup)
        self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.inventory(backup), saved)
        shutil.rmtree(backup)
        self.target.rename(backup)
        self.target.mkdir()
        (self.target / "user-data").write_bytes(b"conflicting tool")
        saved = self.inventory(self.target)
        self.assertIsNone(self.prepare())
        self.assertEqual(self.inventory(self.target), saved)
        self.assertEqual(self.inventory(backup), before)
        self.assertEqual(self.clone_count, 1)

    def test_video_symlink_backup_or_tool_cannot_claim_ownership(self):
        before, _ = self.legacy_video_fixture()
        backup = self.target.parent / m.BACKUP
        backup.symlink_to(self.target, target_is_directory=True)
        self.assertIsNone(self.prepare())
        self.assertTrue(backup.is_symlink())
        self.assertEqual(self.inventory(self.target), before)
        backup.unlink()
        self.target.rename(backup)
        self.target.symlink_to(backup, target_is_directory=True)
        self.assertIsNone(self.prepare())
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(self.inventory(backup), before)

    def test_video_busy_upgrade_or_recovery_leaves_owned_paths_untouched(self):
        before, _ = self.legacy_video_fixture()
        self.assertIsNone(self.auto(is_busy=lambda: True))
        self.assertEqual(self.inventory(self.target), before)
        checks = iter((False, False, False, True))  # auto, prepare, upgrade guard, pre-rename guard
        self.assertIsNone(self.auto(is_busy=lambda: next(checks)))
        self.assertEqual(self.inventory(self.target), before)
        self.target.rename(self.target.parent / m.BACKUP)
        backup = self.target.parent / m.BACKUP
        checks = iter((False, False, True))
        self.assertIsNone(self.auto(is_busy=lambda: next(checks)))
        self.assertFalse(self.target.exists())
        self.assertEqual(self.inventory(backup), before)

    def test_video_busy_between_renames_rolls_back(self):
        before, _ = self.legacy_video_fixture()
        retired = False
        rename = m.os.rename
        def retire(source, destination):
            nonlocal retired
            rename(source, destination)
            if source == self.target:
                retired = True
        with patch.object(m.os, "rename", side_effect=retire):
            self.assertIsNone(self.auto(is_busy=lambda: retired))
        self.assertEqual(self.inventory(self.target), before)
        self.assertFalse((self.target.parent / m.BACKUP).exists())

    def test_video_custom_mapping_and_change_during_clone_prevent_upgrade(self):
        before, _ = self.legacy_video_fixture()
        custom = ORIGINAL.replace("proton_experimental", "my-custom-Proton")
        self.config.write_text(custom)
        self.assertIsNone(self.auto())
        self.assertIsNone(self.prepare())
        self.assertEqual(self.clone_count, 1)
        self.config.write_text(ORIGINAL.replace("proton_experimental", m.NAME))
        def changing(source, stage):
            self.clone(source, stage)
            self.config.write_text(custom)
        self.assertIsNone(self.auto(clone=changing))
        self.assertEqual(self.config.read_text(), custom)
        self.assertEqual(self.inventory(self.target), before)
        self.assertFalse((self.target.parent / m.BACKUP).exists())

    def test_video_source_core_change_during_clone_is_not_published(self):
        self.legacy_video_fixture()
        def changing(source, stage):
            self.clone(source, stage)
            (source / "proton").write_bytes(b"concurrent source edit")
        self.assertIsNone(self.auto(clone=changing))
        self.assertEqual((self.target / "proton").read_bytes(), b"concurrent source edit")
        self.assertFalse((self.target / m.VIDEO[0]).exists())
        self.assert_source_unchanged()

    def test_video_hardlinked_clone_including_different_source_path_is_rejected(self):
        before, _ = self.legacy_video_fixture()
        def hardlinks(source, stage):
            shutil.copytree(source, stage, dirs_exist_ok=True, symlinks=True, copy_function=os.link)
        self.assertIsNone(self.auto(clone=hardlinks))
        self.assertEqual(self.inventory(self.target), before)
        def crosslink(source, stage):
            self.clone(source, stage)
            os.link(source / "proton", stage / "different-name")
        self.assertIsNone(self.auto(clone=crosslink))
        self.assertEqual(self.inventory(self.target), before)
        self.assert_source_unchanged()

    def test_video_internal_codec_links_are_replaced_without_modifying_referents(self):
        for relative in m.VIDEO:
            path = self.stock / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.with_name(path.name + ".original").write_bytes(b"stock codec referent")
            path.symlink_to(path.name + ".original")
        self.source_before = self.inventory(self.stock)
        self.assertEqual(self.auto(), m.NAME)
        manifest = self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        for relative in m.VIDEO:
            self.assertEqual((self.target / (relative + ".original")).read_bytes(), b"stock codec referent")
        self.assert_source_unchanged()

    def test_video_escaping_payload_or_owned_symlinks_are_refused(self):
        before, _ = self.legacy_video_fixture()
        path = self.bundle / "proton-video" / Path(m.VIDEO[0]).name
        path.unlink()
        path.symlink_to(self.stock / "proton")
        self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        path.unlink()
        self.add_video()
        (self.target / "escape").symlink_to(self.stock / "proton")
        before = self.inventory(self.target)
        self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        self.assert_source_unchanged()

    def test_video_upgrade_has_same_space_and_size_bounds_as_stock_clone(self):
        before, _ = self.legacy_video_fixture()
        from types import SimpleNamespace
        with patch.object(m.shutil, "disk_usage", return_value=SimpleNamespace(free=0)):
            self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        with patch.object(m, "RUNTIME_LIMIT", 1):
            self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        payload_size = sum((self.bundle / "proton-video" / Path(key).name).stat().st_size for key in m.VIDEO)
        with patch.object(m, "RUNTIME_LIMIT", payload_size):
            self.assertIsNone(self.auto())  # Payload fits, but the cloned source plus payload does not.
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.clone_count, 1)

    def test_video_mapping_change_between_renames_rolls_back(self):
        before, _ = self.legacy_video_fixture()
        rename = m.os.rename
        custom = ORIGINAL.replace("proton_experimental", "changed-between-renames")
        def change_mapping(source, destination):
            rename(source, destination)
            if source == self.target:
                self.config.write_text(custom)
        with patch.object(m.os, "rename", side_effect=change_mapping):
            self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.config.read_text(), custom)
        self.assertFalse((self.target.parent / m.BACKUP).exists())

    def test_video_conflicting_path_between_renames_is_preserved_with_owned_backup(self):
        before, _ = self.legacy_video_fixture()
        rename = m.os.rename
        def conflict(source, destination):
            rename(source, destination)
            if source == self.target:
                self.target.mkdir()
                (self.target / "user-data").write_bytes(b"new unowned tool")
        with patch.object(m.os, "rename", side_effect=conflict):
            self.assertIsNone(self.auto())
        conflict_before = self.inventory(self.target)
        backup = self.target.parent / m.BACKUP
        self.assertEqual(self.inventory(backup), before)
        self.assertIsNone(self.prepare())
        self.assertEqual(self.inventory(self.target), conflict_before)
        self.assertEqual(self.inventory(backup), before)

    def test_video_failed_upgrade_clone_leaves_source_owned_and_unchanged(self):
        before, _ = self.legacy_video_fixture()
        def fail_clone(source, stage):
            self.assertEqual(source, self.target)
            (stage / "partial").write_bytes(b"partial copy")
            raise OSError("upgrade copy failed")
        self.assertIsNone(self.auto(clone=fail_clone))
        self.assertEqual(self.inventory(self.target), before)
        self.assertFalse((self.target.parent / m.BACKUP).exists())
        self.assertFalse(list(self.target.parent.glob(".steamac-camera-stage-*")))
        self.assert_source_unchanged()

    def test_video_hash_bad_first_install_is_not_published(self):
        self.add_video()
        path = self.bundle / "proton-video" / Path(m.VIDEO[0]).name
        path.write_bytes(b"wrong codec hash")
        self.assertIsNone(self.auto())
        self.assertEqual(self.clone_count, 0)
        self.assert_not_published()

    def test_video_corrupt_backup_is_not_recovered_or_deleted(self):
        self.legacy_video_fixture()
        backup = self.target.parent / m.BACKUP
        self.target.rename(backup)
        (backup / m.PE).write_bytes(b"damaged backup camera")
        before = self.inventory(backup)
        self.assertIsNone(self.auto())
        self.assertIsNone(self.prepare())
        self.assertFalse(self.target.exists())
        self.assertEqual(self.inventory(backup), before)

    def test_video_publication_requires_the_desired_schema3_receipt(self):
        before, _ = self.legacy_video_fixture()
        old_receipt = (self.target / m.RECEIPT).read_text()
        write = VDF["atomic_write"]
        def stale_receipt(path, text):
            write(path, old_receipt if path.name == m.RECEIPT else text)
        self.assertIsNone(self.auto(vdf=dict(VDF, atomic_write=stale_receipt)))
        self.assertEqual(self.inventory(self.target), before)
        self.assertFalse((self.target.parent / m.BACKUP).exists())

    def test_video_changed_published_target_retains_original_backup(self):
        before, _ = self.legacy_video_fixture()
        config = self.config.read_bytes()
        rename = m.os.rename
        def change_published(source, destination):
            rename(source, destination)
            if source.name == "tool":
                # Even another internally valid receipt is not the staged receipt.
                (self.target / "toolmanifest.vdf").write_bytes(b"changed published manifest")
                path = self.target / m.RECEIPT
                receipt = json.loads(path.read_text())
                receipt["files"]["toolmanifest.vdf"] = m.digest(self.target / "toolmanifest.vdf")
                path.write_text(json.dumps(receipt))
        with patch.object(m.os, "rename", side_effect=change_published):
            self.assertIsNone(self.auto())
        backup = self.target.parent / m.BACKUP
        self.assertEqual(self.inventory(backup), before)
        self.assertTrue(m.valid_snapshot(self.target))
        self.assertFalse((backup.parent / m.CLEANUP).exists())
        self.assertEqual(self.config.read_bytes(), config)
        self.assert_source_unchanged()

    def test_video_damaged_published_target_is_preserved_with_backup(self):
        before, _ = self.legacy_video_fixture()
        rename = m.os.rename
        def damage_published(source, destination):
            rename(source, destination)
            if source.name == "tool":
                (self.target / m.VIDEO[0]).write_bytes(b"damaged published codec")
        with patch.object(m.os, "rename", side_effect=damage_published):
            self.assertIsNone(self.auto())
        damaged = self.inventory(self.target)
        self.assertIsNone(self.prepare())
        self.assertEqual(self.inventory(self.target), damaged)
        self.assertEqual(self.inventory(self.target.parent / m.BACKUP), before)
        self.assertFalse((self.target.parent / m.CLEANUP).exists())
        self.assert_source_unchanged()

    def test_video_disappeared_published_target_keeps_recoverable_backup(self):
        before, manifest = self.legacy_video_fixture()
        config = self.config.read_bytes()
        rename = m.os.rename
        def remove_published(source, destination):
            rename(source, destination)
            if source.name == "tool":
                shutil.rmtree(destination)
        with patch.object(m.os, "rename", side_effect=remove_published):
            self.assertIsNone(self.auto())
        self.assertFalse(self.target.exists())
        self.assertEqual(self.inventory(self.target.parent / m.BACKUP), before)
        self.assertEqual(self.config.read_bytes(), config)
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assert_source_unchanged()

    def test_video_cleanup_guard_cannot_adopt_a_replacement_backup(self):
        before, _ = self.legacy_video_fixture()
        backup = self.target.parent / m.BACKUP
        saved = self.base / "original-backup"
        rename = m.os.rename
        published = False
        def observe_publish(source, destination):
            nonlocal published
            rename(source, destination)
            if source.name == "tool":
                published = True
        def replace_backup():
            if published and not saved.exists():
                backup.rename(saved)
                backup.mkdir()  # Even an empty unowned replacement must survive.
            return False
        with patch.object(m.os, "rename", side_effect=observe_publish):
            self.assertIsNone(self.auto(is_busy=replace_backup))
        self.assertTrue(backup.is_dir())
        self.assertEqual(list(backup.iterdir()), [])
        self.assertEqual(self.inventory(saved), before)
        self.assertFalse((backup.parent / m.CLEANUP).exists())
        self.assertTrue(m.valid_snapshot(self.target))
        self.assert_source_unchanged()

    def interrupted_video_cleanup(self, error):
        _, manifest = self.legacy_video_fixture()
        backup = self.target.parent / m.BACKUP
        remove = m.shutil.rmtree
        def interrupt(path, *args, **kwargs):
            if Path(path) == backup / "files":
                (backup / m.RECEIPT).unlink(missing_ok=True)
                remove(backup / "files/bin")
                raise error
            return remove(path, *args, **kwargs)
        with patch.object(m.shutil, "rmtree", side_effect=interrupt):
            if isinstance(error, OSError):
                self.assertIsNone(self.auto())
            else:
                with self.assertRaises(type(error)):
                    self.auto()
        self.assertTrue(m.valid_snapshot(self.target))
        self.assertFalse(m.valid_snapshot(backup))
        self.assertTrue((backup / m.CLEANUP).is_file())
        self.assertTrue((backup.parent / m.CLEANUP).is_file())
        return manifest, backup

    def test_video_partial_cleanup_error_retries_without_recloning(self):
        manifest, _ = self.interrupted_video_cleanup(OSError("partial cleanup"))
        before = self.inventory(self.target)
        config = self.config.read_bytes()
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.config.read_bytes(), config)
        self.assertEqual(self.clone_count, 2)
        self.assert_source_unchanged()

    def test_video_partial_cleanup_process_interruption_retries(self):
        manifest, _ = self.interrupted_video_cleanup(SystemExit("cleanup interrupted"))
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assertEqual(self.clone_count, 2)
        self.assert_source_unchanged()

    def test_video_partial_cleanup_does_not_delete_replacement_directory_or_symlink(self):
        manifest, backup = self.interrupted_video_cleanup(OSError("partial cleanup"))
        saved = self.base / "saved-partial-backup"
        backup.rename(saved)
        original = self.inventory(saved)
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                if symlink:
                    backup.symlink_to(saved, target_is_directory=True)
                else:
                    backup.mkdir()
                    (backup / "user-data").write_bytes(b"arbitrary unowned directory")
                    # A copied marker does not authorize deleting a different inode.
                    shutil.copyfile(saved / m.CLEANUP, backup / m.CLEANUP)
                replacement = self.inventory(backup)
                self.assertIsNone(self.auto())
                self.assertIsNone(self.prepare())
                self.assertEqual(self.inventory(backup), replacement)
                self.assertEqual(self.inventory(saved), original)
                if symlink:
                    self.assertTrue(backup.is_symlink())
                    backup.unlink()
                else:
                    shutil.rmtree(backup)
        saved.rename(backup)
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assert_source_unchanged()

    def test_video_partial_cleanup_requires_unchanged_published_receipt(self):
        manifest, backup = self.interrupted_video_cleanup(OSError("partial cleanup"))
        before = self.inventory(backup)
        path = self.target / "proton"
        original = path.read_bytes()
        path.write_bytes(b"changed during cleanup interruption")
        self.assertIsNone(self.prepare())
        self.assertEqual(self.inventory(backup), before)
        path.write_bytes(original)
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assert_source_unchanged()

    def test_video_partial_cleanup_invalid_journal_does_not_authorize_deletion(self):
        manifest, backup = self.interrupted_video_cleanup(OSError("partial cleanup"))
        journal = backup.parent / m.CLEANUP
        original = journal.read_text()
        record = json.loads(original)
        before = self.inventory(backup)
        target = self.inventory(self.target)
        invalid = [[], {}, dict(record, schema=True),
                   dict(record, backup_id=[True, record["backup_id"][1]]),
                   dict(record, backup_id=[record["backup_id"][0], -1]),
                   dict(record, target_receipt={}), dict(record, extra="unexpected")]
        for value in invalid:
            with self.subTest(value=value):
                journal.write_text(json.dumps(value))
                self.assertIsNone(self.auto())
                self.assertEqual(self.inventory(backup), before)
                self.assertEqual(self.inventory(self.target), target)
        journal.write_text(original)
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)

    def test_video_partial_cleanup_symlink_markers_are_not_followed(self):
        manifest, backup = self.interrupted_video_cleanup(OSError("partial cleanup"))
        for marker in (backup.parent / m.CLEANUP, backup / m.CLEANUP):
            with self.subTest(marker=marker):
                original = marker.read_bytes()
                marker.unlink()
                marker.symlink_to(self.stock / "proton")
                before = self.inventory(backup)
                self.assertIsNone(self.auto())
                self.assertEqual(self.inventory(backup), before)
                self.assertTrue(marker.is_symlink())
                self.assert_source_unchanged()
                marker.unlink()
                marker.write_bytes(original)
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)

    def test_video_partial_cleanup_missing_inner_marker_is_not_authorized(self):
        _, backup = self.interrupted_video_cleanup(OSError("partial cleanup"))
        (backup / m.CLEANUP).unlink()
        before = self.inventory(backup)
        self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(backup), before)
        self.assertTrue((backup.parent / m.CLEANUP).exists())
        self.assert_source_unchanged()

    def test_video_partial_cleanup_busy_or_custom_mapping_keeps_remaining_backup(self):
        manifest, backup = self.interrupted_video_cleanup(OSError("partial cleanup"))
        before = self.inventory(backup)
        config = self.config.read_text()
        self.assertIsNone(self.prepare(is_busy=lambda: True))
        custom = ORIGINAL.replace("proton_experimental", "user-selected-tool")
        self.config.write_text(custom)
        self.assertIsNone(self.auto())
        self.assertIsNone(self.prepare())
        self.assertEqual(self.config.read_text(), custom)
        self.assertEqual(self.inventory(backup), before)
        self.config.write_text(config)
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)

    def test_video_cleanup_journal_before_inner_marker_is_recoverable(self):
        _, manifest = self.legacy_video_fixture()
        write = VDF["atomic_write"]
        journal = self.target.parent / m.CLEANUP
        def interrupt(path, text):
            write(path, text)
            if path == journal:
                raise SystemExit("journal written, inner marker not yet written")
        with patch.dict(VDF, atomic_write=interrupt), self.assertRaises(SystemExit):
            self.auto()
        self.assertTrue(m.valid_snapshot(self.target.parent / m.BACKUP))
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)

    def test_video_cleanup_interruption_before_empty_backup_rmdir_is_recoverable(self):
        _, manifest = self.legacy_video_fixture()
        backup = self.target.parent / m.BACKUP
        rmdir = Path.rmdir
        def interrupt(path):
            if path == backup:
                raise SystemExit("inner marker removed, rmdir pending")
            return rmdir(path)
        with patch.object(Path, "rmdir", interrupt), self.assertRaises(SystemExit):
            self.auto()
        self.assertEqual(list(backup.iterdir()), [])
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)

    def test_video_cleanup_without_inner_marker_refuses_added_unowned_data(self):
        self.legacy_video_fixture()
        backup = self.target.parent / m.BACKUP
        rmdir = Path.rmdir
        def interrupt(path):
            if path == backup:
                raise SystemExit("empty backup retained")
            return rmdir(path)
        with patch.object(Path, "rmdir", interrupt), self.assertRaises(SystemExit):
            self.auto()
        (backup / "user-data").write_bytes(b"unowned content after cleanup")
        before = self.inventory(backup)
        self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(backup), before)
        self.assertTrue((backup.parent / m.CLEANUP).exists())
        self.assert_source_unchanged()

    def test_video_cleanup_interruption_after_backup_rmdir_is_recoverable(self):
        _, manifest = self.legacy_video_fixture()
        journal = self.target.parent / m.CLEANUP
        unlink = Path.unlink
        def interrupt(path, *args, **kwargs):
            if path == journal:
                raise SystemExit("backup removed, journal removal pending")
            return unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", interrupt), self.assertRaises(SystemExit):
            self.auto()
        self.assertFalse((self.target.parent / m.BACKUP).exists())
        self.assertTrue(journal.exists())
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)

    def schema2_fixture(self):
        """Historical owned video receipt, with the still-unmodified launcher."""
        manifest = self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        (self.target / "proton").write_bytes(LAUNCHER)
        path = self.target / m.RECEIPT
        receipt = json.loads(path.read_text())
        receipt["schema"] = 2
        del receipt["launcher"]
        receipt["files"]["proton"] = m.digest(self.target / "proton")
        path.write_text(json.dumps(receipt))
        self.assertTrue(m.valid_snapshot(self.target))
        return self.inventory(self.target), manifest

    def test_launcher_schema2_upgrade_even_when_codecs_are_unchanged(self):
        before, manifest = self.schema2_fixture()
        config = self.config.read_bytes()
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        for relative in (*m.VIDEO, *(key for key in m.CORE if key != "proton")):
            self.assertEqual((self.target / relative).read_bytes(), before[relative][0])
        self.assertEqual((self.target / "proton").stat().st_mode, before["proton"][1])
        self.assertEqual(self.config.read_bytes(), config)
        self.assertEqual(self.clone_count, 2)
        self.assert_source_unchanged()
        current = self.inventory(self.target)
        self.assertEqual(self.auto(), m.NAME)
        self.assertEqual(self.clone_count, 2)
        self.assertEqual(self.inventory(self.target), current)

    def test_launcher_priority_runs_after_all_three_steam_video_paths(self):
        self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        env = {"LD_LIBRARY_PATH": "/private/files/lib/x86_64-linux-gnu:/other"}
        def prepend(environment, key, value, separator):
            environment[key] = value + separator + environment.get(key, "")
        namespace = {"g_session": SimpleNamespace(env=env), "ld_path_var": "LD_LIBRARY_PATH",
                     "steam_linux_path": "/steam", "g_proton": SimpleNamespace(lib_dir="/private/files/lib/"),
                     "prepend_to_env_str": prepend}
        code = (self.target / "proton").read_bytes()
        exec(compile(code, "fixture-proton", "exec"), namespace)
        namespace["Prefix"]().setup()
        self.assertEqual(env["LD_LIBRARY_PATH"].split(":"), [
            "/private/files/lib/x86_64-linux-gnu", "/steam/ubuntu12_64/video/",
            "/steam/ubuntu12_32/video/", "/steam/steamrtarm64/video/",
            "/private/files/lib/x86_64-linux-gnu", "/other"])
        self.assertEqual(code.count(m.VIDEO_PRIORITY), 1)
        self.assert_source_unchanged()

    def test_launcher_unknown_owned_source_is_not_blindly_rewritten(self):
        for schema in (1, 2):
            with self.subTest(schema=schema):
                if schema == 1:
                    self.assertEqual(self.auto(), m.NAME)
                    self.add_video()
                else:
                    shutil.rmtree(self.target)
                    self.config.write_text(ORIGINAL)
                    self.schema2_fixture()
                path = self.target / "proton"
                path.write_bytes(LAUNCHER + b"# unknown source revision\n")
                receipt_path = self.target / m.RECEIPT
                receipt = json.loads(receipt_path.read_text())
                receipt["files"]["proton"] = m.digest(path)
                receipt_path.write_text(json.dumps(receipt))
                self.assertTrue(m.valid_snapshot(self.target))
                before = self.inventory(self.target)
                count = self.clone_count
                config = self.config.read_bytes()
                self.assertIsNone(self.auto())
                self.assertEqual(self.inventory(self.target), before)
                self.assertEqual(self.clone_count, count)
                self.assertEqual(self.config.read_bytes(), config)
                self.assertFalse((self.target.parent / m.BACKUP).exists())
                self.assert_source_unchanged()

    def test_launcher_unknown_stock_source_refuses_before_clone(self):
        self.add_video()
        (self.stock / "proton").write_bytes(LAUNCHER + b"# new stock\n")
        before = self.inventory(self.stock)
        self.assertIsNone(self.auto())
        self.assertEqual(self.clone_count, 0)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.inventory(self.stock), before)
        self.assertEqual(self.config.read_text(), ORIGINAL)

    def test_launcher_requires_valid_regular_bundled_policy(self):
        before, _ = self.schema2_fixture()
        path = self.bundle / "video-launcher.json"
        original = path.read_bytes()
        invalid = [[], {}, dict(self.policy, schema=True), dict(self.policy, schema=2),
                   dict(self.policy, policy_version=True), dict(self.policy, policy_version=2),
                   dict(self.policy, source_sha256="F" * 64),
                   dict(self.policy, source_sha256=None), dict(self.policy, extra="untrusted")]
        for value in invalid:
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                self.assertIsNone(self.auto())
                self.assertEqual(self.inventory(self.target), before)
        path.write_text('{invalid JSON')
        self.assertIsNone(self.auto())
        path.unlink()
        self.assertIsNone(self.auto())
        saved = self.bundle / "policy-copy.json"
        saved.write_bytes(original)
        path.symlink_to(saved.name)
        self.assertIsNone(self.auto())
        path.unlink()
        self.assertEqual(self.clone_count, 1)
        self.assertEqual(self.inventory(self.target), before)
        path.write_bytes(original)
        self.assertEqual(self.auto(), m.NAME)

    def test_launcher_schema3_missing_policy_does_not_report_current(self):
        self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        before = self.inventory(self.target)
        (self.bundle / "video-launcher.json").unlink()
        self.assertTrue(m.ready_tool(self.steam))
        self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.clone_count, 1)

    def test_launcher_missing_ambiguous_or_prepatched_anchor_fails_closed(self):
        self.add_video()
        for source in (LAUNCHER.replace(b"# add Steam ffmpeg", b"# changed Steam ffmpeg"),
                       LAUNCHER + m.VIDEO_ANCHOR,
                       LAUNCHER + b"# steamac private codec priority (policy 1)\n",
                       LAUNCHER.replace(b"\n", b"\r\n")):
            with self.subTest(source=source):
                (self.stock / "proton").write_bytes(source)
                policy = dict(self.policy, source_sha256=m.hashlib.sha256(source).hexdigest())
                (self.bundle / "video-launcher.json").write_text(json.dumps(policy))
                before = self.inventory(self.stock)
                self.assertIsNone(self.auto())
                self.assertEqual(self.clone_count, 0)
                self.assertFalse(self.target.exists())
                self.assertEqual(self.inventory(self.stock), before)

    def test_launcher_change_after_preflight_cannot_publish(self):
        self.add_video()
        def changing(source, stage):
            (source / "proton").write_bytes(LAUNCHER + b"# race before copy\n")
            self.clone(source, stage)
        self.assertIsNone(self.auto(clone=changing))
        self.assertFalse(self.target.exists())
        self.assertEqual(self.config.read_text(), ORIGINAL)
        self.assertTrue(any("launcher source changed" in text for text in self.messages))

    def test_launcher_schema3_receipt_rejects_forged_patch_and_policy(self):
        self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        path = self.target / m.RECEIPT
        original = json.loads(path.read_text())
        for field, value in (("policy", {}), ("patched_sha256", "0" * 64),
                             ("patched_sha256", True)):
            receipt = json.loads(json.dumps(original))
            receipt["launcher"][field] = value
            path.write_text(json.dumps(receipt))
            self.assertFalse(m.valid_snapshot(self.target))
        receipt = json.loads(json.dumps(original))
        receipt["launcher"]["policy"]["source_sha256"] = "0" * 64
        path.write_text(json.dumps(receipt))
        self.assertFalse(m.valid_snapshot(self.target))
        del receipt["launcher"]
        path.write_text(json.dumps(receipt))
        self.assertFalse(m.valid_snapshot(self.target))
        path.write_text(json.dumps(original))
        launcher = self.target / "proton"
        launcher.write_bytes(launcher.read_bytes() + b"# forged extra code\n")
        original["files"]["proton"] = m.digest(launcher)
        original["launcher"]["patched_sha256"] = m.digest(launcher)
        path.write_text(json.dumps(original))
        self.assertFalse(m.valid_snapshot(self.target))
        before = self.inventory(self.target)
        self.assertIsNone(self.prepare())
        self.assertEqual(self.inventory(self.target), before)

    def test_launcher_schema3_camera_only_bundle_never_downgrades(self):
        self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        before = self.inventory(self.target)
        (self.bundle / "proton-video.json").unlink()
        (self.bundle / "video-launcher.json").unlink()
        self.assertEqual(self.auto(), m.NAME)
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.clone_count, 1)

    def test_launcher_unknown_desired_policy_keeps_schema3_unchanged(self):
        self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        before = self.inventory(self.target)
        policy = dict(self.policy, source_sha256="0" * 64)
        (self.bundle / "video-launcher.json").write_text(json.dumps(policy))
        self.assertIsNone(self.auto())
        self.assertTrue(m.valid_snapshot(self.target))
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.clone_count, 1)

    def test_launcher_schema2_failed_publish_and_rollback_preserve_backup(self):
        before, manifest = self.schema2_fixture()
        backup = self.target.parent / m.BACKUP
        rename = m.os.rename
        def fail(source, destination):
            if source.name == "tool" or source == backup:
                raise OSError("publish and rollback unavailable")
            rename(source, destination)
        with patch.object(m.os, "rename", side_effect=fail):
            self.assertIsNone(self.auto())
        self.assertFalse(self.target.exists())
        self.assertEqual(self.inventory(backup), before)
        self.assertTrue(m.valid_snapshot(backup))
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assert_source_unchanged()

    def test_launcher_schema2_failed_publish_rolls_back_without_mutation(self):
        before, _ = self.schema2_fixture()
        rename = m.os.rename
        def fail(source, destination):
            if source.name == "tool":
                raise OSError("publish unavailable")
            rename(source, destination)
        with patch.object(m.os, "rename", side_effect=fail):
            self.assertIsNone(self.auto())
        self.assertEqual(self.inventory(self.target), before)
        self.assertFalse((self.target.parent / m.BACKUP).exists())
        self.assert_source_unchanged()

    def test_launcher_schema2_upgrade_preserves_busy_and_custom_mapping_guards(self):
        before, _ = self.schema2_fixture()
        self.assertIsNone(self.auto(is_busy=lambda: True))
        custom = ORIGINAL.replace("proton_experimental", "user-custom-tool")
        self.config.write_text(custom)
        self.assertIsNone(self.auto())
        self.assertIsNone(self.prepare())
        self.assertEqual(self.config.read_text(), custom)
        self.assertEqual(self.inventory(self.target), before)
        self.assertEqual(self.clone_count, 1)

    def test_launcher_schema3_codec_update_does_not_insert_twice(self):
        self.add_video()
        self.assertEqual(self.auto(), m.NAME)
        launcher = (self.target / "proton").read_bytes()
        manifest = self.add_video(b" updated codec")
        self.assertEqual(self.auto(), m.NAME)
        self.assert_video(manifest)
        self.assertEqual((self.target / "proton").read_bytes(), launcher)
        self.assertEqual(launcher.count(m.VIDEO_PRIORITY), 1)
        self.assertEqual(self.clone_count, 2)

    def test_bundled_launcher_policy_pins_live_source_not_reference(self):
        policy = m.read_launcher_policy(ROOT / "guest/camera")
        self.assertEqual(policy, {"schema": 1, "policy_version": 1, "source_sha256":
                         "6d0cd1d4196d73a970ed4ce2e569f3a2003beae3beb0c7951fa08c22cd2772a1"})

    def test_stage_camera_includes_regular_nonexecutable_launcher_policy(self):
        stager = module("fixture_stage_camera", ROOT / "scripts/lite/stage-camera.py")
        root = self.base / "staging-root"
        runtime = root / "work/camera-release/runtime"
        app, layer = self.base / "app", self.base / "layer"
        (app / "Contents/Resources").mkdir(parents=True)
        (app / "Contents/Resources/Image").write_bytes(b"fixture kernel")
        (layer / "usr/lib/systemd/system").mkdir(parents=True)
        source = root / "guest/camera"
        source.mkdir(parents=True)
        for name in ("start-camera", "prepare-proton.py", "init-home.py", "proton-camera.json",
                     "video-launcher.json", "NOTICE"):
            shutil.copyfile(ROOT / "guest/camera" / name, source / name)
        (source / "proton-camera.json").write_text(json.dumps(self.pins))
        for name in ("camera-agent", "v4l2loopback.ko", "proton/qcap.dll"):
            path = runtime / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"patched camera PE" if name.endswith("qcap.dll") else b"fixture runtime")
        receipt = {"files": {name: m.digest(runtime / name) for name in
                   ("camera-agent", "v4l2loopback.ko", "proton/qcap.dll")}, "sources": {},
                   "kernel_image_sha256": m.digest(app / "Contents/Resources/Image")}
        (runtime / "build.json").write_text(json.dumps(receipt))
        for relative in ("work/camera-release/wine-source/COPYING.LIB",
                         "work/camera-experiment/v4l2loopback/COPYING",
                         "work/camera-release/glibc-COPYING", "work/camera-release/gcc-COPYING"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture license")
        with patch.object(stager, "ROOT", root), patch.object(stager, "INPUT", runtime):
            stager.stage(layer, app)
        staged = layer / "usr/lib/steamac/camera/video-launcher.json"
        self.assertEqual(staged.read_bytes(), (ROOT / "guest/camera/video-launcher.json").read_bytes())
        self.assertFalse(staged.is_symlink())
        self.assertEqual(staged.stat().st_mode & 0o777, 0o644)

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
