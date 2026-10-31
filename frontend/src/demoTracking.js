export const isSeededDemoFailure = (shipment) =>
  shipment?.shipment_status === "failed" &&
  shipment.last_error?.startsWith("Seeded demo failure:");

export const shouldOpenSampleJourney = (order) =>
  order?.payment_status === "captured" && isSeededDemoFailure(order);

export const sampleTrackingNumber = (shipment) => {
  if (!isSeededDemoFailure(shipment) || !shipment.shipment_id) {
    return null;
  }

  return `DEMO-${shipment.shipment_id.replaceAll("-", "").toUpperCase()}`;
};

export const shouldShowSampleResolution = (shipment, sampleViewOrderId) =>
  Boolean(sampleViewOrderId) &&
  shipment?.order_id === sampleViewOrderId &&
  shipment.demo_recovery_status === "completed" &&
  Boolean(sampleTrackingNumber(shipment));

export const sampleJourneyStage = (startedAt, now, stepCount = 6) => {
  if (!Number.isFinite(startedAt)) return stepCount - 1;
  return Math.min(
    Math.max(0, Math.floor((now - startedAt) / 6000)),
    stepCount - 1
  );
};
