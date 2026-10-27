-- The reports claiming the same receipt (schema.sql receipt_matches), for every report the seeds inserted: the
-- website's API and the OCR worker store them as reports and readings come in, the seeds insert their rows directly.
-- Run after every other seed. Running it again only adds what is missing, so it also rebuilds the pairs of a
-- database filled some other way.
SELECT store_receipt_matches(NULL) AS same_receipt_pairs \gset
