"""
CSV로 임포트된 상품의 공급업체(supplier)를 편의점에 맞는 가상 거래처명으로 바꿉니다.
- 상품 ID 기준 매핑입니다. 이름을 바꾸고 싶으면 SUPPLIER_MAP만 수정 후 재실행하세요.
- 실행: python update_suppliers.py
"""
import sqlite3

DB_PATH = "inventory.db"

# {상품 ID: 공급업체명}
SUPPLIER_MAP = {
    1: "㈜신선푸드",       # 삼각김밥(참치마요)
    13: "㈜신선푸드",      # 삼각김밥(전주비빔)
    3: "㈜맛있는한끼",     # 도시락(제육볶음)
    4: "서울샌드위치",     # 샌드위치(햄치즈)
    8: "라면나라",         # 컵라면(신라면)
    9: "서울우유유통",     # 우유(200ml)
    10: "서울우유유통",    # 바나나우유
    11: "삼립베이커리",    # 크림빵

    2: "한빛문구",         # 볼펜
    6: "한빛문구",         # 노트
    16: "한빛문구",        # 테이프
    18: "한빛문구",        # 문구세트
    7: "대한문구유통",     # 포스트잇
    15: "대한문구유통",    # 커터칼
    17: "대한문구유통",    # 스케치북
    19: "대한문구유통",    # 형광펜

    5: "㈜테크나인",       # 보조배터리
    12: "㈜테크나인",      # 무선이어폰
    14: "한국전자유통",    # USB케이블

    20: "청정생활",        # 물티슈
}


def main():
    conn = sqlite3.connect(DB_PATH)
    updated = 0
    for pid, supplier in SUPPLIER_MAP.items():
        cur = conn.execute("UPDATE products SET supplier=? WHERE id=?", (supplier, pid))
        updated += cur.rowcount
    conn.commit()
    conn.close()
    print(f"완료: 공급업체 {updated}개 변경")


if __name__ == "__main__":
    main()
