import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from app import ghosttrail_worker


class GhostTrailWorkerTests(unittest.TestCase):
    def test_job_runs_investigation_proposal_and_discord_handoff(self):
        incident_id = uuid4()
        plan_id = uuid4()
        expires_at = datetime.now(timezone.utc)
        with (
            patch.object(ghosttrail_worker, "diagnose_incident", return_value={
                "diagnosis_id": str(uuid4()), "provider": "deterministic_fallback"
            }) as diagnose,
            patch.object(ghosttrail_worker, "propose_recovery", return_value={
                "plan_id": str(plan_id)
            }) as propose,
            patch.object(ghosttrail_worker, "create_handoff", return_value={
                "case_code": "A" * 32, "expires_at": expires_at
            }) as handoff,
            patch.object(ghosttrail_worker, "text") as sql_text,
        ):
            # The orchestration uses SQLAlchemy text for idempotent lookups.
            sql_text.side_effect = lambda value: value
            class Result:
                def mappings(self):
                    return self
                def first(self):
                    return None
            db = type("DB", (), {"execute": lambda self, *args, **kwargs: Result()})()
            result = ghosttrail_worker.process_job(db, {
                "incident_id": incident_id,
                "customer_session": "customer-session-test",
                "order_id": uuid4(),
            })

        diagnose.assert_called_once()
        propose.assert_called_once()
        handoff.assert_called_once()
        self.assertEqual(result["plan_id"], str(plan_id))
        self.assertEqual(result["case_code"], "A" * 32)
        self.assertTrue(result["simulation_only"])


if __name__ == "__main__":
    unittest.main()
