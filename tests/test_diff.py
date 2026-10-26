import unittest

from btd_actions.diff import Diff

RAW = """diff --git a/a.py b/a.py
index 1..2 100644
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-x
+y
diff --git a/big.txt b/big.txt
--- a/big.txt
+++ b/big.txt
@@ -0,0 +1 @@
+""" + "z" * 500 + """
diff --git a/c.go b/c.go
--- a/c.go
+++ b/c.go
@@ -1 +1 @@
-a
+b"""


class DiffTest(unittest.TestCase):
    def test_parse_paths(self):
        self.assertEqual([f.path for f in Diff.parse(RAW).files], ["a.py", "big.txt", "c.go"])

    def test_render_cuts_large_file(self):
        out = Diff.parse(RAW).render(max_chars=10_000, max_file_chars=150)
        self.assertIn("chars cut", out)
        self.assertIn("c.go", out)

    def test_render_omits_over_budget(self):
        out = Diff.parse(RAW).render(max_chars=200, max_file_chars=10_000)
        self.assertIn("a.py", out)
        self.assertIn("files omitted (budget): big.txt", out)

    def test_empty(self):
        self.assertEqual(Diff.parse("").render(100, 100), "(no diff)")
