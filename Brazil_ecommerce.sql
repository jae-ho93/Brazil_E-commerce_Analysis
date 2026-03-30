USE Brazilian;

#master view
CREATE OR REPLACE VIEW vw_region_order_master AS
SELECT
    o.order_id,
    c.customer_unique_id,
    c.customer_state,
    c.customer_city,

    oi.order_item_id,
    oi.product_id,
    oi.seller_id,
    oi.price,
    oi.freight_value,
    (oi.price + oi.freight_value) AS total_item_value,

    p.product_category_name,
    t.product_category_name_english,

    s.seller_state,
    s.seller_city,

    o.order_status,
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,

    r.review_score,

    TIMESTAMPDIFF(
        DAY,
        o.order_purchase_timestamp,
        o.order_delivered_customer_date
    ) AS delivery_days,

    CASE
        WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1
        ELSE 0
    END AS is_delayed,

    YEAR(o.order_purchase_timestamp) AS order_year,
    MONTH(o.order_purchase_timestamp) AS order_month
FROM olist_customers_dataset c
JOIN olist_orders_dataset o
    ON c.customer_id = o.customer_id
JOIN olist_order_items_dataset oi
    ON o.order_id = oi.order_id
LEFT JOIN olist_order_reviews_dataset r
    ON o.order_id = r.order_id
LEFT JOIN olist_products_dataset p
    ON oi.product_id = p.product_id
LEFT JOIN product_category_name_translation t
    ON p.product_category_name = t.product_category_name
LEFT JOIN olist_sellers_dataset s
    ON oi.seller_id = s.seller_id
WHERE o.order_status = 'delivered';


#A-1 지역별 주문 수 / 고객 수 / 매출
SELECT
    customer_state,
    COUNT(DISTINCT order_id) AS total_orders,
    COUNT(DISTINCT customer_unique_id) AS total_customers,
    ROUND(SUM(total_item_value), 2) AS total_sales,
    ROUND(SUM(total_item_value) / COUNT(DISTINCT order_id), 2) AS avg_order_value
FROM vw_region_order_master
GROUP BY customer_state
ORDER BY total_sales DESC;

#A-2 지역별 월별 매출 추이
SELECT
    customer_state,
    order_year,
    order_month,
    ROUND(SUM(total_item_value), 2) AS monthly_sales,
    COUNT(DISTINCT order_id) AS monthly_orders
FROM vw_region_order_master
GROUP BY customer_state, order_year, order_month
ORDER BY customer_state, order_year, order_month;

#B-1 지역별 인기 카테고리 TOP5
WITH category_rank AS (
    SELECT
        customer_state,
        COALESCE(product_category_name_english, 'unknown') AS category_name,
        COUNT(*) AS item_count,
        ROUND(SUM(total_item_value), 2) AS category_sales,
        ROW_NUMBER() OVER (
            PARTITION BY customer_state
            ORDER BY COUNT(*) DESC
        ) AS rn
    FROM vw_region_order_master
    GROUP BY customer_state, COALESCE(product_category_name_english, 'unknown')
)
SELECT
    customer_state,
    category_name,
    item_count,
    category_sales
FROM category_rank
WHERE rn <= 5
ORDER BY customer_state, item_count DESC;

#B-2 지역별 평균 상품 가격 / 배송
SELECT
    customer_state,
    ROUND(AVG(price), 2) AS avg_product_price,
    ROUND(AVG(freight_value), 2) AS avg_freight_value,
    ROUND(AVG(total_item_value), 2) AS avg_total_item_value
FROM vw_region_order_master
GROUP BY customer_state
ORDER BY avg_total_item_value DESC;

#B-3 지역별 고가/저가 상품 비중
SELECT
    customer_state,
    SUM(CASE WHEN price < 50 THEN 1 ELSE 0 END) AS low_price_items,
    SUM(CASE WHEN price BETWEEN 50 AND 200 THEN 1 ELSE 0 END) AS mid_price_items,
    SUM(CASE WHEN price > 200 THEN 1 ELSE 0 END) AS high_price_items
FROM vw_region_order_master
GROUP BY customer_state
ORDER BY high_price_items DESC;

#C-1 지역별 평균 배송일수
SELECT
    customer_state,
    COUNT(DISTINCT order_id) AS total_orders,
    ROUND(AVG(delivery_days), 2) AS avg_delivery_days
FROM vw_region_order_master
WHERE delivery_days IS NOT NULL
GROUP BY customer_state
ORDER BY avg_delivery_days DESC;

#C-2 지역별 배송 지연률
SELECT
    customer_state,
    COUNT(DISTINCT order_id) AS total_orders,
    SUM(is_delayed) AS delayed_orders,
    ROUND(100 * SUM(is_delayed) / COUNT(*), 2) AS delay_rate_pct
FROM vw_region_order_master
GROUP BY customer_state
ORDER BY delay_rate_pct DESC;

#C-3 주문 기준 지역별 지연률
SELECT
    customer_state,
    COUNT(DISTINCT order_id) AS total_orders,
    SUM(order_delay_flag) AS delayed_orders,
    ROUND(100 * SUM(order_delay_flag) / COUNT(DISTINCT order_id), 2) AS delay_rate_pct
FROM (
    SELECT
        order_id,
        customer_state,
        MAX(is_delayed) AS order_delay_flag
    FROM vw_region_order_master
    GROUP BY order_id, customer_state
) x
GROUP BY customer_state
ORDER BY delay_rate_pct DESC;

#D-1 지역별 평균 리뷰 점수
SELECT
    customer_state,
    COUNT(DISTINCT order_id) AS total_orders,
    ROUND(AVG(review_score), 2) AS avg_review_score
FROM vw_region_order_master
WHERE review_score IS NOT NULL
GROUP BY customer_state
ORDER BY avg_review_score DESC;

#D-2 지역별 리뷰 분포(저평가 비중)
SELECT
    customer_state,
    COUNT(*) AS review_count,
    SUM(CASE WHEN review_score IN (1, 2) THEN 1 ELSE 0 END) AS low_review_count,
    ROUND(
        100 * SUM(CASE WHEN review_score IN (1, 2) THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) AS low_review_ratio_pct
FROM vw_region_order_master
WHERE review_score IS NOT NULL
GROUP BY customer_state
ORDER BY low_review_ratio_pct DESC;


#E-1.지역별 배송일수와 리뷰 평균 동시 비교
SELECT
    customer_state,
    ROUND(AVG(delivery_days), 2) AS avg_delivery_days,
    ROUND(AVG(review_score), 2) AS avg_review_score,
    ROUND(100 * SUM(is_delayed) / COUNT(*), 2) AS delay_rate_pct
FROM vw_region_order_master
WHERE delivery_days IS NOT NULL
  AND review_score IS NOT NULL
GROUP BY customer_state
ORDER BY avg_delivery_days DESC;

#E-2. 배송 구간별 리뷰 점수
SELECT
    CASE
        WHEN delivery_days <= 5 THEN '0-5 days'
        WHEN delivery_days <= 10 THEN '6-10 days'
        WHEN delivery_days <= 15 THEN '11-15 days'
        ELSE '16+ days'
    END AS delivery_bucket,
    COUNT(*) AS order_count,
    ROUND(AVG(review_score), 2) AS avg_review_score
FROM vw_region_order_master
WHERE delivery_days IS NOT NULL
  AND review_score IS NOT NULL
GROUP BY delivery_bucket
ORDER BY delivery_bucket;

#F-1. 지역 내 거래 vs 타지역 거래 비중
SELECT
    customer_state,
    CASE
        WHEN customer_state = seller_state THEN 'same_state'
        ELSE 'cross_state'
    END AS trade_type,
    COUNT(*) AS item_count,
    ROUND(SUM(total_item_value), 2) AS total_sales
FROM vw_region_order_master
GROUP BY customer_state,
         CASE
             WHEN customer_state = seller_state THEN 'same_state'
             ELSE 'cross_state'
         END
ORDER BY customer_state, item_count DESC;