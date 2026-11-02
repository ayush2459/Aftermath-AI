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


    def test_normalizes_qualitative_and_percentage_confidence(self):
        base = {
            "summary": "Problem",
            "likely_cause": "Cause",
            "evidence_refs": [],
            "unknowns": [],
            "recommended_next_step": "operator_review",
        }
        for raw, expected in (("high", 0.8), ("MEDIUM", 0.5), ("low", 0.2), ("80%", 0.8), ("80", 0.8), ("0.8", 0.8), (80, 0.8)):
            with self.subTest(raw=raw):
                result = validate_diagnosis({**base, "confidence": raw}, set())
                self.assertAlmostEqual(result["confidence"], expected)

    def test_confidence_validation_does_not_mutate_model_payload(self):
        value = {
            "summary": "Problem",
            "likely_cause": "Cause",
            "evidence_refs": [],
            "confidence": "75%",
            "unknowns": [],
            "recommended_next_step": "operator_review",
        }
        result = validate_diagnosis(value, set())
        self.assertEqual(value["confidence"], "75%")
        self.assertEqual(result["confidence"], 0.75)

    def test_rejects_invalid_confidence_values(self):
        base = {
            "summary": "Problem",
            "likely_cause": "Cause",
            "evidence_refs": [],
            "unknowns": [],
            "recommended_next_step": "operator_review",
        }
        for raw in (True, "certain", "101%", -1, float("nan"), float("inf"), None):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    validate_diagnosis({**base, "confidence": raw}, set())

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
