#!/usr/bin/env python3
"""Cheap provenance regression tests. No Docker, VM, network or FFmpeg build.

Tiny synthetic source/ELF fixtures exercise the real protocol around a mocked
Docker boundary. They validate provenance checks, not codec functionality.
"""
import contextlib
import fcntl
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol = load('tested_video_build', HERE / 'record-video-build.py')
stager = load('tested_video_stage', HERE / 'stage-video.py')


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='steamac-video-provenance-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in protocol.INPUTS:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dest)
        self.work = self.root / 'work/video-release'
        self.work.mkdir(parents=True)
        self.pin = json.loads((self.root / protocol.INPUTS[0]).read_text())
        self.archive = self.work / 'ffmpeg-source.tar.gz'
        self.make_archive()
        self.pin['archive_sha256'] = protocol.digest(self.archive)
        (self.root / protocol.INPUTS[0]).write_text(json.dumps(self.pin))
        self.calls = []
        self.runs = []
        self.hook = None

    def make_archive(self, extra=None):
        with tarfile.open(self.archive, 'w:gz') as archive:
            prefix = 'FFmpeg-' + self.pin['commit']
            for name, data in [('configure', b'#!/bin/sh\n# synthetic configure\n'),
                               ('COPYING.LGPLv2.1', b'synthetic LGPL text'),
                               ('COPYING.GPLv2', b'synthetic GPL text'),
                               ('LICENSE.md', b'synthetic license text')]:
                member = tarfile.TarInfo(prefix + '/' + name)
                member.mode = 0o755 if name == 'configure' else 0o644
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            if extra:
                member, data = extra
                archive.addfile(member, io.BytesIO(data) if data is not None else None)

    def fake_docker(self, command, check):
        self.assertTrue(check)
        self.assertEqual(command[:7], ['docker', 'run', '--rm', '--platform', 'linux/amd64', '--user', '0'])
        self.assertIn(self.pin['sdk_image'], command)
        image_index = command.index(self.pin['sdk_image'])
        self.assertEqual(command[image_index + 1:], ['env', '-i', *protocol.ENVIRONMENT, '/bin/sh', '/recipe.sh'])
        mounts = command[:image_index]
        source_mount = next(arg for arg in mounts if 'dst=/source,' in arg)
        recipe_mount = next(arg for arg in mounts if 'dst=/recipe.sh,' in arg)
        self.assertTrue(source_mount.endswith(',readonly'))
        self.assertTrue(recipe_mount.endswith(',readonly'))
        self.assertNotIn(str(self.root) + ':/src', command)
        source = Path(source_mount.split('src=', 1)[1].split(',dst=', 1)[0])
        run = source.parent
        self.runs.append(run)
        self.calls.append(command)
        self.assertEqual(list((run / 'build').iterdir()), [])
        self.assertEqual(list((run / 'install').iterdir()), [])
        self.assertEqual(protocol.tree_inventory(source), protocol.archive_inventory(self.archive, self.pin))
        installed = run / 'install/usr/lib/x86_64-linux-gnu'
        installed.mkdir(parents=True)
        hashes = {}
        for index, name in enumerate(protocol.SONAMES):
            elf = bytearray(64)
            elf[:6] = b'\x7fELF\x02\x01'
            struct.pack_into('<H', elf, 18, 62)
            elf.extend(f'synthetic library {index}'.encode())
            linked = run / 'build' / name.split('.')[0] / name
            linked.parent.mkdir()
            linked.write_bytes(elf)
            # FFmpeg install normally supplies SONAME symlinks to versioned files.
            versioned = installed / (name + '.99.1')
            versioned.write_bytes(elf)
            (installed / name).symlink_to(versioned.name)
            hashes[name] = protocol.digest(linked)
        static = run / 'build/libswresample/libswresample.a'
        static.parent.mkdir()
        static.write_bytes(b'!<arch>\nsynthetic swresample PIC archive')
        evidence = run / 'evidence'
        shutil.copyfile(static, evidence / 'libswresample.a')
        for name in protocol.DYNAMIC_EVIDENCE:
            (evidence / name).write_text(' 0x1 (NEEDED) Shared library: [libc.so.6]\n')
        config = ' '.join(protocol.CONFIGURE)
        header = '#define FFMPEG_CONFIGURATION ' + json.dumps(config) + '\n'
        header += '#define FFMPEG_LICENSE "LGPL version 2.1 or later"\n'
        header += ''.join('#define ' + name + ' 0\n' for name in (
            'CONFIG_GPL', 'CONFIG_NONFREE', 'CONFIG_VERSION3', 'CONFIG_GPLV3'))
        for suffix, components in (('DECODER', protocol.DECODERS),
                                   ('PARSER', protocol.PARSERS), ('DEMUXER', protocol.DEMUXERS)):
            header += ''.join('#define CONFIG_' + name.upper() + '_' + suffix + ' 1\n' for name in components)
        header += ''.join('#define CONFIG_' + name + ' 1\n' for name in ('SWRESAMPLE', 'STATIC', 'SHARED'))
        (evidence / 'config.h').write_text(header)
        (evidence / 'config.mak').write_text('FFMPEG_CONFIGURATION=' + config + '\n')
        (evidence / 'packages.tsv').write_text('gcc\tfixture\tamd64\nnasm\t' + self.pin['nasm_package'] + '\tamd64\n')
        (evidence / 'machine.txt').write_text('x86_64-linux-gnu\n')
        for name in ('compiler.txt', 'linker.txt', 'strip.txt', 'nasm.txt'):
            (evidence / name).write_text('synthetic tool version\n')
        (evidence / 'libraries.sha256').write_text(''.join(sha + '  ' + name + '\n' for name, sha in hashes.items()))
        if self.hook:
            self.hook(run)
        return subprocess.CompletedProcess(command, 0)

    def build(self):
        # Any Docker invocation is intercepted here; no process is spawned.
        with patch.object(protocol.subprocess, 'run', side_effect=self.fake_docker), \
                patch.object(protocol.urllib.request, 'urlopen', side_effect=AssertionError('network forbidden')), \
                contextlib.redirect_stdout(io.StringIO()):
            return protocol.build(self.root)

    def assert_rejected(self, runtime, pattern=None):
        layer, app = self.root / 'layer', self.root / 'app'
        with self.assertRaisesRegex((ValueError, FileNotFoundError), pattern or '.'):
            stager.stage(layer, app, root=self.root, runtime=runtime)
        self.assertFalse(layer.exists(), 'Rejected inputs must not write a guest manifest/payload')
        self.assertFalse(app.exists(), 'Rejected inputs must not change the application')

    def mutate(self, path):
        path.write_bytes(path.read_bytes() + b'\nmodified\n')

    def rehash_artifact(self, runtime, name):
        receipt_path = runtime / 'build.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['artifacts'][name] = protocol.digest(runtime / name)
        receipt_path.write_text(json.dumps(receipt))

    def test_complete_build_and_stage(self):
        runtime = self.build()
        receipt = protocol.verify_runtime(runtime, self.root)
        self.assertEqual(receipt['schema'], 2)
        self.assertEqual(set(receipt['files']), set(protocol.SONAMES))
        self.assertEqual(receipt['license'], 'LGPL-2.1-or-later')
        layer, app = self.root / 'layer', self.root / 'app'
        stager.stage(layer, app, root=self.root, runtime=runtime)
        manifest = json.loads((layer / 'usr/lib/steamac/camera/proton-video.json').read_text())
        self.assertEqual(manifest['schema'], 1)  # Guest four-library contract stays compatible.
        self.assertEqual(set(manifest['files']), {'files/lib/x86_64-linux-gnu/' + n for n in protocol.SONAMES})
        self.assertEqual(json.loads((app / 'Contents/Resources/steamac-video-build.json').read_text()), receipt)
        self.assertFalse((app / 'Contents/Resources/ffmpeg-source.tar.gz').exists())

    def test_each_build_uses_clean_source_build_install(self):
        stale = self.work / ('FFmpeg-' + self.pin['commit'])
        stale.mkdir()
        (stale / 'configure').write_text('UNTRUSTED OLD TREE')
        old_build = self.work / 'build'
        old_build.mkdir()
        (old_build / 'config.h').write_text('UNTRUSTED OLD CONFIG')
        self.build()
        (self.runs[0] / 'source/configure').write_text('MUTATED PREVIOUS RUN')
        self.build()
        self.assertNotEqual(self.runs[0], self.runs[1])
        self.assertEqual((stale / 'configure').read_text(), 'UNTRUSTED OLD TREE')

    def test_bad_archive_fails_before_docker(self):
        self.mutate(self.archive)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.build()
        self.assertEqual(self.calls, [])
        self.assertFalse((self.work / 'runtime').exists())

    def test_unsafe_archive_members(self):
        for kind in ('traversal', 'absolute', 'symlink', 'hardlink', 'duplicate'):
            with self.subTest(kind=kind):
                prefix = 'FFmpeg-' + self.pin['commit']
                name = {'traversal': prefix + '/../escape', 'absolute': '/escape',
                        'duplicate': prefix + '/configure'}.get(kind, prefix + '/link')
                member = tarfile.TarInfo(name)
                data = b'bad'
                member.size = len(data)
                if kind in ('symlink', 'hardlink'):
                    member.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
                    member.linkname = '/escape'
                    member.size = 0
                    data = None
                self.make_archive((member, data))
                pin = {**self.pin, 'archive_sha256': protocol.digest(self.archive)}
                with self.assertRaises(ValueError):
                    protocol.archive_inventory(self.archive, pin)
        self.assertFalse((self.root / 'escape').exists())

    def test_extraction_never_reuses_existing_tree(self):
        source = self.root / 'already-there'
        source.mkdir()
        with self.assertRaises(FileExistsError):
            protocol.archive_inventory(self.archive, self.pin, source)

    def test_source_mutation_during_build_fails(self):
        self.hook = lambda run: self.mutate(run / 'source/configure')
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            self.build()
        self.assertFalse((self.work / 'runtime').exists())

    def test_recipe_mutation_during_build_fails(self):
        self.hook = lambda run: self.mutate(run / 'recipe.sh')
        with self.assertRaisesRegex(ValueError, 'Recipe changed'):
            self.build()

    def test_repository_input_mutation_during_build_fails(self):
        self.hook = lambda run: self.mutate(self.root / 'guest/video/build-codecs.sh')
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.build()

    def test_docker_failure_preserves_previous_runtime(self):
        runtime = self.build()
        before = (runtime / 'build.json').read_bytes()
        with patch.object(protocol.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['docker'])):
            with self.assertRaises(subprocess.CalledProcessError):
                protocol.build(self.root)
        self.assertEqual((runtime / 'build.json').read_bytes(), before)

    def test_actual_config_must_match_recipe(self):
        def wrong(run):
            path = run / 'evidence/config.h'
            path.write_text(path.read_text().replace('CONFIG_GPL 0', 'CONFIG_GPL 1'))
        self.hook = wrong
        with self.assertRaisesRegex(ValueError, 'license configuration'):
            self.build()

    def test_extra_configure_argument_rejected(self):
        def wrong(run):
            path = run / 'evidence/config.h'
            path.write_text(path.read_text().replace('--enable-protocol=file', '--enable-protocol=file --enable-gpl'))
        self.hook = wrong
        with self.assertRaisesRegex(ValueError, 'configure arguments'):
            self.build()

    def test_installed_libraries_must_equal_this_runs_linked_outputs(self):
        self.hook = lambda run: self.mutate(run / 'install/usr/lib/x86_64-linux-gnu' / (protocol.SONAMES[0] + '.99.1'))
        with self.assertRaisesRegex(ValueError, 'linked output differ'):
            self.build()

    def test_installed_library_cannot_escape_workspace(self):
        def escape(run):
            path = run / 'install/usr/lib/x86_64-linux-gnu' / protocol.SONAMES[0]
            path.unlink()
            path.symlink_to(self.root / 'guest/video/NOTICE')
        self.hook = escape
        with self.assertRaisesRegex(ValueError, 'escapes build output'):
            self.build()

    def test_wrong_actual_nasm_version_rejected(self):
        self.hook = lambda run: (run / 'evidence/packages.tsv').write_text('nasm\twrong\tamd64\n')
        with self.assertRaisesRegex(ValueError, 'nasm package'):
            self.build()

    def test_completed_build_hashes_must_match(self):
        self.hook = lambda run: (run / 'evidence/libraries.sha256').write_text('0' * 64 + '  libavcodec.so.58\n')
        with self.assertRaisesRegex(ValueError, 'Incomplete build output'):
            self.build()

    def test_stale_protocol_inputs_fail_closed(self):
        runtime = self.build()
        for name in protocol.INPUTS:
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                self.mutate(path)
                self.assert_rejected(runtime)
                path.write_bytes(original)

    def test_runtime_evidence_and_payload_tampering_rejected(self):
        runtime = self.build()
        for name in ('libavcodec.so.58', 'COPYING.LGPLv2.1', 'evidence/packages.tsv',
                     'evidence/config.h', 'recipe.sh', 'ffmpeg-source.tar.gz'):
            with self.subTest(name=name):
                path = runtime / name
                original = path.read_bytes()
                self.mutate(path)
                self.assert_rejected(runtime)
                path.write_bytes(original)

    def test_rehashing_altered_config_does_not_bless_it(self):
        runtime = self.build()
        path = runtime / 'evidence/config.h'
        path.write_text(path.read_text().replace('CONFIG_NONFREE 0', 'CONFIG_NONFREE 1'))
        self.rehash_artifact(runtime, 'evidence/config.h')
        self.assert_rejected(runtime, 'license configuration')

    def test_rehashing_arbitrary_recipe_does_not_bless_it(self):
        runtime = self.build()
        self.mutate(runtime / 'recipe.sh')
        self.rehash_artifact(runtime, 'recipe.sh')
        self.assert_rejected(runtime, 'recipe')

    def test_legacy_hardcoded_receipt_rejected(self):
        runtime = self.build()
        (runtime / 'build.json').write_text(json.dumps({'schema': 1, 'source': self.pin}))
        self.assert_rejected(runtime, 'schema 2')

    def test_missing_evidence_rejected(self):
        runtime = self.build()
        (runtime / 'evidence/compiler.txt').unlink()
        self.assert_rejected(runtime)

    def test_extra_payload_and_symlink_rejected(self):
        runtime = self.build()
        extra = runtime / 'extra.so'
        extra.write_text('unrecorded')
        self.assert_rejected(runtime)
        extra.unlink()
        path = runtime / 'libavcodec.so.58'
        original = path.read_bytes()
        path.unlink()
        outside = self.root / 'unowned.so'
        outside.write_bytes(original)
        path.symlink_to(outside)
        self.assert_rejected(runtime)

    def test_concurrent_build_is_rejected_before_docker(self):
        with (self.work / '.build.lock').open('w') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'already running'):
                self.build()
        self.assertEqual(self.calls, [])

    def test_rehashing_wrong_license_does_not_bless_it(self):
        runtime = self.build()
        self.mutate(runtime / 'COPYING.LGPLv2.1')
        self.rehash_artifact(runtime, 'COPYING.LGPLv2.1')
        self.assert_rejected(runtime, 'License differs')

    def test_receipt_source_recipe_environment_cannot_drift(self):
        runtime = self.build()
        path = runtime / 'build.json'
        original = path.read_bytes()
        mutations = {'source_tree_sha256': '0' * 64, 'configure': [],
                     'environment': ['CFLAGS=unrecorded'], 'make_overrides': [], 'files': {}}
        for name, value in mutations.items():
            with self.subTest(name=name):
                receipt = json.loads(original)
                receipt[name] = value
                path.write_text(json.dumps(receipt))
                self.assert_rejected(runtime)
                path.write_bytes(original)

    def test_wrong_elf_rejected_even_if_checksum_lists_are_rehashed(self):
        runtime = self.build()
        name = protocol.SONAMES[0]
        path = runtime / name
        data = bytearray(path.read_bytes())
        struct.pack_into('<H', data, 18, 183)  # AArch64 must not enter x86 Proton.
        path.write_bytes(data)
        receipt_path = runtime / 'build.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['files'][name] = protocol.digest(path)
        receipt['artifacts'][name] = protocol.digest(path)
        rows = ''.join(sha + '  ' + n + '\n' for n, sha in receipt['files'].items())
        (runtime / 'evidence/libraries.sha256').write_text(rows)
        receipt['artifacts']['evidence/libraries.sha256'] = protocol.digest(runtime / 'evidence/libraries.sha256')
        receipt_path.write_text(json.dumps(receipt))
        self.assert_rejected(runtime, 'x86_64')

    def test_requested_formats_are_in_actual_canonical_recipe(self):
        wanted = {'vp8', 'vp9', 'opus', 'theora', 'mpeg1video', 'mpeg2video',
                  'mpeg4', 'vc1', 'wmv3', 'wmav1', 'wmav2'}
        self.assertTrue(wanted <= set(protocol.DECODERS))
        self.assertIn('--disable-autodetect', protocol.CONFIGURE)
        recipe = protocol.recipe(self.pin)
        self.assertIn('--enable-decoder=' + ','.join(protocol.DECODERS), recipe)
        self.assertIn('make -j2 libswresample/libswresample.a', recipe)
        self.assertIn('avcodec_FFLIBS=avutil', recipe)
        self.assertIn('/build/libswresample/libswresample.a', recipe)
        self.assertIn('${name%%.*}', recipe)
        self.assertNotIn('--enable-gpl', recipe)
        self.assertNotIn('--enable-nonfree', recipe)
        self.assertNotIn('--enable-libopus', recipe)
        self.assertNotIn('--enable-libvpx', recipe)

    def test_silently_disabled_requested_codec_rejected(self):
        def disable(run):
            path = run / 'evidence/config.h'
            path.write_text(path.read_text().replace('CONFIG_OPUS_DECODER 1', 'CONFIG_OPUS_DECODER 0'))
        self.hook = disable
        with self.assertRaisesRegex(ValueError, 'component was disabled: opus'):
            self.build()

    def test_fifth_ffmpeg_shared_dependency_rejected(self):
        def dependency(run):
            (run / 'evidence' / protocol.DYNAMIC_EVIDENCE[0]).write_text(
                ' 0x1 (NEEDED) Shared library: [libswresample.so.3]\n')
        self.hook = dependency
        with self.assertRaisesRegex(ValueError, 'must remain four libraries'):
            self.build()

    def test_embedded_static_dependency_must_match_this_build(self):
        self.hook = lambda run: self.mutate(run / 'evidence/libswresample.a')
        with self.assertRaisesRegex(ValueError, 'static archive differs'):
            self.build()

    def test_generated_recipe_shell_syntax(self):
        subprocess.run(['/bin/sh', '-n'], input=protocol.recipe(self.pin), text=True, check=True)

    def test_failed_post_build_validation_keeps_previous_runtime(self):
        runtime = self.build()
        previous = (runtime / 'build.json').read_bytes()
        self.hook = lambda run: self.mutate(run / 'source/configure')
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            self.build()
        self.assertEqual((runtime / 'build.json').read_bytes(), previous)
        protocol.verify_runtime(runtime, self.root)

    def test_generated_make_config_must_match_header_and_recipe(self):
        def wrong(run):
            path = run / 'evidence/config.mak'
            path.write_text(path.read_text().replace('--enable-protocol=file', '--enable-protocol=http'))
        self.hook = wrong
        with self.assertRaisesRegex(ValueError, 'config.mak'):
            self.build()

    def test_old_bless_arbitrary_dirs_cli_removed(self):
        result = subprocess.run([sys.executable, str(HERE / 'record-video-build.py'),
                                 str(self.root / 'arbitrary-libs'), str(self.root / 'arbitrary-source')],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('invalid choice', result.stderr)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
