import os
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# Mac: AppleGothic / Windows: Malgun Gothic / Linux: NanumGothic
plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False

# =========================
# 1. 파일 경로 설정
# =========================
DATA_DIR = "/Users/kimjaeho/Downloads/데이터 원본(csv)" 

ORDERS_PATH = os.path.join(DATA_DIR, "olist_orders_dataset.csv")
CUSTOMERS_PATH = os.path.join(DATA_DIR, "olist_customers_dataset.csv")
REVIEWS_PATH = os.path.join(DATA_DIR, "olist_order_reviews_dataset.csv")
ORDER_ITEMS_PATH = os.path.join(DATA_DIR, "olist_order_items_dataset.csv")
PRODUCTS_PATH = os.path.join(DATA_DIR, "olist_products_dataset.csv")
CATEGORY_TRANSLATION_PATH = os.path.join(DATA_DIR, "product_category_name_translation.csv")

# =========================
# 2. 데이터 로드
# =========================
orders = pd.read_csv(ORDERS_PATH)
customers = pd.read_csv(CUSTOMERS_PATH)
reviews = pd.read_csv(REVIEWS_PATH)
order_items = pd.read_csv(ORDER_ITEMS_PATH)

products = pd.read_csv(PRODUCTS_PATH) if os.path.exists(PRODUCTS_PATH) else None
cat_trans = pd.read_csv(CATEGORY_TRANSLATION_PATH) if os.path.exists(CATEGORY_TRANSLATION_PATH) else None

print("orders:", orders.shape)
print("customers:", customers.shape)
print("reviews:", reviews.shape)
print("order_items:", order_items.shape)
if products is not None:
    print("products:", products.shape)
if cat_trans is not None:
    print("category_translation:", cat_trans.shape)

# =========================
# 3. 전처리
# =========================
date_cols_orders = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date"
]

for col in date_cols_orders:
    if col in orders.columns:
        orders[col] = pd.to_datetime(orders[col], errors="coerce")

if "review_creation_date" in reviews.columns:
    reviews["review_creation_date"] = pd.to_datetime(reviews["review_creation_date"], errors="coerce")
if "review_answer_timestamp" in reviews.columns:
    reviews["review_answer_timestamp"] = pd.to_datetime(reviews["review_answer_timestamp"], errors="coerce")

# 배송일수 계산
orders["delivery_days"] = (
    orders["order_delivered_customer_date"] - orders["order_purchase_timestamp"]
).dt.days

# 지연 여부 계산
orders["delayed_flag"] = (
    orders["order_delivered_customer_date"] > orders["order_estimated_delivery_date"]
).astype("float")

# 정상 범위 필터
orders = orders[(orders["delivery_days"].isna()) | ((orders["delivery_days"] >= 0) & (orders["delivery_days"] <= 100))]

# =========================
# 4. 기본 병합
# =========================
base = (
    orders.merge(customers[["customer_id", "customer_state", "customer_city"]], on="customer_id", how="left")
          .merge(reviews[["order_id", "review_score"]], on="order_id", how="left")
)

# 주문별 총매출 계산
sales_per_order = (
    order_items.groupby("order_id", as_index=False)
    .agg(
        total_sales=("price", "sum"),
        total_freight=("freight_value", "sum"),
        item_count=("order_item_id", "count")
    )
)

base = base.merge(sales_per_order, on="order_id", how="left")

# 분석용 컬럼 보정
base["total_sales"] = base["total_sales"].fillna(0)
base["total_freight"] = base["total_freight"].fillna(0)
base["item_count"] = base["item_count"].fillna(0)

# =========================
# 5. 지역별 집계 데이터
# =========================
state_summary = (
    base.groupby("customer_state", as_index=False)
    .agg(
        order_count=("order_id", "nunique"),
        total_sales=("total_sales", "sum"),
        avg_order_value=("total_sales", "mean"),
        avg_delivery_days=("delivery_days", "mean"),
        delayed_rate=("delayed_flag", "mean"),
        avg_review_score=("review_score", "mean")
    )
    .sort_values("total_sales", ascending=False)
)

print("\n[지역별 요약]")
print(state_summary.head())

# =========================
# 6. 배송 구간 생성
# =========================
def delivery_bucket(x):
    if pd.isna(x):
        return np.nan
    if x <= 5:
        return "0-5일"
    elif x <= 10:
        return "6-10일"
    elif x <= 15:
        return "11-15일"
    else:
        return "16일 이상"

base["delivery_bucket"] = base["delivery_days"].apply(delivery_bucket)

# =========================
# 7. 카테고리 데이터 생성
# =========================
category_sales = None

if products is not None:
    item_prod = order_items.merge(products[["product_id", "product_category_name"]], on="product_id", how="left")

    if cat_trans is not None:
        # 번역 테이블 컬럼명 유연 대응
        cat_cols = cat_trans.columns.tolist()
        if "product_category_name" in cat_cols and "product_category_name_english" in cat_cols:
            item_prod = item_prod.merge(
                cat_trans[["product_category_name", "product_category_name_english"]],
                on="product_category_name",
                how="left"
            )
            item_prod["category_final"] = item_prod["product_category_name_english"].fillna(item_prod["product_category_name"])
        else:
            item_prod["category_final"] = item_prod["product_category_name"]
    else:
        item_prod["category_final"] = item_prod["product_category_name"]

    category_sales = (
        item_prod.groupby("category_final", as_index=False)
        .agg(total_sales=("price", "sum"))
        .sort_values("total_sales", ascending=False)
    )
    category_sales["cum_sales"] = category_sales["total_sales"].cumsum()
    category_sales["cum_pct"] = category_sales["cum_sales"] / category_sales["total_sales"].sum() * 100

# =========================
# 8. 저장 폴더
# =========================
OUT_DIR = "./python_viz_output"
os.makedirs(OUT_DIR, exist_ok=True)

# =========================
# 9. 시각화 1: 지역별 시장 포지셔닝 개선판
# =========================
fig, ax = plt.subplots(figsize=(12, 8))

sizes = state_summary["total_sales"] / state_summary["total_sales"].max() * 2000 + 50
sc = ax.scatter(
    state_summary["order_count"],
    state_summary["avg_order_value"],
    s=sizes,
    c=state_summary["avg_review_score"],
    alpha=0.7,
    edgecolors="black"
)

for _, row in state_summary.iterrows():
    ax.text(
        row["order_count"],
        row["avg_order_value"],
        row["customer_state"],
        fontsize=10,
        ha="center",
        va="bottom"
    )

ax.set_title("지역별 시장 포지셔닝: 주문수 vs 객단가 vs 리뷰점수", fontsize=16, fontweight="bold")
ax.set_xlabel("주문 수")
ax.set_ylabel("평균 주문 금액")
cbar = plt.colorbar(sc)
cbar.set_label("평균 리뷰 점수")

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "01_state_positioning.png"), dpi=200, bbox_inches="tight")
plt.show()

# =========================
# 10. 시각화 2: 배송일수 vs 리뷰점수 회귀 시각화
# =========================
reg_df = base[["delivery_days", "review_score"]].dropna().copy()
reg_df = reg_df[(reg_df["delivery_days"] >= 0) & (reg_df["delivery_days"] <= 60)]

# delivery_days별 평균 리뷰
reg_mean = reg_df.groupby("delivery_days", as_index=False)["review_score"].mean()

fig, ax = plt.subplots(figsize=(12, 7))
ax.scatter(
    reg_mean["delivery_days"],
    reg_mean["review_score"],
    alpha=0.7,
    edgecolors="black",
    s=70
)

# 1차 회귀선
if len(reg_mean) > 1:
    coef = np.polyfit(reg_mean["delivery_days"], reg_mean["review_score"], 1)
    poly = np.poly1d(coef)
    x_line = np.linspace(reg_mean["delivery_days"].min(), reg_mean["delivery_days"].max(), 200)
    y_line = poly(x_line)
    ax.plot(x_line, y_line, linewidth=2)

corr = reg_df["delivery_days"].corr(reg_df["review_score"])

ax.set_title(f"배송일수와 리뷰점수 관계 (상관계수: {corr:.3f})", fontsize=16, fontweight="bold")
ax.set_xlabel("배송일수")
ax.set_ylabel("평균 리뷰점수")
ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "02_delivery_vs_review_regression.png"), dpi=200, bbox_inches="tight")
plt.show()

# =========================
# 11. 시각화 3: 배송 구간별 리뷰점수 Boxplot
# =========================
box_df = base[["delivery_bucket", "review_score"]].dropna().copy()
bucket_order = ["0-5일", "6-10일", "11-15일", "16일 이상"]

data_for_box = [
    box_df.loc[box_df["delivery_bucket"] == bucket, "review_score"].values
    for bucket in bucket_order
]

fig, ax = plt.subplots(figsize=(10, 6))
ax.boxplot(data_for_box, labels=bucket_order, patch_artist=False)

bucket_means = (
    box_df.groupby("delivery_bucket", as_index=False)["review_score"]
    .mean()
)
bucket_means["delivery_bucket"] = pd.Categorical(bucket_means["delivery_bucket"], categories=bucket_order, ordered=True)
bucket_means = bucket_means.sort_values("delivery_bucket")

for i, val in enumerate(bucket_means["review_score"], start=1):
    ax.text(i, val + 0.05, f"{val:.2f}", ha="center", fontsize=10)

ax.set_title("배송 구간별 리뷰점수 분포", fontsize=16, fontweight="bold")
ax.set_xlabel("배송 구간")
ax.set_ylabel("리뷰 점수")
ax.grid(alpha=0.3, axis="y")

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "03_review_score_boxplot_by_delivery_bucket.png"), dpi=200, bbox_inches="tight")
plt.show()

# =========================
# 12. 시각화 4: 지역별 배송 품질 복합 시각화
# =========================
state_delivery = state_summary.sort_values("avg_delivery_days", ascending=False).copy()

fig, ax1 = plt.subplots(figsize=(14, 7))

x = np.arange(len(state_delivery))
bars = ax1.bar(x, state_delivery["avg_delivery_days"], alpha=0.8)
ax1.set_ylabel("평균 배송일수")
ax1.set_xlabel("지역")
ax1.set_xticks(x)
ax1.set_xticklabels(state_delivery["customer_state"], rotation=45)
ax1.set_title("지역별 배송 품질 비교: 평균 배송일수 vs 지연율", fontsize=16, fontweight="bold")

ax2 = ax1.twinx()
ax2.plot(x, state_delivery["delayed_rate"], marker="o", linewidth=2)
ax2.set_ylabel("지연율")

for i, v in enumerate(state_delivery["avg_delivery_days"]):
    if pd.notna(v):
        ax1.text(i, v + 0.3, f"{v:.1f}", ha="center", fontsize=9)

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "04_state_delivery_quality_combo.png"), dpi=200, bbox_inches="tight")
plt.show()

# =========================
# 13. 시각화 5: 카테고리 Pareto Chart
# =========================
if category_sales is not None and len(category_sales) > 0:
    top_n = 15
    pareto_df = category_sales.head(top_n).copy()

    fig, ax1 = plt.subplots(figsize=(14, 7))
    ax1.bar(pareto_df["category_final"], pareto_df["total_sales"], alpha=0.85)
    ax1.set_ylabel("총매출")
    ax1.set_xlabel("카테고리")
    ax1.set_title("상위 카테고리 Pareto Chart", fontsize=16, fontweight="bold")
    ax1.tick_params(axis="x", rotation=75)

    ax2 = ax1.twinx()
    ax2.plot(pareto_df["category_final"], pareto_df["cum_pct"], marker="o", linewidth=2)
    ax2.set_ylabel("누적 매출 비율(%)")
    ax2.axhline(80, linestyle="--", linewidth=1)

    for i, v in enumerate(pareto_df["cum_pct"]):
        ax2.text(i, v + 1, f"{v:.1f}%", ha="center", fontsize=8)

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "05_category_pareto_chart.png"), dpi=200, bbox_inches="tight")
    plt.show()

# =========================
# 14. 시각화 6: 지역별 총매출 Top 10 + 리뷰점수 동시 비교
# =========================
top10_state = state_summary.sort_values("total_sales", ascending=False).head(10).copy()

fig, ax1 = plt.subplots(figsize=(12, 7))
ax1.bar(top10_state["customer_state"], top10_state["total_sales"], alpha=0.85)
ax1.set_ylabel("총매출")
ax1.set_xlabel("지역")
ax1.set_title("상위 10개 지역: 총매출과 평균 리뷰점수", fontsize=16, fontweight="bold")

ax2 = ax1.twinx()
ax2.plot(top10_state["customer_state"], top10_state["avg_review_score"], marker="o", linewidth=2)
ax2.set_ylabel("평균 리뷰점수")

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "06_top10_state_sales_review_combo.png"), dpi=200, bbox_inches="tight")
plt.show()

print(f"\n시각화 파일 저장 완료: {OUT_DIR}")