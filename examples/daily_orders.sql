SELECT
    order_date,
    COUNT(*) AS order_count,
    SUM(net_amount) AS net_revenue
FROM curated.orders
WHERE order_date >= current_date - INTERVAL '7' DAY
GROUP BY order_date
ORDER BY order_date;

