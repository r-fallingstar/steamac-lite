#!/usr/bin/env python3
"""Verify installation boundaries, preservation, rollback and resume without Steam."""
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
source = ROOT/"guest/layer/usr/lib/steamac/vrchat-setup"
loader = importlib.machinery.SourceFileLoader("vrchat_setup", str(source))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        m.STEAM, m.STATE, m.PAYLOAD = base/"Steam", base/"state", base/"payload"
        m.STATE.mkdir(); m.PAYLOAD.mkdir()
        self.config = m.STEAM/"config/config.vdf"
        self.local = m.STEAM/"userdata/1234/config/localconfig.vdf"
        m.atomic_write(self.config, '"InstallConfigStore" { "Software" { "Valve" { "Steam" { "Other" "keep" "CompatToolMapping" { "0" {"name" "proton-stable"} "42" {"name" "mine"} } } } } }')
        m.atomic_write(self.local, '"UserLocalConfigStore" { "Other" "keep" }')
        m.atomic_write(m.STEAM/"config/loginusers.vdf", '"users" { "76561197960266962" { "MostRecent" "1" } }')
        self.paths = {}
        for appid, title in m.TOOLS:
            title = "Proton - Experimental" if appid == "1493710" else title
            directory = m.STEAM/"steamapps/common"/title
            directory.mkdir(parents=True)
            (directory/"version").write_text("experimental-11.0-test-x86_64")
            m.atomic_write(m.STEAM/"steamapps"/f"appmanifest_{appid}.acf", f'"AppState" {{ "StateFlags" "4" "installdir" "{title}" }}')
            self.paths[appid] = directory
        names = ["usr/bin/FEX", "usr/bin/FEXServer", "FEXCompatTool", "VERSIONS.txt", "ConfigTemplate.json"]
        archive = m.PAYLOAD/"runtime.tar.xz"
        hashes = {}
        with tarfile.open(archive, "w:xz") as tar:
            for name in names:
                data = ("patched:"+name).encode()
                member = tarfile.TarInfo("stage/"+name); member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
                hashes[name] = hashlib.sha256(data).hexdigest()
                p = self.paths["3127680"]/name
                p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"valve")
        m.save(m.PAYLOAD/"manifest.json", {"archive":archive.name, "sha256":hashlib.sha256(archive.read_bytes()).hexdigest(), "files":hashes, "commit":"test"})
        self.running = patch.object(m, "steam_running", return_value=False); self.running.start();self.addCleanup(self.running.stop)
        self.busy = patch.object(m, "busy", return_value=False);self.busy.start();self.addCleanup(self.busy.stop)

    def test_account_selection(self):
        self.assertEqual(m.account(), self.local)

    def test_arm_steam_account_without_mostrecent(self):
        path=m.STEAM/"config/loginusers.vdf"
        path.write_text(path.read_text().replace('"MostRecent" "1"','"AllowAutoLogin" "1"'))
        self.assertEqual(m.account(),self.local)

    def test_first_setup_waits_for_login_instead_of_exiting(self):
        (m.STEAM/"config/loginusers.vdf").unlink()
        with patch.object(m,"enabled",return_value=True), patch.object(m,"run_ui") as ui, patch.object(m.sys,"argv",["vrchat-setup"]):
            m.main()
        ui.assert_called_once()

    def test_only_vrchat_and_original_backups(self):
        m.configure(self.local)
        text = self.config.read_text()
        self.assertEqual(m.value(text, (*m.MAPPING,"name")), "proton_experimental")
        self.assertEqual(m.value(text, (*m.MAPPING[:-1],"0","name")), "proton-stable")
        self.assertEqual(m.value(text, (*m.MAPPING[:-1],"42","name")), "mine")
        self.assertEqual((m.STATE/"valve-fex-backup/usr/bin/FEX").read_bytes(), b"valve")
        self.assertFalse(m.load(m.STATE/"complete.json")["vrchat_launched"])
        self.assertTrue(m.compatible_launch(m.value(self.local.read_text(),m.LAUNCH)))

    def test_repeat_and_preserve_user_flags(self):
        m.configure(self.local)
        before = (m.STATE/"config-backups/1234/localconfig.vdf").read_bytes()
        text = self.local.read_text()
        options = m.value(text,m.LAUNCH)+" --custom-user-flag"
        m.atomic_write(self.local,m.set_value(text,m.LAUNCH,options))
        m.configure(self.local)
        self.assertEqual(m.value(self.local.read_text(),m.LAUNCH),options)
        self.assertEqual((m.STATE/"config-backups/1234/localconfig.vdf").read_bytes(),before)

    def test_maintenance_after_valve_tool_update(self):
        m.configure(self.local)
        fex=self.paths["3127680"]/"usr/bin/FEX"
        fex.write_bytes(b"updated Valve binary")
        with patch.object(m,"enabled",return_value=True), patch.object(m.sys,"argv",["vrchat-setup","--maintain"]):m.main()
        self.assertEqual(fex.read_bytes(),b"patched:usr/bin/FEX")
        self.assertEqual((m.STATE/"valve-fex-backup/usr/bin/FEX").read_bytes(),b"valve")

    def test_custom_options_require_explicit_replace(self):
        m.atomic_write(self.local,m.set_value(self.local.read_text(),m.LAUNCH,"my-wrapper %command%"))
        before = self.config.read_bytes()
        with self.assertRaisesRegex(RuntimeError,"custom-settings"):m.configure(self.local)
        self.assertEqual(self.config.read_bytes(),before)
        m.configure(self.local,replace=True)

    def test_active_game_or_steam_refused(self):
        for name in ("busy","steam_running"):
            with patch.object(m,name,return_value=True):
                with self.assertRaisesRegex(RuntimeError,"game-running"):m.configure(self.local)
        self.assertFalse((m.STATE/"complete.json").exists())

    def test_partial_download_not_accepted(self):
        path=m.STEAM/"steamapps/appmanifest_1493710.acf"
        path.write_text(path.read_text().replace('"4"','"1026"'))
        self.assertIsNone(m.tool("1493710"))
        with self.assertRaisesRegex(RuntimeError,"downloads-pending"):m.configure(self.local)

    def test_arm_proton_not_accepted(self):
        (self.paths["1493710"]/"version").write_text("experimental-arm64")
        with self.assertRaisesRegex(RuntimeError,"proton-architecture"):m.configure(self.local)
        self.assertEqual((self.paths["3127680"]/"usr/bin/FEX").read_bytes(),b"valve")

    def test_corrupt_runtime_does_not_change_tool(self):
        (m.PAYLOAD/"runtime.tar.xz").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError,"checksum"):m.configure(self.local)
        self.assertEqual((self.paths["3127680"]/"usr/bin/FEX").read_bytes(),b"valve")

    def test_fex_write_failure_rolls_back(self):
        replace=m.os.replace
        failed=[False]
        def fail_once(a,b):
            if str(b).endswith("usr/bin/FEXServer") and not failed[0]:
                failed[0]=True;raise OSError("simulated disk error")
            return replace(a,b)
        with patch.object(m.os,"replace",side_effect=fail_once):
            with self.assertRaises(OSError):m.install_fex(self.paths["3127680"])
        self.assertEqual((self.paths["3127680"]/"usr/bin/FEX").read_bytes(),b"valve")

    def test_external_library_and_quoted_paths(self):
        target=m.STEAM.parent/"日本語 Library"
        target.mkdir()
        (m.STEAM/"steamapps/libraryfolders.vdf").write_text('"libraryfolders" { "1" { "path" '+m.VDF['vdf_quote'](str(target))+' } }')
        self.assertIn(target,m.libraries())
        command=m.launch_options(target/"Proton EasyAntiCheat Runtime",cpus=4)
        self.assertIn("16:0,1,2,3,0,1,2,3,0,1,2,3,0,1,2,3",command)
        self.assertIn(str(target/"Proton EasyAntiCheat Runtime"),m.shlex.split(command)[2])


if __name__ == "__main__":
    unittest.main()
