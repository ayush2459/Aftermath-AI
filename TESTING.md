# Testing Aftermath AI

Use a disposable PostgreSQL database and Razorpay Test Mode credentials for the checkout checks. Follow the [setup guide](README.md#getting-started) before running the application. Never use a real payment or delivery to exercise the seeded failure flow.

## Automated checks

From the repository root, run the backend tests and syntax check:

```powershell
$env:PYTHONPATH = 'backend'
python -m unittest discover -s backend/tests -p 'test_*.py' -v
python -m compileall backend/app
```

From `frontend/`, run:

```powershell
npm ci
npm test
npm run build
```

The backend tests cover access to the sample recovery action, payment and failure eligibility, and its recorded event. The frontend tests cover sample tracking references and timeline progression. These checks do not prove that a real carrier created or delivered a parcel.

## Local checkout and shipment check

1. Start the backend and frontend as described in the [setup guide](README.md#getting-started). Check that `http://127.0.0.1:8000/health` reports a working database and that the storefront loads products.
2. Complete a Razorpay Test Mode checkout with automatic payment capture enabled. The app should open `/shipments?order=<order-uuid>` and display the deliberately failed shipment and its incident.
3. Open `/shipments?order=<order-uuid>&recover=1` in the **same browser session**. Confirm that the page offers **Show resolution**. Click it once; the address should become `/shipments?order=<order-uuid>&view=sample`, showing the delivery journey one stage at a time. The Delivered/Resolved demo result and illustrative tracking number should appear only after the final stage. Refresh the page and confirm the result persists. Replaying the journey must not create a duplicate event.
4. Return to the normal `/shipments?order=<order-uuid>` address. It must still show the failed shipment, even after the sample view was completed.
5. Check the shipment status and issue history for that order in the backend documentation at `http://127.0.0.1:8000/docs`. They must still report the original seeded failure; sample recovery must not change the real order, shipment, payment, or incident records.
6. Check an unrelated browser session or order. It must not be able to complete the sample recovery for the first order. A real, unseeded failure and an order without captured test payment must remain ineligible.

The sample Delivered view is illustrative. Real shipment and delivery status require carrier integration. Record which checks actually ran and whether the local page picked up the latest update before telling a customer it is available.
