CREATE VIEW ${catalog}.${schema}.genie_truth_lab_booking_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: "(SELECT bookings.booking_id, bookings.property_id, bookings.check_in, bookings.check_out, bookings.total_amount, bookings.status, properties.title AS property_title, properties.property_type FROM samples.wanderbricks.bookings AS bookings JOIN samples.wanderbricks.properties AS properties ON bookings.property_id = properties.property_id)"
  dimensions:
    - name: Booking Month
      expr: "DATE_TRUNC('MONTH', check_in)"
    - name: Booking Status
      expr: status
    - name: Property ID
      expr: property_id
    - name: Property Title
      expr: property_title
    - name: Property Type
      expr: property_type
  measures:
    - name: Booking Count
      expr: COUNT(1)
    - name: Gross Booked Value
      expr: SUM(total_amount)
    - name: Average Stay Nights
      expr: AVG(DATEDIFF(check_out, check_in))
    - name: Booked Property Count
      expr: COUNT(DISTINCT property_id)
$$;
