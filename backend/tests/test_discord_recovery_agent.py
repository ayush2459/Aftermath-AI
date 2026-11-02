import unittest

from app.discord_recovery_agent import (
    format_case_reply,
    format_confirmation_reply,
    parse_command,
)
from app.support_router import classify_issue


class DiscordRecoveryCommandTests(unittest.TestCase):
    def test_case_command_extracts_opaque_code(self):
        code = "qwerty_ABC-0123456789abcdefgh"
        self.assertEqual(parse_command(f"@Aftermath Recovery CASE {code}"), ("case", code))

    def test_status_command_extracts_opaque_code_without_becoming_confirmation(self):
        code = "qwerty_ABC-0123456789abcdefgh"
        self.assertEqual(parse_command(f"STATUS {code}"), ("status", code))

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

    def test_case_reply_explains_diagnosis_approved_action_and_confirmation(self):
        code = "qwerty_ABC-0123456789abcdefgh"
        reply = format_case_reply({
            "order_id": "12345678-1234-1234-1234-123456789abc",
            "order_status": "paid",
            "payment_status": "captured",
            "shipment_status": "failed",
            "diagnosis": {
                "summary": "Shipment creation timed out after payment capture.",
                "root_cause": "Carrier adapter timeout",
                "confidence": 0.82,
            },
            "plan": {"actions": [{
                "action_type": "reconcile_shipment_with_carrier",
                "description": "Reconcile the simulated shipment record.",
            }]},
        }, code)
        self.assertIn("Shipment creation timed out", reply)
        self.assertIn("Carrier adapter timeout", reply)
        self.assertIn("82%", reply)
        self.assertIn("CONFIRM " + code, reply)
        self.assertIn("no physical parcel", reply)

    def test_confirmation_reply_requires_all_verified_states_and_safe_url(self):
        reply = format_confirmation_reply({
            "status": "completed",
            "customer_url": "https://shop.example/shipments?view=recovered&share=opaque",
            "verification": {
                "order_status": "restored",
                "shipment_status": "created",
                "incident_status": "resolved",
                "carrier_code": "AFTERMATH-DEMO",
                "tracking_number": "AFTER-1234567890",
            },
        })
        self.assertIn("[Open your corrected shipment page]", reply)
        self.assertIn("AFTER-1234567890", reply)
        self.assertIn("no real parcel", reply)

    def test_confirmation_reply_never_claims_success_without_verification(self):
        with self.assertRaises(RuntimeError):
            format_confirmation_reply({
                "status": "completed",
                "customer_url": "https://shop.example/shipments",
                "verification": {
                    "order_status": "restored",
                    "shipment_status": "created",
                    "incident_status": "pending",
                    "carrier_code": "AFTERMATH-DEMO",
                },
            })

    def test_confirmation_reply_rejects_non_http_links(self):
        with self.assertRaises(RuntimeError):
            format_confirmation_reply({
                "status": "completed",
                "customer_url": "javascript:alert(1)",
                "verification": {
                    "order_status": "restored",
                    "shipment_status": "created",
                    "incident_status": "resolved",
                    "carrier_code": "AFTERMATH-DEMO",
                },
            })


if __name__ == "__main__":
    unittest.main()
