import unittest

from app.support_router import classify_issue, _redact


class UnifiedSupportRoutingTests(unittest.TestCase):
    def test_routes_shipment_before_generic_bug_terms(self):
        self.assertEqual(classify_issue("My shipment tracking page shows an error"), "shipment_recovery")

    def test_routes_payment_and_account_issues(self):
        self.assertEqual(classify_issue("I was charged twice at checkout"), "payment_support")
        self.assertEqual(classify_issue("I cannot log in to my account"), "account_support")

    def test_routes_software_bugs(self):
        self.assertEqual(classify_issue("The dashboard button is broken"), "software_bug")
        self.assertEqual(classify_issue("The page is not loading"), "software_bug")

    def test_defaults_to_general_support(self):
        self.assertEqual(classify_issue("I have a question about my profile"), "general_support")

    def test_redacts_common_credentials_and_email_addresses(self):
        value = _redact("Contact me at person@example.com, token ghp_123456789012345678901234")
        self.assertNotIn("person@example.com", value)
        self.assertNotIn("ghp_123456789012345678901234", value)
        self.assertIn("[redacted", value)
        card = _redact("My card number is 4111 1111 1111 1111")
        self.assertNotIn("4111 1111 1111 1111", card)


if __name__ == "__main__":
    unittest.main()
