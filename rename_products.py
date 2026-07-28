"""
CSV로 임포트된 상품(상품 P0001 (Groceries) 등)을 실제 편의점 상품명으로 바꿉니다.
- 상품 ID(위 목록의 왼쪽 번호)를 기준으로 매핑합니다.
- 이름을 다르게 하고 싶으면 아래 RENAME_MAP만 수정해서 다시 실행하면 됩니다.
- 실행: python rename_products.py
"""
import sqlite3

DB_PATH = "inventory.db"

# {상품 ID: 새 이름}
RENAME_MAP = {
    1: "삼각김밥(참치마요)",
    2: "볼펜",
    3: "도시락(제육볶음)",
    4: "샌드위치(햄치즈)",
    5: "보조배터리",
    6: "노트",
    7: "포스트잇",
    8: "컵라면(신라면)",
    9: "우유(200ml)",
    10: "바나나우유",
    11: "크림빵",
    12: "무선이어폰",
    13: "삼각김밥(전주비빔)",
    14: "USB케이블",
    15: "커터칼",
    16: "테이프",
    17: "스케치북",
    18: "문구세트",
    19: "형광펜",
    20: "물티슈",
}


def main():
    conn = sqlite3.connect(DB_PATH)
    updated = 0
    for pid, name in RENAME_MAP.items():
        cur = conn.execute("UPDATE products SET name=? WHERE id=?", (name, pid))
        updated += cur.rowcount
    conn.commit()
    conn.close()
    print(f"완료: 상품 {updated}개 이름 변경")


if __name__ == "__main__":
    main()
