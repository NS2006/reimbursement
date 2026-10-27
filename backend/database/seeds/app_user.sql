-- Seed: website users (local development only; fake addresses, no real people).
-- Safe to run again: an existing email keeps its row and only gets its name updated.
BEGIN;

INSERT INTO app_user (email, name) VALUES
    ('admin@example.com',    'Admin'),
    ('reviewer1@example.com', 'Reviewer One'),
    ('reviewer2@example.com', 'Reviewer Two'),
    ('niko.sutiono@gdn-commerce.com', 'Niko Sutiono')
ON CONFLICT (email) DO UPDATE
    SET name = EXCLUDED.name;

COMMIT;

-- \i backend/database/seeds/app_user.sql