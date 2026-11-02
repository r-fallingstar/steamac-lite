#!/usr/bin/env python3
"""Exercise allocation/activation failure paths without root, swap or a VM."""
from pathlib import Path
import os
import runpy
import subprocess
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE = runpy.run_path(str(ROOT / 'guest/layer/usr/lib/steamac/low-memory-swap'))
GIB = MODULE['GIB']


class SwapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / 'private'
        self.calls = []
        self.is_active = False
        self.free = 12 * GIB
        self.fs = 'ext4'
        self.failure = None

    def runner(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[0] == self.failure:
            raise subprocess.CalledProcessError(1, argv)
        out = ''
        if argv[0] == 'findmnt': out = self.fs
        if argv[0] == 'fallocate':
            # A sparse fixture avoids allocating real disk space during unit tests.
            with open(argv[-1], 'r+b') as f: f.truncate(4 * GIB)
        if argv[:2] == ['swapon', '--priority']: self.is_active = True
        return types.SimpleNamespace(stdout=out)

    def swap(self):
        return MODULE['SwapFile'](self.directory, self.runner,
                                  lambda _: types.SimpleNamespace(free=self.free), os.getuid(),
                                  lambda: 'Filename Type Size Used Priority\n' +
                                  (str(self.directory/'swapfile') + ' file 4194300 0 10\n' if self.is_active else ''))

    def test_flag_is_opt_in(self):
        enabled = MODULE['enabled']
        for cmdline in ['', 'steamac.low_memory=0', 'xsteamac.low_memory=1', 'steamac.low_memory=1 steamac.low_memory=0']:
            self.assertFalse(enabled(cmdline))
        self.assertTrue(enabled('console=hvc0 steamac.low_memory=1'))

    def test_allocate_and_reuse(self):
        self.assertEqual(self.swap().apply()['disk_swap_mib'], 4096)
        self.assertIn(['swapon', '--priority', '10', str(self.directory/'swapfile')], self.calls)
        self.calls.clear()
        self.free = 0
        self.swap().apply()
        self.assertEqual(self.calls, [])

    def test_low_space_does_not_allocate(self):
        self.free = 8 * GIB - 1
        with self.assertRaisesRegex(ValueError, '8 GiB'): self.swap().apply()
        self.assertFalse((self.directory/'swapfile').exists())
        self.assertFalse(any(c[0] == 'fallocate' for c in self.calls))

    def test_unsupported_filesystem(self):
        self.fs = 'btrfs'
        with self.assertRaisesRegex(ValueError, 'ext4'): self.swap().apply()

    def test_symlink_is_never_followed(self):
        self.directory.mkdir(mode=0o700)
        target = Path(self.tmp.name)/'untouched'
        target.write_text('keep')
        (self.directory/'swapfile').symlink_to(target)
        with self.assertRaises(ValueError): self.swap().apply()
        self.assertEqual(target.read_text(), 'keep')
        self.assertEqual(self.calls, [])

    def test_failed_allocation_cleans_only_temporary_file(self):
        self.failure = 'fallocate'
        with self.assertRaises(subprocess.CalledProcessError): self.swap().apply()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_failed_activation_preserves_completed_swap_file(self):
        self.failure = 'swapon'
        with self.assertRaises(subprocess.CalledProcessError): self.swap().apply()
        self.assertTrue((self.directory/'swapfile').is_file())
        self.assertFalse((self.directory/'swapfile.new').exists())


if __name__ == '__main__':
    unittest.main()
