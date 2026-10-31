export const sampleTrackingNumber = (shipment) => {
  if (
    !shipment?.last_error?.startsWith("Seeded demo failure:") ||
    !shipment.shipment_id
  ) {
    return null;
  }

  return `DEMO-${shipment.shipment_id.replaceAll("-", "").toUpperCase()}`;
};
