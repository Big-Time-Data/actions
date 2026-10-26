import unittest

from btd_actions.version import Version

TAGS = ["v2.27.3", "v2.27.4", "v2.27.4-beta", "v2.27.5-beta", "v2.28.0-beta", "v2.27.10", "app/v9.9.9", "latest"]


class VersionTest(unittest.TestCase):
    def test_parse(self):
        v = Version.parse("v1.2.3-beta.4")
        self.assertEqual((v.prefix, v.major, v.minor, v.patch, v.pre), ("v", 1, 2, 3, "beta.4"))
        self.assertEqual(v.channel, "beta")
        self.assertEqual(v.number, "1.2.3-beta.4")
        self.assertIsNone(Version.parse("latest"))
        self.assertEqual(Version.parse("1.0.0").channel, "stable")

    def test_previous_stable_skips_beta(self):
        self.assertEqual(Version.parse("v2.28.0").previous(TAGS), "v2.27.10")

    def test_previous_beta_uses_beta(self):
        self.assertEqual(Version.parse("v2.28.0-beta").previous(TAGS), "v2.27.5-beta")
        self.assertEqual(Version.parse("v2.28.1-beta").previous(TAGS), "v2.28.0-beta")

    def test_previous_numeric_order(self):
        self.assertEqual(Version.parse("v2.27.11").previous(TAGS), "v2.27.10")

    def test_previous_same_prefix(self):
        self.assertEqual(Version.parse("app/v10.0.0").previous(TAGS), "app/v9.9.9")

    def test_no_previous(self):
        self.assertEqual(Version.parse("v0.0.1").previous(TAGS), "")
