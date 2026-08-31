import subprocess
import unittest
from unittest import mock

from tests import visual_smoke


class BrowserProcessTests(unittest.TestCase):
    def test_transient_timeout_is_retried_once_without_weakening_result(self):
        passed = subprocess.CompletedProcess(["browser"], 0, "passed", "")
        with mock.patch.object(
            visual_smoke.subprocess,
            "run",
            side_effect=[subprocess.TimeoutExpired(["browser"], 30), passed],
        ) as run:
            result = visual_smoke.run_browser(["browser"], timeout=30)

        self.assertIs(result, passed)
        self.assertEqual(run.call_count, 2)

    def test_persistent_timeout_remains_a_hard_failure(self):
        with mock.patch.object(
            visual_smoke.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["browser"], 30),
        ) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                visual_smoke.run_browser(["browser"], timeout=30)

        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
