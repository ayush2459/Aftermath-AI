import unittest

from app.discord_recovery_agent import parse_command
from app.support_router import classify_issue


class DiscordRecoveryCommandTests(unittest.TestCase):
    def test_case_command_extracts_opaque_code(self):
        code = "qwerty_ABC-0123456789abcdefgh"
        self.assertEqual(parse_command(f"@Aftermath Recovery CASE {code}"), ("case", code))

    def test_confirmation_command_extracts_code(self):
        code = "qwerty_ABC-0123456789abcdefgh"
        self.assertEqual(parse_command(f"@Aftermath Recovery CONFIRM {code}"), ("confirm", code))

    def test_confirmation_takes_precedence_if_both_are_present(self):
        case_code = "qwerty_ABC-0123456789abcdefgh"
        self.assertEqual(
            parse_command(f"CASE {case_code} then CONFIRM {case_code}"),
            ("confirm", case_code),
        )

    def test_short_or_unstructured_text_is_ignored(self):
        self.assertIsNone(parse_command("CASE short"))
        self.assertIsNone(parse_command("please fix my shipment"))

    def test_non_command_customer_message_is_routed_to_support_specialist(self):
        self.assertEqual(classify_issue("The dashboard page is broken"), "software_bug")


if __name__ == "__main__":
    unittest.main()
