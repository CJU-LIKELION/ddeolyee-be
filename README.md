# Ddeolyee Backend API

마감 할인 상품 거래 앱 **Ddeolyee(떨이)** 의 FastAPI 프로토타입 백엔드입니다.

현재 스택은 **FastAPI + PostgreSQL + SQLAlchemy + Alembic**입니다. 초기 검토 단계에서는 H2도 확인했지만, Python 백엔드와 프론트 연동 안정성을 고려해 PostgreSQL 구조로 전환했습니다.

## 구현 범위

- Auth: 회원가입, 로그인, 액세스 토큰 발급, 리프레시 토큰 재발급
- Users: 내 정보 조회/수정/탈퇴, 위치 갱신, 포인트 조회/이력
- Stores: 점주 매장 등록/조회/수정/삭제, 주변 매장 검색
- Products: 마감 할인 상품 등록/조회/수정/삭제, 상품 피드
- Orders: 주문 생성, 내 주문 조회, 주문 상세, 주문 취소, 픽업 완료
- Reviews: 주문 리뷰 작성, 내 리뷰 조회, 리뷰 수정/삭제
- Favorites: 즐겨찾기 추가/조회/삭제

## 로컬 실행 준비

```powershell
cd C:\like_lion\lion_be
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
Copy-Item .env.example .env
```

PostgreSQL을 Docker로 실행하는 경우:

```powershell
docker compose up -d postgres
```

DB 스키마 생성:

```powershell
alembic upgrade head
```

개발 서버 실행:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger 문서는 서버 실행 후 아래 주소에서 확인할 수 있습니다.

```text
http://127.0.0.1:8000/docs
```

## 환경 변수

`.env.example` 기본값:

```text
APP_NAME=Ddeolyee API
APP_ENV=local
DATABASE_URL=postgresql+psycopg://last_call:last_call@localhost:5432/last_call_market
ACCESS_TOKEN_TTL_MINUTES=120
```

현재 DB 이름과 계정은 로컬 프로토타입용 기본값입니다. 팀원 로컬 환경에서는 Docker Compose를 사용하거나, 같은 정보로 PostgreSQL DB를 직접 생성하면 됩니다.

## 테스트

PostgreSQL 테스트 DB가 준비되어 있을 때:

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://last_call:last_call@localhost:5432/last_call_market"
pytest
```

`TEST_DATABASE_URL`이 없으면 통합 테스트는 건너뜁니다.

## 구현 메모

- 주문 생성 시 상품 재고를 차감하고 포인트 사용/적립 이력을 기록합니다.
- 주문 취소 시 재고와 포인트를 복구합니다.
- 상품 할인율은 서버에서 자동 계산합니다.
- 마감 시간이 지난 상품은 조회/주문 시 `EXPIRED`로 자동 변경되며 구매할 수 없습니다.
- 거리 검색은 위도/경도 기반 haversine 계산을 애플리케이션 레이어에서 수행합니다.
- DB 모델은 [app/models.py](app/models.py)에 있고, Alembic 설정은 [alembic](alembic)에 있습니다.
