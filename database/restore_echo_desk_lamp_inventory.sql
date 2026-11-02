-- Restore the seeded demo inventory for Echo Desk Lamp.
-- Existing orders and order_items remain untouched. Apply once to an existing database.
UPDATE products
SET stock_quantity = 18
WHERE product_id = 'echo-desk-lamp'
  AND is_active = TRUE
  AND stock_quantity < 18;
