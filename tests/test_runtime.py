import os
import tempfile
import unittest
from pathlib import Path

from btd_actions.runtime import ActionError, Runtime


class RuntimeTest(unittest.TestCase):
    def test_inputs(self):
        rt = Runtime({"INPUT_A": " x ", "INPUT_FLAG": "true", "INPUT_N": "5", "INPUT_LIST": "a, b\nc\n"})
        self.assertEqual(rt.input("a"), "x")
        self.assertEqual(rt.input("missing", "d"), "d")
        self.assertTrue(rt.bool_input("flag"))
        self.assertEqual(rt.int_input("n", 1), 5)
        self.assertEqual(rt.list_input("list"), ["a", "b", "c"])
        with self.assertRaises(ActionError):
            rt.input("missing", required=True)
        with self.assertRaises(ActionError):
            Runtime({"INPUT_FLAG": "maybe"}).bool_input("flag")

    def test_multiline_output(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out")
            Runtime({"GITHUB_OUTPUT": path}).set_output("body", "line 1\nline 2")
            lines = Path(path).read_text().splitlines()
        self.assertTrue(lines[0].startswith("body<<ghadelimiter_"))
        self.assertEqual(lines[1:3], ["line 1", "line 2"])
        self.assertEqual(lines[3], lines[0].split("<<", 1)[1])
