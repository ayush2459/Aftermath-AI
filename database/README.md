# PostgreSQL database

## Bootstrap a fresh local database
Create the database once, then apply the schema and demo seed records:

```powershell
createdb -U postgres aftermath_ai
psql -U postgres -d aftermath_ai -f .\database\schema.sql
```

If the database already exists, skip `createdb`. Back it up first, then apply `razorpay_test_mode_migration.sql` to add payment-provider metadata and the Discord notification outbox. The schema uses `CREATE TABLE IF NOT EXISTS` and seeds the five demo products with `ON CONFLICT` updates to product descriptions/prices/image paths; it does not dump or import any live database records.

## Existing local database
To set the image paths without reseeding schema, run:

```powershell
psql -U postgres -d aftermath_ai -f .\database\update_product_images.sql
```

Only synthetic demo product records belong in this repository. Do not commit database dumps, customer records, passwords, or `.env` files.
