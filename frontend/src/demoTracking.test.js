import test from "node:test";
import assert from "node:assert/strict";
import { isSeededDemoFailure, sampleJourneyStage, sampleTrackingNumber, shouldOpenSampleJourney, shouldShowSampleResolution } from "./demoTracking.js";

test("sample tracking references are stable and only created for seeded failures", () => {
  const shipment = {
    shipment_id: "10dcf829-777b-43b7-8f1c-f2f058b90ba3",
    shipment_status: "failed",
    last_error: "Seeded demo failure: carrier allocation timeout"
  };

  assert.equal(isSeededDemoFailure(shipment), true);
  assert.equal(isSeededDemoFailure({ ...shipment, shipment_status: "shipped" }), false);
  assert.equal(shouldOpenSampleJourney({ ...shipment, payment_status: "captured" }), true);
  assert.equal(shouldOpenSampleJourney({ ...shipment, payment_status: "pending" }), false);
  assert.equal(shouldOpenSampleJourney({ ...shipment, payment_status: "captured", last_error: "Carrier timeout" }), false);
  assert.equal(sampleTrackingNumber(shipment), "DEMO-10DCF829777B43B78F1CF2F058B90BA3");
  assert.equal(sampleTrackingNumber({ ...shipment, last_error: null }), null);
  assert.equal(sampleTrackingNumber({ last_error: shipment.last_error }), null);
  assert.equal(shouldShowSampleResolution(shipment), false);
  assert.equal(shouldShowSampleResolution({ ...shipment, demo_recovery_status: "completed" }), true);
});

test("sample journey advances from the recorded failure time", () => {
  const startedAt = 1_000_000;
  assert.equal(sampleJourneyStage(startedAt, startedAt), 0);
  assert.equal(sampleJourneyStage(startedAt, startedAt + 5999), 0);
  assert.equal(sampleJourneyStage(startedAt, startedAt + 6000), 1);
  assert.equal(sampleJourneyStage(startedAt, startedAt + 30_000), 5);
  assert.equal(sampleJourneyStage(startedAt, startedAt + 300_000), 5);
  assert.equal(sampleJourneyStage(startedAt, startedAt - 1000), 0);
  assert.equal(sampleJourneyStage(Number.NaN, startedAt), 5);
});
