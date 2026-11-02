const buildCustomerJourney = (shipment, events = []) => {
  const status = String(shipment.shipment_status || "unknown").toLowerCase();
  const eventText = events.map((event) => String(event.event_type || "").toLowerCase()).join(" ");
  const has = (...terms) => terms.some((term) => eventText.includes(term));
  const failed = status === "failed" || status === "unknown";
  const delivered = status === "delivered" || has("delivered", "delivery_confirmed");
  const outForDelivery = delivered || status === "out_for_delivery" || has("out_for_delivery");
  const inTransit = outForDelivery || status === "in_transit" || has("in_transit", "departed_facility");
  const pickedUp = inTransit || has("picked_up", "carrier_pickup", "collected");
  const shipmentCreated = !failed && ["created", "label_created", "picked_up", "in_transit", "out_for_delivery", "delivered"].includes(status);
  const firstEvent = (...terms) => events.find((event) => terms.some((term) => String(event.event_type || "").toLowerCase().includes(term)));
  const createdEvent = firstEvent("shipment_created", "discord_simulated_shipment_restored");
  const pickupEvent = firstEvent("picked_up", "carrier_pickup", "collected");
  const transitEvent = firstEvent("in_transit", "departed_facility");
  const outEvent = firstEvent("out_for_delivery");
  const deliveredEvent = firstEvent("delivered", "delivery_confirmed");
  const paymentDone = events.some((event) => String(event.event_type || "").toLowerCase().includes("payment")) ||
    ["captured", "paid", "verified"].includes(String(shipment.payment_status || "").toLowerCase()) ||
    shipment.order_status !== "payment_pending";
  const milestones = [
    { title: "Order placed", detail: "Your order was recorded by the store.", done: true, time: shipment.order_created_at },
    { title: "Payment confirmed", detail: "Payment confirmation is based on the backend payment record.", done: paymentDone },
    { title: "Shipment created", detail: failed ? (shipment.last_error || "Shipment creation has not been confirmed.") : "A shipment record is present in the order system.", done: shipmentCreated, failed, time: createdEvent?.occurred_at || (shipmentCreated ? shipment.shipment_updated_at : null) },
    { title: "Carrier pickup", detail: pickedUp ? "Pickup is recorded in the shipment event history." : "Waiting for a carrier pickup scan.", done: pickedUp, time: pickupEvent?.occurred_at },
    { title: "In transit", detail: inTransit ? "A transit scan is recorded." : "This step remains pending until a carrier reports movement.", done: inTransit, time: transitEvent?.occurred_at },
    { title: "Out for delivery", detail: outForDelivery ? "The carrier has reported the parcel out for delivery." : "Waiting for an out-for-delivery scan.", done: outForDelivery, time: outEvent?.occurred_at },
    { title: "Delivered", detail: delivered ? "Delivery is recorded in the shipment status or event history." : "Delivery confirmation has not been received.", done: delivered, time: deliveredEvent?.occurred_at }
  ];
  return milestones.map((step, index) => ({
    ...step,
    state: step.failed ? "failed" : step.done ? "complete" : "upcoming",
    number: index + 1
  }));
};
