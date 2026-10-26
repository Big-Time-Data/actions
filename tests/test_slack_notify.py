import unittest

from btd_actions.runtime import ActionError
from btd_actions.slack_notify import SlackMessage


class SlackMessageTest(unittest.TestCase):
    def test_colors(self):
        self.assertEqual(SlackMessage.resolve_color("success"), "good")
        self.assertEqual(SlackMessage.resolve_color("failure"), "danger")
        self.assertEqual(SlackMessage.resolve_color(""), "good")
        self.assertEqual(SlackMessage.resolve_color("#A1B2C3"), "#a1b2c3")
        with self.assertRaises(ActionError):
            SlackMessage.resolve_color("purple")

    def test_payload(self):
        att = SlackMessage("Title", "*hi*", "good", "https://x").payload()["attachments"][0]
        self.assertEqual((att["title"], att["text"], att["color"], att["title_link"]), ("Title", "*hi*", "good", "https://x"))
        self.assertNotIn("title_link", SlackMessage("t", "m").payload()["attachments"][0])
