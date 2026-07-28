"""
편의점 재고관리 시스템 MVP - 백엔드 (FastAPI + SQLite)
--------------------------------------------------
- 프론트엔드(index.html)의 in-memory 로직을 그대로 서버 API로 옮김
- DB: SQLite (파일: inventory.db) — 나중에 MySQL로 바꾸려면 DB_URL만 교체
- 실행: uvicorn main:app --reload --port 8000
"""
from datetime import date, timedelta
from typing import Optional
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = "inventory.db"

CATEGORY_DEFAULTS = {
    "식품":     {"shelf_life": 7,    "safety_stock": 20},
    "생활용품": {"shelf_life": 365,  "safety_stock": 15},
    "전자기기": {"shelf_life": 1000, "safety_stock": 5},
    "문구":     {"shelf_life": 500,  "safety_stock": 10},
}
# D-6 .. D-0(오늘), 뒤 이틀(토/일 가정)에 가중치
WEEKDAY_WEIGHT = [1, 1, 1, 1, 1, 1.3, 1.3]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
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

    # 최초 실행 시에만 데모 데이터 삽입
    count = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    if count == 0:
        def d_ago(n):
            return (date.today() - timedelta(days=n)).isoformat()

        demo = [
            ("삼각김밥(참치)", "식품", 1500, "㈜신선푸드", 18, 20, 7, d_ago(5)),
            ("생수 500ml", "생활용품", 800, "맑은물산업", 60, 15, 365, d_ago(30)),
            ("무선 이어폰", "전자기기", 39000, "㈜테크나인", 3, 5, 1000, d_ago(100)),
            ("볼펜 세트", "문구", 2500, "한빛문구", 25, 10, 500, d_ago(50)),
        ]
        demo_sales = {
            "삼각김밥(참치)": [22, 25, 20, 24, 19, 30, 33],
            "생수 500ml": [10, 12, 9, 11, 10, 14, 15],
            "무선 이어폰": [1, 2, 1, 3, 2, 4, 6],
            "볼펜 세트": [3, 2, 4, 3, 2, 3, 5],
        }
        for name, cat, price, supplier, stock, safety, shelf, received in demo:
            cur = conn.execute(
                "INSERT INTO products (name, category, price, supplier, current_stock, "
                "safety_stock, shelf_life, last_received) VALUES (?,?,?,?,?,?,?,?)",
                (name, cat, price, supplier, stock, safety, shelf, received),
            )
            pid = cur.lastrowid
            total = 0
            # 최근 7일치 판매 로그를 역산해서 심어둔다 (D-6 ~ D-0)
            for i, qty in enumerate(demo_sales[name]):
                day = (date.today() - timedelta(days=6 - i)).isoformat()
                conn.execute(
                    "INSERT INTO sales_log (product_id, qty, date) VALUES (?,?,?)",
                    (pid, qty, day),
                )
                total += qty
            conn.execute("UPDATE products SET total_sold=? WHERE id=?", (total, pid))
        conn.commit()
    conn.close()


app = FastAPI(title="편의점 재고관리 시스템 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Pydantic 모델 ----------
class LoginIn(BaseModel):
    id: str
    pw: str


class ProductIn(BaseModel):
    name: str
    category: str
    price: int
    supplier: Optional[str] = None


class QtyIn(BaseModel):
    qty: int


class OrderIn(BaseModel):
    product_id: int
    qty: int
    vendor: Optional[str] = "거래처 A"


# ---------- 유통기한 / 추천 로직 헬퍼 ----------
def days_until_expiry(row) -> int:
    last_received = date.fromisoformat(row["last_received"])
    expiry = last_received + timedelta(days=row["shelf_life"])
    return (expiry - date.today()).days


def last7_daily_sales(conn, product_id: int):
    """최근 7일(D-6..D-0)의 일별 판매수량 리스트를 만든다 (없는 날은 0)."""
    days = [(date.today() - timedelta(days=6 - i)).isoformat() for i in range(7)]
    rows = conn.execute(
        "SELECT date, SUM(qty) AS q FROM sales_log WHERE product_id=? AND date IN (%s) "
        "GROUP BY date" % ",".join("?" * len(days)),
        (product_id, *days),
    ).fetchall()
    by_day = {r["date"]: r["q"] for r in rows}
    return [by_day.get(d, 0) for d in days]


def daily_avg_sales(last7):
    return (sum(last7) / 7) or 0.01


def weighted_avg(last7):
    s = sum(v * w for v, w in zip(last7, WEEKDAY_WEIGHT))
    wsum = sum(WEEKDAY_WEIGHT)
    return s / wsum


def compute_recommendation(conn, row):
    last7 = last7_daily_sales(conn, row["id"])
    w_avg = weighted_avg(last7)
    recent3 = last7[-3:]
    prior4 = last7[:4]
    recent3_avg = sum(recent3) / 3
    prior4_avg = (sum(prior4) / 4) or 0.01
    trend_ratio = recent3_avg / prior4_avg * 100
    is_trend = trend_ratio >= 150

    if is_trend:
        safety = round(row["safety_stock"] * 1.5)
        recommended = round(max(w_avg * 1.3, safety))
    else:
        safety = row["safety_stock"]
        recommended = round(max(w_avg, safety))

    days_left = days_until_expiry(row)
    d_avg = daily_avg_sales(last7)
    sellable_by_expiry = max(0, round(d_avg * max(days_left, 0)))
    waste_risk = max(0, row["current_stock"] - sellable_by_expiry)
    expiry_note = ""

    if waste_risk > 0:
        recommended = 0
        expiry_note = (
            f"유통기한(D-{days_left}) 내 소진이 어려운 재고 {waste_risk}개 보유 "
            f"→ 발주 보류, 소진(할인 등) 우선 권장"
        )
    else:
        max_by_shelf_life = round(d_avg * row["shelf_life"])
        if row["shelf_life"] <= 30 and recommended > max_by_shelf_life:
            recommended = max_by_shelf_life
            expiry_note = f"유통기한이 짧아({row['shelf_life']}일) 소진 가능한 양으로 발주량 자동 축소"

    return {
        "wAvg": round(w_avg, 1),
        "trendRatio": round(trend_ratio),
        "isTrend": is_trend,
        "recommended": recommended,
        "safety": safety,
        "daysLeft": days_left,
        "wasteRisk": waste_risk,
        "expiryNote": expiry_note,
    }


def product_to_dict(row, conn) -> dict:
    last7 = last7_daily_sales(conn, row["id"])
    days_left = days_until_expiry(row)
    d_avg = daily_avg_sales(last7)
    sellable = round(d_avg * max(days_left, 0))
    waste_risk = max(0, row["current_stock"] - sellable)
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "price": row["price"],
        "supplier": row["supplier"],
        "status": row["status"],
        "currentStock": row["current_stock"],
        "safetyStock": row["safety_stock"],
        "shelfLife": row["shelf_life"],
        "lastReceived": row["last_received"],
        "totalSold": row["total_sold"],
        "daysUntilExpiry": days_left,
        "wasteRisk": waste_risk,
        "last7": last7,
    }


@app.on_event("startup")
def on_startup():
    init_db()


# ---------- 로그인 (MVP 데모 - 고정 계정) ----------
@app.post("/api/login")
def login(payload: LoginIn):
    if payload.id == "admin" and payload.pw == "admin1234":
        return {"success": True}
    raise HTTPException(status_code=401, detail="ID/PW가 일치하지 않습니다.")


# ---------- 카테고리 기본값 ----------
@app.get("/api/category-defaults")
def category_defaults():
    return CATEGORY_DEFAULTS


# ---------- 1) 상품 관리 ----------
@app.get("/api/products")
def list_products():
    conn = get_db()
    rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    result = [product_to_dict(r, conn) for r in rows]
    conn.close()
    return result


@app.post("/api/products")
def add_product(p: ProductIn):
    if p.category not in CATEGORY_DEFAULTS:
        raise HTTPException(status_code=400, detail="알 수 없는 카테고리입니다.")
    d = CATEGORY_DEFAULTS[p.category]
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO products (name, category, price, supplier, current_stock, "
        "safety_stock, shelf_life, last_received) VALUES (?,?,?,?,0,?,?,?)",
        (p.name, p.category, p.price, p.supplier or "미지정",
         d["safety_stock"], d["shelf_life"], date.today().isoformat()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM products WHERE id=?", (cur.lastrowid,)).fetchone()
    result = product_to_dict(row, conn)
    conn.close()
    return result


class RenameIn(BaseModel):
    name: str


@app.patch("/api/products/{product_id}/rename")
def rename_product(product_id: int, body: RenameIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="상품명을 입력하세요.")
    conn = get_db()
    row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    conn.execute("UPDATE products SET name=? WHERE id=?", (name, product_id))
    conn.commit()
    conn.close()
    return {"id": product_id, "name": name}


@app.patch("/api/products/{product_id}/toggle")
def toggle_product(product_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    new_status = "판매중지" if row["status"] == "판매중" else "판매중"
    conn.execute("UPDATE products SET status=? WHERE id=?", (new_status, product_id))
    conn.commit()
    conn.close()
    return {"id": product_id, "status": new_status}


# ---------- 2) 재고 관리 ----------
@app.post("/api/products/{product_id}/sell")
def sell_product(product_id: int, body: QtyIn):
    if body.qty <= 0:
        raise HTTPException(status_code=400, detail="판매 수량을 확인하세요.")
    conn = get_db()
    row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    if body.qty > row["current_stock"]:
        conn.close()
        raise HTTPException(status_code=400, detail=f"재고가 부족합니다. (현재재고 {row['current_stock']}개)")
    conn.execute(
        "UPDATE products SET current_stock = current_stock - ?, total_sold = total_sold + ? WHERE id=?",
        (body.qty, body.qty, product_id),
    )
    conn.execute(
        "INSERT INTO sales_log (product_id, qty, date) VALUES (?,?,?)",
        (product_id, body.qty, date.today().isoformat()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    result = product_to_dict(row, conn)
    conn.close()
    return result


@app.post("/api/products/{product_id}/receive")
def receive_product(product_id: int, body: QtyIn):
    if body.qty <= 0:
        raise HTTPException(status_code=400, detail="입고 수량을 확인하세요.")
    conn = get_db()
    row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    conn.execute(
        "UPDATE products SET current_stock = current_stock + ?, last_received=? WHERE id=?",
        (body.qty, date.today().isoformat(), product_id),
    )
    # 해당 상품의 '확정' 상태 발주가 있으면 입고완료로 전환
    order = conn.execute(
        "SELECT * FROM orders WHERE product_id=? AND status='확정' ORDER BY id LIMIT 1",
        (product_id,),
    ).fetchone()
    if order:
        conn.execute("UPDATE orders SET status='입고완료' WHERE id=?", (order["id"],))
    conn.commit()
    row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    result = product_to_dict(row, conn)
    conn.close()
    return result


# ---------- 3) 판매 통계 ----------
@app.get("/api/stats")
def stats():
    conn = get_db()
    total_sales = conn.execute("SELECT COALESCE(SUM(qty),0) AS s FROM sales_log").fetchone()["s"]
    total_revenue = conn.execute(
        "SELECT COALESCE(SUM(sl.qty * p.price),0) AS s FROM sales_log sl JOIN products p ON p.id=sl.product_id"
    ).fetchone()["s"]
    product_count = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    order_count = conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]

    top = conn.execute(
        "SELECT id, name, total_sold FROM products ORDER BY total_sold DESC LIMIT 5"
    ).fetchall()
    top_products = [{"id": r["id"], "name": r["name"], "totalSold": r["total_sold"]} for r in top]

    log_rows = conn.execute(
        "SELECT sl.date, p.name, sl.qty FROM sales_log sl JOIN products p ON p.id=sl.product_id "
        "ORDER BY sl.id DESC LIMIT 8"
    ).fetchall()
    recent_log = [{"date": r["date"], "productName": r["name"], "qty": r["qty"]} for r in log_rows]

    conn.close()
    return {
        "totalSales": total_sales,
        "totalRevenue": total_revenue,
        "productCount": product_count,
        "orderCount": order_count,
        "topProducts": top_products,
        "recentLog": recent_log,
    }


@app.get("/api/stats/timeseries")
def sales_timeseries(days: int = 30, interval: str = "day"):
    conn = get_db()
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = conn.execute(
        "SELECT sl.date AS date, SUM(sl.qty) AS qty, SUM(sl.qty * p.price) AS revenue "
        "FROM sales_log sl JOIN products p ON p.id = sl.product_id "
        "WHERE sl.date >= ? GROUP BY sl.date ORDER BY sl.date",
        (start,),
    ).fetchall()
    conn.close()

    if interval == "day":
        return [{"label": r["date"], "qty": r["qty"], "revenue": r["revenue"]} for r in rows]

    # 주별/월별 집계 (기간이 길어질수록 일별 데이터는 점이 너무 많아 보기 어려움)
    buckets = {}
    order = []
    for r in rows:
        d = date.fromisoformat(r["date"])
        if interval == "week":
            key = (d - timedelta(days=d.weekday())).isoformat()  # 그 주의 월요일
        else:  # month
            key = f"{d.year:04d}-{d.month:02d}"
        if key not in buckets:
            buckets[key] = {"qty": 0, "revenue": 0}
            order.append(key)
        buckets[key]["qty"] += r["qty"]
        buckets[key]["revenue"] += r["revenue"]

    return [{"label": k, "qty": buckets[k]["qty"], "revenue": buckets[k]["revenue"]} for k in order]


# ---------- 4) 자동 발주 추천 ----------
@app.get("/api/orders/recommendations")
def order_recommendations():
    conn = get_db()
    rows = conn.execute("SELECT * FROM products WHERE status='판매중' ORDER BY id").fetchall()
    result = []
    for r in rows:
        rec = compute_recommendation(conn, r)
        result.append({
            "productId": r["id"],
            "name": r["name"],
            "currentStock": r["current_stock"],
            **rec,
        })
    conn.close()
    return result


@app.get("/api/orders")
def list_orders():
    conn = get_db()
    rows = conn.execute(
        "SELECT o.*, p.name AS product_name FROM orders o JOIN products p ON p.id=o.product_id "
        "ORDER BY o.id DESC"
    ).fetchall()
    result = [
        {
            "id": r["id"],
            "productId": r["product_id"],
            "productName": r["product_name"],
            "qty": r["qty"],
            "vendor": r["vendor"],
            "date": r["date"],
            "status": r["status"],
        }
        for r in rows
    ]
    conn.close()
    return result


@app.post("/api/orders")
def create_order(o: OrderIn):
    conn = get_db()
    row = conn.execute("SELECT * FROM products WHERE id=?", (o.product_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    cur = conn.execute(
        "INSERT INTO orders (product_id, qty, vendor, date, status) VALUES (?,?,?,?,'대기')",
        (o.product_id, o.qty, o.vendor, date.today().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"id": cur.lastrowid}


@app.patch("/api/orders/{order_id}/advance")
def advance_order(order_id: int):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        conn.close()
        raise HTTPException(status_code=404, detail="발주를 찾을 수 없습니다.")
    if order["status"] == "대기":
        conn.execute("UPDATE orders SET status='확정' WHERE id=?", (order_id,))
    elif order["status"] == "확정":
        conn.execute("UPDATE orders SET status='입고완료' WHERE id=?", (order_id,))
        conn.execute(
            "UPDATE products SET current_stock = current_stock + ? WHERE id=?",
            (order["qty"], order["product_id"]),
        )
    conn.commit()
    conn.close()
    return {"id": order_id}


@app.delete("/api/orders/{order_id}")
def delete_order(order_id: int):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        conn.close()
        raise HTTPException(status_code=404, detail="발주를 찾을 수 없습니다.")
    if order["status"] == "입고완료":
        conn.execute(
            "UPDATE products SET current_stock = MAX(0, current_stock - ?) WHERE id=?",
            (order["qty"], order["product_id"]),
        )
    conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    return {"deleted": order_id}
