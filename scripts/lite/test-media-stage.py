#!/usr/bin/env python3
"""Stager contract/race tests with an injected verifier; no build, VM or network."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('tested_media_stage', HERE / 'stage-media.py')
stager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stager)


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(root):
    if not root.exists():
        return None
    result = {}
    for path in sorted(root.rglob('*')):
        mode = path.lstat().st_mode
        data = (os.readlink(path) if stat.S_ISLNK(mode) else
                path.read_bytes() if stat.S_ISREG(mode) else None)
        result[path.relative_to(root).as_posix()] = (mode, data)
    return result


class MediaStageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='steamac-media-stage-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runtime = self.root / 'work/media-release/runtime'
        self.runtime.mkdir(parents=True)
        self.layer, self.app = self.root / 'layer', self.root / 'SteamAC.app'
        self.payload = self.layer / 'usr/lib/steamac/camera/proton-media'
        self.manifest = self.payload.parent / 'proton-media.json'
        self.resources = self.app / 'Contents/Resources'
        self.build_receipt = self.resources / 'steamac-media-build.json'
        self.notices = self.resources / 'licenses/Media'
        self.artifacts = {}
        files = {}
        for name in stager.DLLS:
            data = ('synthetic patched DLL: ' + name).encode()
            (self.runtime / name).write_bytes(data)
            files[name] = checksum(data)
            self.artifacts[name] = checksum(data)
        for name in ('NOTICE', 'COPYING.LIB'):
            source = self.root / 'guest/media' / name
            source.parent.mkdir(parents=True, exist_ok=True)
            data = ('Synthetic media license: ' + name).encode()
            source.write_bytes(data)
            (self.runtime / name).write_bytes(data)
            self.artifacts[name] = checksum(data)
        (self.runtime / 'evidence').mkdir()
        (self.runtime / 'evidence/compiler.txt').write_bytes(b'synthetic compiler version')
        self.artifacts['evidence/compiler.txt'] = checksum(b'synthetic compiler version')
        self.receipt = {
            'schema': 1, 'source_version_sha256': checksum(b'stock version'),
            'files': files,
            'stock_files': {stager.WINE + name: checksum(('stock ' + name).encode()) for name in stager.DLLS},
            'inputs': {'guest/media/NOTICE': self.artifacts['NOTICE']},
            'source': {'commit': 'a' * 40},
            'builder_image_id': 'sha256:' + 'b' * 64,
            'evidence': {'evidence/compiler.txt': self.artifacts['evidence/compiler.txt']},
        }
        self.protocol = SimpleNamespace(
            LICENSES=('NOTICE', 'COPYING.LIB'), verify_runtime=Mock(side_effect=self.verify))

    def verify(self, runtime, root):
        """Controlled provenance boundary; structural validation belongs to the stager."""
        self.assertEqual((runtime, root), (self.runtime, self.root))
        for name, expected in self.artifacts.items():
            path = runtime / name
            if not path.is_file() or path.is_symlink() or checksum(path.read_bytes()) != expected:
                raise ValueError('Stub verifier rejected changed artifact: ' + name)
        return copy.deepcopy(self.receipt)

    def stage(self, *, use_default=False):
        options = {'root': self.root, '_protocol': self.protocol}
        if not use_default:
            options['runtime'] = self.runtime
        with contextlib.redirect_stdout(io.StringIO()):
            stager.stage(self.layer, self.app, **options)

    def reject_before_mutation(self, pattern='.'):
        before = snapshot(self.root)
        with self.assertRaisesRegex((ValueError, OSError), pattern):
            self.stage()
        self.assertEqual(snapshot(self.root), before)

    def assert_unpublished(self):
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.build_receipt.exists())
        self.assertFalse(any(self.root.rglob('.media-*')), 'Temporary files must be cleaned up')

    def test_exact_manifest_payload_and_full_receipt(self):
        # Unrelated stock/prefix data is outside both output destinations.
        stock = self.root / 'Steam/steamapps/common/Proton/files/lib/wine/x86_64-windows'
        prefix = self.root / 'Steam/steamapps/compatdata/123/pfx/drive_c'
        stock.mkdir(parents=True)
        prefix.mkdir(parents=True)
        (stock / 'mfmediaengine.dll').write_bytes(b'untouched Steam DLL')
        (prefix / 'sentinel').write_bytes(b'untouched Wine prefix')
        before = snapshot(self.root / 'Steam')
        self.stage(use_default=True)
        expected = {
            'schema': 1, 'source_version_sha256': self.receipt['source_version_sha256'],
            'files': {stager.WINE + name: {
                'stock_sha256': self.receipt['stock_files'][stager.WINE + name],
                'patched_sha256': self.receipt['files'][name]} for name in stager.DLLS},
        }
        self.assertEqual(json.loads(self.manifest.read_text()), expected)
        self.assertEqual(json.loads(self.build_receipt.read_text()), self.receipt)
        self.assertEqual({p.name for p in self.payload.iterdir()}, set(stager.DLLS))
        for name in stager.DLLS:
            path = self.payload / name
            self.assertEqual(path.read_bytes(), (self.runtime / name).read_bytes())
            self.assertTrue(stat.S_ISREG(path.lstat().st_mode))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        self.assertEqual({p.name for p in self.notices.iterdir()}, {'NOTICE', 'COPYING.LIB'})
        for name in ('NOTICE', 'COPYING.LIB'):
            self.assertEqual((self.notices / name).read_bytes(), (self.root / 'guest/media' / name).read_bytes())
        self.assertEqual(snapshot(self.root / 'Steam'), before)
        self.assertEqual(self.protocol.verify_runtime.call_count, 2)
        self.assertEqual({p.relative_to(self.resources).as_posix() for p in self.resources.rglob('*') if p.is_file()},
                         {'steamac-media-build.json', 'licenses/Media/NOTICE', 'licenses/Media/COPYING.LIB'})

    def test_verifier_failure_leaves_absent_outputs_absent(self):
        self.protocol.verify_runtime.side_effect = ValueError('bad receipt')
        self.reject_before_mutation('bad receipt')
        self.assertFalse(self.layer.exists())
        self.assertFalse(self.app.exists())

    def test_verifier_failure_preserves_existing_outputs(self):
        self.stage()
        self.protocol.verify_runtime.side_effect = ValueError('stale inputs')
        self.reject_before_mutation('stale inputs')

    def test_receipt_contract_rejects_unknown_or_unsafe_files(self):
        original = copy.deepcopy(self.receipt)
        mutations = [
            ('schema', True), ('schema', 2), ('files', {}),
            ('source_version_sha256', '../version'),
            ('files', {**original['files'], '../escape.dll': 'a' * 64}),
            ('files', {**original['files'], '/escape.dll': 'a' * 64}),
            ('files', {**original['files'], 'extra.dll': 'a' * 64}),
            ('files', {'mfmediaengine.dll': 'a' * 64, 'sub/winegstreamer.dll': 'b' * 64}),
            ('files', {**original['files'], 'mfmediaengine.dll': 'not a hash'}),
            ('stock_files', {}),
            ('stock_files', {**original['stock_files'], '../escape': 'a' * 64}),
            ('stock_files', {**original['stock_files'], stager.WINE + 'mfmediaengine.dll': 'A' * 64}),
            ('stock_files', {**original['stock_files'], stager.WINE + 'mfmediaengine.dll':
                             original['files']['mfmediaengine.dll']}),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                self.receipt = {**original, key: value}
                self.reject_before_mutation()
        self.receipt = original

    def test_payload_checksum_defense_with_permissive_verifier(self):
        self.protocol.verify_runtime.side_effect = None
        self.protocol.verify_runtime.return_value = self.receipt
        (self.runtime / stager.DLLS[-1]).write_bytes(b'tampered')
        self.reject_before_mutation('checksum')

    def test_payload_symlink_directory_and_fifo_rejected(self):
        self.protocol.verify_runtime.side_effect = None
        self.protocol.verify_runtime.return_value = self.receipt
        path = self.runtime / stager.DLLS[-1]
        path.unlink()
        outside = self.root / 'external.dll'
        outside.write_bytes(b'untouched')
        for kind in ('symlink', 'directory', 'fifo'):
            with self.subTest(kind=kind):
                if kind == 'symlink':
                    path.symlink_to(outside)
                elif kind == 'directory':
                    path.mkdir()
                else:
                    os.mkfifo(path)
                self.reject_before_mutation('no symlinks')
                if kind == 'directory':
                    path.rmdir()
                else:
                    path.unlink()

    def test_runtime_directory_symlink_rejected(self):
        real = self.runtime.with_name('real-runtime')
        self.runtime.rename(real)
        self.runtime.symlink_to(real, target_is_directory=True)
        self.reject_before_mutation('no symlinks')

    def test_missing_guest_license_fails_before_mutation(self):
        (self.root / 'guest/media/COPYING.LIB').unlink()
        self.reject_before_mutation('Missing regular')

    def test_guest_license_symlink_rejected(self):
        path = self.root / 'guest/media/NOTICE'
        path.unlink()
        path.symlink_to(self.runtime / 'NOTICE')
        self.reject_before_mutation('no symlinks')

    def test_runtime_license_must_match_guest_notice(self):
        self.protocol.verify_runtime.side_effect = None
        self.protocol.verify_runtime.return_value = self.receipt
        (self.runtime / 'NOTICE').write_bytes(b'wrong notice')
        self.reject_before_mutation('differs from guest/media')

    def test_generic_runtime_license_files_copied(self):
        name = 'compiler/GCC-COPYING'
        path = self.runtime / name
        path.parent.mkdir()
        path.write_bytes(b'synthetic compiler license')
        self.artifacts[name] = checksum(path.read_bytes())
        self.protocol.LICENSES += (name,)
        self.stage()
        self.assertEqual((self.notices / name).read_bytes(), path.read_bytes())

    def test_unsafe_license_contract_rejected_before_mutation(self):
        for name in ('../escape', '/escape', 'a/../escape', 'a\\escape', './NOTICE',
                     'a//COPYING', '', 'NOTICE/child'):
            with self.subTest(name=name):
                self.protocol.LICENSES = ('NOTICE', 'COPYING.LIB', name)
                self.reject_before_mutation()
        self.protocol.LICENSES = ('NOTICE', 'NOTICE')
        self.reject_before_mutation('Duplicate')

    def test_destination_symlinks_rejected_before_any_mutation(self):
        external = self.root / 'outside'
        external.mkdir()
        for path in (self.layer, self.layer / 'usr', self.payload, self.payload / stager.DLLS[-1],
                     self.manifest, self.app, self.resources, self.notices / 'COPYING.LIB', self.build_receipt):
            with self.subTest(path=path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(external)
                self.reject_before_mutation('no symlinks')
                path.unlink()

    def test_existing_payload_rejects_unknown_files(self):
        self.payload.mkdir(parents=True)
        (self.payload / 'extra.dll').write_bytes(b'untracked')
        self.reject_before_mutation('Unexpected existing')

    def test_copy_tampering_never_publishes_receipts(self):
        copyfile = stager.shutil.copyfile

        def corrupt(source, target):
            result = copyfile(source, target)
            if source.name == stager.DLLS[-1]:
                target.write_bytes(b'corrupted during copy')
            return result

        with patch.object(stager.shutil, 'copyfile', side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, 'changed while staging'):
                self.stage()
        self.assert_unpublished()

    def test_license_copy_tampering_never_publishes_receipts(self):
        copyfile = stager.shutil.copyfile

        def corrupt(source, target):
            result = copyfile(source, target)
            if source.name == 'COPYING.LIB':
                target.write_bytes(b'corrupted license')
            return result

        with patch.object(stager.shutil, 'copyfile', side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, 'changed while staging'):
                self.stage()
        self.assert_unpublished()

    def test_runtime_change_after_copy_rejected_by_second_verification(self):
        copyfile = stager.shutil.copyfile

        def mutate_source(source, target):
            result = copyfile(source, target)
            if source.name == stager.DLLS[-1]:
                source.write_bytes(b'changed after copy')
            return result

        with patch.object(stager.shutil, 'copyfile', side_effect=mutate_source):
            with self.assertRaisesRegex(ValueError, 'changed artifact'):
                self.stage()
        self.assertEqual(self.protocol.verify_runtime.call_count, 2)
        self.assert_unpublished()

    def test_second_verification_precedes_both_publications(self):
        def verify(runtime, root):
            self.assert_unpublished()
            if self.protocol.verify_runtime.call_count == 2:
                self.assertTrue(all((self.payload / name).is_file() for name in stager.DLLS))
                self.assertTrue((self.notices / 'NOTICE').is_file())
                raise ValueError('inputs changed during staging')
            return self.verify(runtime, root)

        self.protocol.verify_runtime.side_effect = verify
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.stage()
        self.assert_unpublished()

    def test_changed_receipt_on_second_verification_is_rejected(self):
        changed = copy.deepcopy(self.receipt)
        changed['builder_image_id'] = 'sha256:' + 'c' * 64
        self.protocol.verify_runtime.side_effect = [self.receipt, changed]
        with self.assertRaisesRegex(ValueError, 'receipt changed'):
            self.stage()
        self.assert_unpublished()

    def test_already_copied_payload_tampering_is_rechecked(self):
        def verify(runtime, root):
            if self.protocol.verify_runtime.call_count == 2:
                (self.payload / stager.DLLS[0]).write_bytes(b'changed staged file')
            return self.verify(runtime, root)

        self.protocol.verify_runtime.side_effect = verify
        with self.assertRaisesRegex(ValueError, 'Staged media checksum'):
            self.stage()
        self.assert_unpublished()

    def test_existing_hard_link_destination_does_not_modify_stock(self):
        self.payload.mkdir(parents=True)
        stock = self.root / 'stock.dll'
        stock.write_bytes(b'untouched hard linked DLL')
        os.link(stock, self.payload / stager.DLLS[0])
        self.stage()
        self.assertEqual(stock.read_bytes(), b'untouched hard linked DLL')

    def test_current_parent_protocol_loads_without_running_build(self):
        protocol = stager.load_protocol()
        self.assertTrue(callable(protocol.verify_runtime))
        self.assertEqual(set(protocol.FILENAMES), set(stager.DLLS))
        self.assertTrue({'NOTICE', 'COPYING.LIB'} <= set(protocol.LICENSES))


if __name__ == '__main__':
    unittest.main(verbosity=2)
