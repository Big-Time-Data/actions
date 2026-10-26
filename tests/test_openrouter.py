import io
import json
import unittest
import urllib.error
from unittest import mock

from btd_actions.httpclient import HttpClient
from btd_actions.openrouter import OpenRouter, OpenRouterError


def reply(content, finish="stop"):
    body = {"model": "m", "choices": [{"finish_reason": finish, "message": {"content": content}}], "usage": {}}
    resp = mock.MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps(body).encode()
    return resp


def http_error(code):
    return urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(b"boom"))


class OpenRouterTest(unittest.TestCase):
    def client(self, models=None):
        return OpenRouter("key", models or ["a/model"], http=HttpClient(sleep=lambda _: None))

    def test_request_body(self):
        with mock.patch("urllib.request.urlopen", return_value=reply('{"x": 1}')) as urlopen:
            out = self.client(["a/one", "b/two"]).complete_json(system="s", user="u", name="n", schema={})
        self.assertEqual(out, {"x": 1})
        sent = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(sent["model"], "a/one")
        self.assertEqual(sent["models"], ["a/one", "b/two"])
        self.assertEqual(sent["response_format"]["type"], "json_schema")

    def test_retry_on_server_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=[http_error(500), http_error(429), reply('{"ok": true}')]):
            self.assertEqual(self.client().complete_json(system="s", user="u", name="n", schema={}), {"ok": True})

    def test_no_retry_on_client_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=[http_error(401)]):
            with self.assertRaisesRegex(OpenRouterError, "HTTP 401"):
                self.client().complete_json(system="s", user="u", name="n", schema={})

    def test_length_is_error(self):
        with mock.patch("urllib.request.urlopen", return_value=reply('{"x"', finish="length")):
            with self.assertRaisesRegex(OpenRouterError, "length"):
                self.client().complete_json(system="s", user="u", name="n", schema={})

    def test_parse_fenced_json(self):
        self.assertEqual(OpenRouter.parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(OpenRouter.parse_json('Here: {"a": 2} done'), {"a": 2})
        with self.assertRaises(OpenRouterError):
            OpenRouter.parse_json("no json")
