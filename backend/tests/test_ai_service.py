import unittest

from app.ai_service import deterministic_diagnosis, validate_diagnosis


class DiagnosisSchemaTests(unittest.TestCase):
    def test_deterministic_diagnosis_uses_only_known_finding_codes(self):
        findings = [{"code": "payment_captured_shipment_failed", "severity": "high", "message": "Captured but shipment failed"}]
        result = deterministic_diagnosis(
            {"payment": {"status": "captured"}, "shipment": {"status": "failed"}},
            findings,
        )
        checked = validate_diagnosis(result, {"payment_captured_shipment_failed"})
        self.assertEqual(checked["recommended_next_step"], "operator_review")
        self.assertEqual(checked["evidence_refs"], ["payment_captured_shipment_failed"])

    def test_rejects_unknown_evidence_reference(self):
        value = {
            "summary": "Problem",
            "likely_cause": "Cause",
            "evidence_refs": ["invented"],
            "confidence": 0.8,
            "unknowns": [],
            "recommended_next_step": "operator_review",
        }
        with self.assertRaises(ValueError):
            validate_diagnosis(value, set())

    def test_rejects_unsupported_action_recommendation(self):
        value = {
            "summary": "Problem",
            "likely_cause": "Cause",
            "evidence_refs": [],
            "confidence": 0.8,
            "unknowns": [],
            "recommended_next_step": "issue_refund",
        }
        with self.assertRaises(ValueError):
            validate_diagnosis(value, set())


if __name__ == "__main__":
    unittest.main()
