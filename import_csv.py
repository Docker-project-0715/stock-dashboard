"""
sales_data.csv (S002 매장) → inventory.db 임포트 스크립트
--------------------------------------------------------
- 대상 매장: S002
- 카테고리 매핑: Groceries→식품, Furniture→생활용품, Electronics→전자기기,
                Clothing/Toys→문구
- 날짜는 데이터셋의 마지막 날짜(2024-01-30)가 "오늘"이 되도록 통째로 이동시켜서
  최근 7일 판매량 기반 발주 추천이 실제로 동작하도록 만듭니다.
- 실행: python import_csv.py /path/to/sales_data.csv
"""
import csv
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta

DB_PATH = "inventory.db"
TARGET_STORE = "S002"

CATEGORY_MAP = {
    "Groceries": "식품",
    "Furniture": "생활용품",
    "Electronics": "전자기기",
    "Clothing": "문구",
    "Toys": "문구",
}
CATEGORY_DEFAULTS = {
    "식품":     {"shelf_life": 7,    "safety_stock": 20},
    "생활용품": {"shelf_life": 365,  "safety_stock": 15},
    "전자기기": {"shelf_life": 1000, "safety_stock": 5},
    "문구":     {"shelf_life": 500,  "safety_stock": 10},
}


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price INTEGER NOT NULL,
            supplier TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '판매중',
            current_stock INTEGER NOT NULL DEFAULT 0,
            safety_stock INTEGER NOT NULL,
            shelf_life INTEGER NOT NULL,
            last_received TEXT NOT NULL,
            total_sold INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sales_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            qty INTEGER NOT NULL,
            date TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            qty INTEGER NOT NULL,
            vendor TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '대기'
        );
        """
    )
    conn.commit()


def main(csv_path):
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)

    # 기존 데이터 초기화 (데모 데이터 제거 후 CSV 데이터로 교체)
    conn.executescript(
        "DELETE FROM sales_log; DELETE FROM orders; DELETE FROM products; "
        "DELETE FROM sqlite_sequence WHERE name IN ('products','orders','sales_log');"
    )
    conn.commit()

    rows_by_product = defaultdict(list)
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Store ID"] != TARGET_STORE:
                continue
            rows_by_product[row["Product ID"]].append(row)

    if not rows_by_product:
        print(f"경고: {TARGET_STORE} 매장 데이터가 없습니다.")
        return

    # 날짜 이동량 계산: 데이터셋 마지막 날짜 → 오늘
    all_dates = [row["Date"] for rows in rows_by_product.values() for row in rows]
    max_date = max(date.fromisoformat(d) for d in all_dates)
    shift_days = (date.today() - max_date).days

    def shift(d_str):
        return (date.fromisoformat(d_str) + timedelta(days=shift_days)).isoformat()

    product_pk = {}  # Product ID(csv) -> DB id
    for pid in sorted(rows_by_product.keys()):
        rows = sorted(rows_by_product[pid], key=lambda r: r["Date"])
        last_row = rows[-1]
        orig_cat = last_row["Category"]
        cat = CATEGORY_MAP.get(orig_cat, "식품")
        d = CATEGORY_DEFAULTS[cat]

        price = round(float(last_row["Price"]))
        current_stock = int(last_row["Inventory Level"])
        total_sold = sum(int(r["Units Sold"]) for r in rows)

        # 마지막으로 실제 발주(입고)가 있었던 날을 최근 입고일로 사용
        restock_rows = [r for r in rows if int(r["Units Ordered"]) > 0]
        last_received_raw = restock_rows[-1]["Date"] if restock_rows else last_row["Date"]
        last_received = shift(last_received_raw)

        name = f"상품 {pid} ({orig_cat})"

        cur = conn.execute(
            "INSERT INTO products (name, category, price, supplier, current_stock, "
            "safety_stock, shelf_life, last_received, total_sold) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, cat, price, "CSV 데이터셋", current_stock,
             d["safety_stock"], d["shelf_life"], last_received, total_sold),
        )
        product_pk[pid] = cur.lastrowid

    conn.commit()

    # 전 상품의 판매 로그를 날짜순으로 정렬해서 삽입 (최근 판매 로그 정렬이 실제 시간순이 되도록)
    all_rows = []
    for pid, rows in rows_by_product.items():
        for r in rows:
            all_rows.append((r["Date"], pid, int(r["Units Sold"])))
    all_rows.sort(key=lambda x: x[0])

    conn.executemany(
        "INSERT INTO sales_log (product_id, qty, date) VALUES (?,?,?)",
        [(product_pk[pid], qty, shift(d)) for d, pid, qty in all_rows if qty > 0],
    )
    conn.commit()
    conn.close()

    print(f"완료: {TARGET_STORE} 매장 상품 {len(product_pk)}개, "
          f"판매 로그 {sum(1 for _,_,q in all_rows if q>0)}건 임포트 (날짜 {shift_days}일 이동)")


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "sales_data.csv"
    main(csv_path)
