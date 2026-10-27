-- The fuels sold at Pertamina, Shell, BP and Vivo stations: real data, not dummy. The fuel price page lists them and a
-- refresh from the web looks for their prices (fuel_price.sql seeds their price history).
-- The fuel price workers insert them too when fuel_product has no row at all, as on a first deploy
-- (fuel_price_repository.add_products_if_none), so keep this file one INSERT statement.
-- Running it again updates these rows; other products stay.
INSERT INTO fuel_product (merchant, name, fuel_kind, ron) VALUES
    ('pertamina', 'Pertalite', 'gasoline', 90),
    ('pertamina', 'Pertamax', 'gasoline', 92),
    ('pertamina', 'Pertamax Green 95', 'gasoline', 95),
    ('pertamina', 'Pertamax Turbo', 'gasoline', 98),
    ('pertamina', 'Biosolar', 'diesel', NULL),
    ('pertamina', 'Dexlite', 'diesel', NULL),
    ('pertamina', 'Pertamina Dex', 'diesel', NULL),
    ('shell', 'Shell Super', 'gasoline', 92),
    ('shell', 'Shell V-Power', 'gasoline', 95),
    ('shell', 'Shell V-Power Nitro+', 'gasoline', 98),
    ('shell', 'Shell V-Power Diesel', 'diesel', NULL),
    ('bp', 'BP 90', 'gasoline', 90),
    ('bp', 'BP 92', 'gasoline', 92),
    ('bp', 'BP Ultimate', 'gasoline', 95),
    ('bp', 'BP Ultimate Diesel', 'diesel', NULL),
    ('vivo', 'Revvo 90', 'gasoline', 90),
    ('vivo', 'Revvo 92', 'gasoline', 92),
    ('vivo', 'Revvo 95', 'gasoline', 95),
    ('vivo', 'Diesel Primus Plus', 'diesel', NULL)
ON CONFLICT (merchant, name) DO UPDATE
    SET fuel_kind = EXCLUDED.fuel_kind, ron = EXCLUDED.ron;
