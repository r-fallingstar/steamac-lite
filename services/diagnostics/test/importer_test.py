import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('importer', Path(__file__).parents[1] / 'import-to-github.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ImporterTest(unittest.TestCase):
    def exercise(self, *, private=True, duplicate=False, fail=False):
        report = {'id': '11111111-1111-4111-8111-111111111111', 'kind': 'startup-stalled',
                  'version': '1.9.8-lite.7', 'stage': 'main', 'received_at': '2026-11-16T00:00:00Z'}
        calls = []
        def request(url, token, method='GET', body=None):
            calls.append((url, method, body))
            if url.endswith('/repos/test/inbox'): return {'private': private}
            if url.endswith('/admin/reports'): return {'reports': [report]}
            if '/issues?' in url:
                return [{'body': '<!-- steamac-diagnostic:' + report['id'] + ' -->'}] if duplicate else []
            if url.endswith('/issues'):
                if fail: raise RuntimeError('GitHub unavailable')
                return {'number': 123}
            if url.endswith('/admin/ack'): return {'status': 'ok'}
            raise AssertionError(url)
        if not private or fail:
            with self.assertRaises(RuntimeError): m.synchronize('https://intake.test', 'reader', 'test/inbox', 'gh', request)
            self.assertFalse(any(url.endswith('/admin/ack') for url, _, _ in calls))
        else:
            self.assertEqual(m.synchronize('https://intake.test', 'reader', 'test/inbox', 'gh', request), 1)
            self.assertEqual(sum(method == 'POST' and url.endswith('/issues') for url, method, _ in calls), 0 if duplicate else 1)
    def test_private_repo_required(self): self.exercise(private=False)
    def test_delivery(self): self.exercise()
    def test_retry_does_not_duplicate(self): self.exercise(duplicate=True)
    def test_no_ack_on_failure(self): self.exercise(fail=True)
    def test_text_cannot_escape_or_ping(self):
        self.assertEqual(m.fenced('``` @test'), "```text\n''' ＠test\n```")


if __name__ == '__main__': unittest.main()
