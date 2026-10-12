-- Gold answers for Genie Truth Lab Chat-mode evaluation.
-- Keep selected columns and aliases stable because native result comparison
-- can mark extra columns as incorrect.

-- family: monthly-booking-volume
SELECT
  DATE_TRUNC('MONTH', bookings.check_in) AS check_in_month,
  COUNT(*) AS booking_count
FROM samples.wanderbricks.bookings AS bookings
GROUP BY DATE_TRUNC('MONTH', bookings.check_in)
ORDER BY check_in_month;

-- family: monthly-gross-booked-value
SELECT
  DATE_TRUNC('MONTH', bookings.check_in) AS check_in_month,
  SUM(bookings.total_amount) AS gross_booked_value
FROM samples.wanderbricks.bookings AS bookings
GROUP BY DATE_TRUNC('MONTH', bookings.check_in)
ORDER BY check_in_month;

-- family: booking-status-mix
SELECT
  bookings.status,
  COUNT(*) AS booking_count
FROM samples.wanderbricks.bookings AS bookings
GROUP BY bookings.status
ORDER BY booking_count DESC, bookings.status;

-- family: property-gross-booked-value
SELECT
  properties.property_id,
  properties.title AS property_title,
  SUM(bookings.total_amount) AS gross_booked_value
FROM samples.wanderbricks.bookings AS bookings
JOIN samples.wanderbricks.properties AS properties
  ON bookings.property_id = properties.property_id
GROUP BY properties.property_id, properties.title
ORDER BY gross_booked_value DESC, properties.property_id
LIMIT 20;

-- family: average-stay-length
SELECT
  properties.property_type,
  AVG(DATEDIFF(bookings.check_out, bookings.check_in)) AS average_stay_nights
FROM samples.wanderbricks.bookings AS bookings
JOIN samples.wanderbricks.properties AS properties
  ON bookings.property_id = properties.property_id
GROUP BY properties.property_type
ORDER BY average_stay_nights DESC, properties.property_type;

-- family: booked-property-type-mix
SELECT
  properties.property_type,
  COUNT(DISTINCT bookings.property_id) AS booked_property_count
FROM samples.wanderbricks.bookings AS bookings
JOIN samples.wanderbricks.properties AS properties
  ON bookings.property_id = properties.property_id
GROUP BY properties.property_type
ORDER BY booked_property_count DESC, properties.property_type;
