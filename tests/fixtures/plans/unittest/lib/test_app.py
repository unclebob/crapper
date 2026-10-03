import unittest

from demo.app import run


class AppTest(unittest.TestCase):
    def test_run(self):
        self.assertEqual(run(), 1)
