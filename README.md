# 🏪 편의점 재고관리 시스템 (Convenience Store Inventory Management System)

유통기한 관리 + 판매패턴 기반 자동 발주 추천 MVP

판매·재고 데이터를 바탕으로 가중이동평균과 트렌드 판별 로직을 적용해 발주량을 자동으로 추천하고, 유통기한 임박/폐기 위험 재고를 사전에 감지하는 편의점 재고관리 시스템입니다.

---

## 📌 주요 기능

- **상품 관리** — 상품 등록, 이름 수정, 판매중지/재개, 카테고리별 유통기한·안전재고 기본값 자동 적용
- **재고 관리** — 판매/입고 처리 시 재고 자동 증감, 유통기한 자동 계산(D-day), **위험 · 주의 · 여유 순 정렬**
- **판매 통계** — 1개월/6개월/1년 기간별 매출·판매량 추이 그래프, 인기상품 TOP 5
- **발주 추천** — 가중이동평균 + 트렌드 판별 + 유통기한 반영 발주량 자동 계산, **위험/주의/여유 필터**로 모아보기
- **발주 워크플로우** — 발주 생성 → 확정 → 입고완료 상태 관리, 입고 시 재고 자동 반영

## 🧮 발주 추천 알고리즘

1. 최근 7일 판매 이력 수집 (요일 가중치: 주말 ×1.3)
2. 가중이동평균 계산
3. 트렌드 판별: 최근 3일 평균 ÷ 이전 4일 평균 ≥ 150%
4. 트렌드 상품은 안전재고·가중치 상향 적용
5. **유통기한 반영**: 잔여기간 내 소진 불가한 재고가 있으면 발주 보류, 유통기한이 짧은 상품은 소진 가능량 이내로 발주량 자동 축소

## 🛠 기술 스택

이 저장소에는 실행 환경에 따라 고를 수 있는 **두 가지 백엔드**가 있습니다.

| 구분 | 폴더 | 설명 |
|---|---|---|
| 기본 버전 | `backend/` | FastAPI + SQLite. 개발/확장에 적합 (`pip install` 필요) |
| 설치 없는 버전 | `standalone/` | Python 표준 라이브러리만 사용. `pip install` · 인터넷 연결 불필요 (발표·시연용) |

공통: 프론트엔드는 순수 HTML/JavaScript + Chart.js, DB는 SQLite.

향후 확장 계획으로는 MySQL 전환, Java/Spring Boot 백엔드, React 프론트엔드, Docker/Kubernetes 기반 다지점 배포, 점주/직원 권한 분리(OWNER/STAFF) 등을 설계 중입니다.

## 📂 폴더 구조

```
├── backend/                  # FastAPI 버전
│   ├── main.py                  # API 서버
│   ├── requirements.txt
│   ├── import_csv.py             # Kaggle 데이터셋 임포트 스크립트
│   ├── rename_products.py        # 상품명 일괄 변경 스크립트
│   ├── update_suppliers.py       # 공급업체 일괄 변경 스크립트
│   └── inventory.db              # SQLite DB (샘플 데이터 포함)
│
├── standalone/                # 설치 없는 버전 (발표·시연용)
│   ├── app.py                    # 프론트+백엔드 통합 서버 (표준 라이브러리만 사용)
│   ├── run.bat                   # Windows 더블클릭 실행
│   ├── index.html
│   ├── chart.umd.min.js
│   └── inventory.db
│
└── frontend/                  # 프론트엔드 (index.html, chart.umd.min.js)
```

## 🚀 실행 방법

### 방법 A — 기본 버전 (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

이후 `frontend/index.html`을 브라우저로 열면 됩니다.

### 방법 B — 설치 없는 버전 (권장: 발표·시연용)

```bash
cd standalone
python app.py
```

브라우저가 자동으로 열립니다 (안 열리면 `http://localhost:8000` 접속). Windows에서는 `run.bat`을 더블클릭해도 됩니다.

### 로그인

```
아이디: admin
비밀번호: admin1234
```

## 📊 데이터

실제 POS 판매 데이터는 접근이 불가능하여, 아래 두 데이터를 결합해 현실성을 확보했습니다.

- **[Kaggle: Retail Store Inventory and Demand Forecasting](https://www.kaggle.com/)** — 5개 매장 중 S002 매장, 20개 상품, 2022-01~2024-01(2년치) 일별 판매 이력을 편의점 컨셉으로 매핑
- **카테고리 매핑**: `Groceries`→식품, `Furniture`→생활용품, `Electronics`→전자기기, `Clothing`/`Toys`→문구
- 데이터셋의 마지막 날짜를 실행 시점의 "오늘"로 자동 이동시켜, 최근 7일 기반 발주 추천 로직이 항상 정상 동작하도록 처리했습니다.

다른 매장 데이터로 다시 임포트하려면:

```bash
cd backend
python import_csv.py sales_data.csv
```

## 🔌 API 개요 (backend/main.py)

| Method | Endpoint | 설명 |
|---|---|---|
| POST | `/api/login` | 로그인 |
| GET/POST | `/api/products` | 상품 목록 조회 / 등록 |
| PATCH | `/api/products/{id}/rename` | 상품명 수정 |
| PATCH | `/api/products/{id}/toggle` | 판매중지/재개 |
| POST | `/api/products/{id}/sell` | 판매 처리 |
| POST | `/api/products/{id}/receive` | 입고 처리 |
| GET | `/api/stats` | 누적 판매 통계, 인기상품 TOP5 |
| GET | `/api/stats/timeseries` | 기간별(일/주/월) 매출·판매량 추이 |
| GET | `/api/orders/recommendations` | 발주 추천 목록 |
| GET/POST | `/api/orders` | 발주 목록 조회 / 생성 |
| PATCH | `/api/orders/{id}/advance` | 발주 상태 전환 (대기→확정→입고완료) |
| DELETE | `/api/orders/{id}` | 발주 삭제 |

## 👥 팀 구성

| 역할 | 담당 |
|---|---|
| 백엔드 (Java) | 상품·판매·구매 로직, 재고 자동 차감, 발주 추천 계산 |
| 프론트엔드 + DB | 화면, DB 스키마 설계, 통계 쿼리 |
| 인프라 | Docker/K8s 구성, 서버 관리 |
| 데이터 · 문서 | 데이터 수집, 발표자료, 문서화 |

## 🗺 향후 계획

- [ ] MySQL 전환
- [ ] 네이버 쇼핑 오픈 API 연동 (실 상품 가격 정보 반영)
- [ ] 점주(OWNER)/직원(STAFF) 권한 분리
- [ ] 입고 배치(Batch) 단위 유통기한 관리 (FIFO)
- [ ] Docker/Kubernetes 기반 다지점 배포
