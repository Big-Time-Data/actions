import unittest
from unittest import mock

from btd_actions.release_notes import Config, ReleaseNotes


def cfg(**kw):
    base = dict(tag="v1.2.0", previous_tag="v1.1.0", target="abc", product="", instructions="",
                slack_lines="3 to 5", max_commits=10, header="", footer="")
    return Config(**{**base, **kw})


class ReleaseNotesTest(unittest.TestCase):
    def git(self, commits):
        git = mock.Mock()
        git.commits.return_value = commits
        return git

    def test_fallback_git_skips_noise(self):
        git = self.git(["- chore: bump (a1)", "- feat: add x (b2)\nbody", "- ci: fix (c3)"])
        notes = ReleaseNotes(cfg(), git, None, None).generate()
        self.assertEqual(notes.source, "git")
        self.assertEqual(notes.slack, ["feat: add x (b2)"])
        git.commits.assert_called_once_with("v1.1.0..abc", 10, body=True)

    def test_no_commits(self):
        llm = mock.Mock()
        notes = ReleaseNotes(cfg(), self.git([]), None, llm).generate()
        llm.complete_json.assert_not_called()
        self.assertEqual((notes.source, notes.slack), ("git", ["No changes since v1.1.0"]))
        self.assertIn("No changes since v1.1.0", notes.body)

    def test_ai_strips_bullets(self):
        llm = mock.Mock()
        llm.complete_json.return_value = {"github_notes": "### Features\n- x", "slack_summary": ["• *x* added", "- y", ""]}
        notes = ReleaseNotes(cfg(), self.git(["- feat: x (a)"]), None, llm).generate()
        self.assertEqual((notes.source, notes.slack), ("ai", ["*x* added", "y"]))

    def test_render_placeholders(self):
        gen = ReleaseNotes(cfg(tag="v2.0.0-beta", header="## App {tag}", footer="Get {version} (from {previous_tag})"), None, None, None)
        out = gen.render(mock.Mock(body="notes"))
        self.assertEqual(out, "## App v2.0.0-beta\n\nnotes\n\nGet 2.0.0-beta (from v1.1.0)\n")
