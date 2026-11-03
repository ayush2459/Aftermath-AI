import test from "node:test";
import assert from "node:assert/strict";
import { buildCustomerJourney } from "./shipmentJourney.js";

const base = {
  order_status: "recovery_required",
  shipment_status: "failed",
  last_error: "Seeded demo failure: carrier allocation timeout"
};

test("failed order stops at shipment creation and leaves later stages pending", () => {
  const steps = buildCustomerJourney(base, []);
  assert.equal(steps[0].state, "complete");
  assert.equal(steps[1].state, "complete");
  assert.equal(steps[2].state, "failed");
  assert.deepEqual(steps.slice(3).map((step) => step.state), [
    "upcoming", "upcoming", "upcoming", "upcoming"
  ]);
});

test("Discord recovery completes shipment creation but does not invent carrier scans", () => {
  const steps = buildCustomerJourney(
    { ...base, order_status: "restored", shipment_status: "created", carrier_code: "AFTERMATH-DEMO" },
    [{ event_type: "discord_simulated_shipment_restored", occurred_at: "2026-11-02T10:12:01Z" }]
  );
  assert.equal(steps[2].state, "complete");
  assert.deepEqual(steps.slice(3).map((step) => step.state), [
    "upcoming", "upcoming", "upcoming", "upcoming"
  ]);
  assert.equal(steps[2].time, "2026-11-02T10:12:01Z");
});

test("carrier scans advance only the milestones supported by recorded events", () => {
  const steps = buildCustomerJourney(
    { ...base, order_status: "shipped", shipment_status: "in_transit" },
    [
      { event_type: "carrier_picked_up", occurred_at: "2026-11-02T10:00:00Z" },
      { event_type: "shipment_in_transit", occurred_at: "2026-11-02T11:00:00Z" }
    ]
  );
  assert.deepEqual(steps.map((step) => step.state), [
    "complete", "complete", "complete", "complete", "complete", "upcoming", "upcoming"
  ]);
});

test("delivered status completes the full customer journey", () => {
  const steps = buildCustomerJourney(
    { ...base, order_status: "delivered", shipment_status: "delivered" },
    [{ event_type: "shipment_delivered", occurred_at: "2026-11-02T15:00:00Z" }]
  );
  assert.ok(steps.every((step) => step.state === "complete"));
});
