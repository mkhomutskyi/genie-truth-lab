-- Genie Truth Lab source profiling
-- Read-only by design. Run each statement separately if the client does not
-- support multi-statement execution.

SHOW TABLES IN samples.wanderbricks;

DESCRIBE TABLE samples.wanderbricks.bookings;
DESCRIBE TABLE samples.wanderbricks.properties;
DESCRIBE TABLE samples.wanderbricks.reviews;
DESCRIBE TABLE samples.wanderbricks.destinations;
DESCRIBE TABLE samples.wanderbricks.payments;
DESCRIBE TABLE samples.wanderbricks.booking_updates;

SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT bookings.booking_id) AS distinct_booking_ids,
  MIN(bookings.check_in) AS min_check_in,
  MAX(bookings.check_in) AS max_check_in,
  MIN(bookings.check_out) AS min_check_out,
  MAX(bookings.check_out) AS max_check_out,
  COUNT_IF(bookings.check_in IS NULL) AS null_check_in,
  COUNT_IF(bookings.check_out IS NULL) AS null_check_out,
  COUNT_IF(bookings.check_out <= bookings.check_in) AS nonpositive_stays,
  COUNT_IF(bookings.total_amount IS NULL) AS null_total_amount,
  COUNT_IF(bookings.total_amount < 0) AS negative_total_amount_rows,
  COUNT_IF(bookings.property_id IS NULL) AS null_property_id
FROM samples.wanderbricks.bookings AS bookings;

SELECT
  bookings.status,
  COUNT(*) AS booking_count
FROM samples.wanderbricks.bookings AS bookings
GROUP BY bookings.status
ORDER BY booking_count DESC, bookings.status;

SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT properties.property_id) AS distinct_property_ids,
  COUNT(DISTINCT properties.title) AS distinct_titles,
  COUNT_IF(properties.property_id IS NULL) AS null_property_id,
  COUNT_IF(properties.title IS NULL) AS null_titles,
  COUNT_IF(properties.property_type IS NULL) AS null_property_types
FROM samples.wanderbricks.properties AS properties;

SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT reviews.review_id) AS distinct_review_ids,
  MIN(reviews.rating) AS min_rating,
  MAX(reviews.rating) AS max_rating,
  COUNT_IF(reviews.rating IS NULL) AS null_ratings,
  COUNT_IF(reviews.property_id IS NULL) AS null_property_id,
  COUNT_IF(reviews.is_deleted IS NULL) AS null_is_deleted
FROM samples.wanderbricks.reviews AS reviews;

SELECT
  reviews.is_deleted,
  COUNT(*) AS review_count
FROM samples.wanderbricks.reviews AS reviews
GROUP BY reviews.is_deleted
ORDER BY reviews.is_deleted;

SELECT
  COUNT(*) AS bookings_rows,
  COUNT_IF(properties.property_id IS NULL) AS bookings_without_property
FROM samples.wanderbricks.bookings AS bookings
LEFT JOIN samples.wanderbricks.properties AS properties
  ON bookings.property_id = properties.property_id;

SELECT
  COUNT(*) AS property_rows,
  COUNT(DISTINCT properties.property_id) AS distinct_property_ids,
  COUNT(*) - COUNT(DISTINCT properties.property_id) AS duplicate_property_ids
FROM samples.wanderbricks.properties AS properties;

SELECT COUNT(*) AS row_count
FROM samples.wanderbricks.destinations;

SELECT
  COUNT(*) AS joined_rows,
  COUNT(DISTINCT bookings.booking_id) AS distinct_bookings,
  COUNT(*) - COUNT(DISTINCT bookings.booking_id) AS join_row_expansion
FROM samples.wanderbricks.bookings AS bookings
JOIN samples.wanderbricks.properties AS properties
  ON bookings.property_id = properties.property_id;

SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT payments.payment_id) AS distinct_payment_ids,
  COUNT_IF(payments.amount < 0) AS negative_amount_rows,
  COUNT(DISTINCT payments.booking_id) AS bookings_with_payments,
  ROUND(COUNT(*) / COUNT(DISTINCT payments.booking_id), 2) AS average_rows_per_booking
FROM samples.wanderbricks.payments AS payments;

SELECT MAX(payment_rows) AS maximum_rows_per_booking
FROM (
  SELECT payments.booking_id, COUNT(*) AS payment_rows
  FROM samples.wanderbricks.payments AS payments
  GROUP BY payments.booking_id
);

SELECT COUNT(*) AS payment_booking_orphans
FROM samples.wanderbricks.payments AS payments
LEFT JOIN samples.wanderbricks.bookings AS bookings
  ON payments.booking_id = bookings.booking_id
WHERE bookings.booking_id IS NULL;

SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT booking_updates.booking_id) AS bookings_with_updates,
  ROUND(
    COUNT(*) / COUNT(DISTINCT booking_updates.booking_id),
    2
  ) AS average_rows_per_booking
FROM samples.wanderbricks.booking_updates AS booking_updates;

SELECT MAX(update_rows) AS maximum_rows_per_booking
FROM (
  SELECT booking_updates.booking_id, COUNT(*) AS update_rows
  FROM samples.wanderbricks.booking_updates AS booking_updates
  GROUP BY booking_updates.booking_id
);

SELECT COUNT(*) AS update_booking_orphans
FROM samples.wanderbricks.booking_updates AS booking_updates
LEFT JOIN samples.wanderbricks.bookings AS bookings
  ON booking_updates.booking_id = bookings.booking_id
WHERE bookings.booking_id IS NULL;

SELECT COUNT(DISTINCT reviews.booking_id) AS bookings_with_reviews
FROM samples.wanderbricks.reviews AS reviews
JOIN samples.wanderbricks.bookings AS bookings
  ON reviews.booking_id = bookings.booking_id;

WITH payment_totals AS (
  SELECT
    payments.booking_id,
    SUM(payments.amount) AS payment_amount
  FROM samples.wanderbricks.payments AS payments
  GROUP BY payments.booking_id
)
SELECT ROUND(
  100.0 * COUNT_IF(
    ABS(bookings.total_amount - payment_totals.payment_amount) > 1
  ) / COUNT(*),
  1
) AS percent_differing_by_more_than_1_unit
FROM samples.wanderbricks.bookings AS bookings
JOIN payment_totals
  ON bookings.booking_id = payment_totals.booking_id;
