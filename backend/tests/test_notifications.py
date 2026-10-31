import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from io import BytesIO

from app import notifications


class DiscordTransportTests(unittest.TestCase):
    def setUp(self):
        self.old = (
            notifications.DISCORD_BOT_TOKEN,
            notifications.DISCORD_CHANNEL_ID,
            notifications.DISCORD_WEBHOOK_URL,
        )
        notifications.DISCORD_BOT_TOKEN = "test-token"
        notifications.DISCORD_CHANNEL_ID = "123456789"
        notifications.DISCORD_WEBHOOK_URL = ""

    def tearDown(self):
        (
            notifications.DISCORD_BOT_TOKEN,
            notifications.DISCORD_CHANNEL_ID,
            notifications.DISCORD_WEBHOOK_URL,
        ) = self.old

    @patch("app.notifications.urllib.request.urlopen")
    def test_bot_transport_posts_embed_with_auth_and_user_agent(self, urlopen):
        response = MagicMock()
        response.status = 200
        urlopen.return_value.__enter__.return_value = response

        payload = {"embeds": [{"title": "Incident test"}]}
        self.assertTrue(notifications._send_discord(payload))

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://discord.com/api/v10/channels/123456789/messages")
        self.assertEqual(request.get_header("Authorization"), "Bot test-token")
        self.assertEqual(request.get_header("User-agent"), "AftermathAI/1.0")
        self.assertEqual(json.loads(request.data), payload)

    @patch("app.notifications.urllib.request.urlopen")
    def test_webhook_fallback_is_used_when_bot_is_not_configured(self, urlopen):
        notifications.DISCORD_BOT_TOKEN = ""
        notifications.DISCORD_CHANNEL_ID = ""
        notifications.DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/test/secret"
        response = MagicMock()
        response.status = 204
        urlopen.return_value.__enter__.return_value = response

        self.assertTrue(notifications._send_discord({"content": "hello"}))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, notifications.DISCORD_WEBHOOK_URL)
        self.assertIsNone(request.get_header("Authorization"))

    @patch("app.notifications.urllib.request.urlopen")
    def test_http_error_includes_discord_response_without_logging_credentials(self, urlopen):
        error = HTTPError(
            "https://discord.com/api/v10/channels/123/messages",
            403,
            "Forbidden",
            {},
            BytesIO(b'{"message":"Missing Permissions","code":50013}'),
        )
        urlopen.side_effect = error
        with self.assertRaisesRegex(RuntimeError, "Missing Permissions"):
            notifications._send_discord({"content": "hello"})

    def test_missing_configuration_returns_false(self):
        notifications.DISCORD_BOT_TOKEN = ""
        notifications.DISCORD_CHANNEL_ID = ""
        notifications.DISCORD_WEBHOOK_URL = ""
        self.assertFalse(notifications._send_discord({"content": "hello"}))


if __name__ == "__main__":
    unittest.main()
