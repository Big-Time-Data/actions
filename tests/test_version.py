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

    def test_prerelease_since_any(self):
        tags = ["v0.1.4", "v0.1.5-beta.1", "v0.1.9", "v0.1.10-beta.3"]
        self.assertEqual(Version.parse("v0.1.5-beta.2").previous(tags, "any"), "v0.1.5-beta.1")
        self.assertEqual(Version.parse("v0.2.0-beta.1").previous(tags, "any"), "v0.1.10-beta.3")
        self.assertEqual(Version.parse("v0.1.10-beta.4").previous(tags, "any"), "v0.1.10-beta.3")
        # A stable tag still compares with stable tags only.
        self.assertEqual(Version.parse("v0.1.10").previous(tags, "any"), "v0.1.9")

    def test_stable_sorts_after_its_prereleases(self):
        self.assertLess(Version.parse("v1.0.0-beta.9").key, Version.parse("v1.0.0").key)

    def test_no_previous(self):
        self.assertEqual(Version.parse("v0.0.1").previous(TAGS), "")
