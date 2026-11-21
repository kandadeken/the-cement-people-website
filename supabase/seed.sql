-- =============================================================================
-- Starting price list (seed data)
--
-- The 17 products on thecementpeople.com today, copied from
-- web/src/data/products.json on 21 November 2026. Supabase loads this file
-- into local and test databases. For the real project it is the starting
-- price list, loaded once at go-live (see DEPLOYMENT.md); after that, prices
-- are changed in the admin system, not here.
-- =============================================================================

insert into public.products (site_id, name, category, unit, current_price, published, price_visible) values
  ('c1', 'Supacem 32.5R', 'Cement', '50 kg bag', 75.00, true, true),
  ('c2', 'Supacem 42.5R', 'Cement', '50 kg bag', 98.00, true, true),
  ('c3', 'Dzata 42.5R', 'Cement', '50 kg bag', 110.00, true, true),
  ('c4', 'Ghacem Waterproof 42.5N', 'Cement', '50 kg bag', 120.00, true, true),
  ('i1', 'Iron rod 16 mm', 'Iron Rods (Single Piece)', '30 ft rod', 102.00, true, true),
  ('i2', 'Iron rod 14 mm', 'Iron Rods (Single Piece)', '30 ft rod', 75.00, true, true),
  ('i3', 'Iron rod 12 mm', 'Iron Rods (Single Piece)', '30 ft rod', 58.00, true, true),
  ('i4', 'Iron rod 11.5 mm', 'Iron Rods (Single Piece)', '30 ft rod', 48.00, true, true),
  ('i5', 'Iron rod 10 mm', 'Iron Rods (Single Piece)', '30 ft rod', 40.00, true, true),
  ('i6', 'Iron rod 8 mm', 'Iron Rods (Single Piece)', '30 ft rod', 25.00, true, true),
  ('j1', 'Iron rod 16 mm', 'Iron Rods (Per Ton)', 'ton', 6800.00, true, true),
  ('j2', 'Iron rod 14 mm', 'Iron Rods (Per Ton)', 'ton', 6800.00, true, true),
  ('j3', 'Iron rod 12 mm', 'Iron Rods (Per Ton)', 'ton', 6800.00, true, true),
  ('j4', 'Iron rod 11.5 mm', 'Iron Rods (Per Ton)', 'ton', 6800.00, true, true),
  ('j5', 'Iron rod 10 mm', 'Iron Rods (Per Ton)', 'ton', 6800.00, true, true),
  ('j6', 'Iron rod 8 mm', 'Iron Rods (Per Ton)', 'ton', 6800.00, true, true),
  ('i8', 'Binding wire', 'Binding Wire', 'roll', 60.00, true, true);
