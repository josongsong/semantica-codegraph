# Alembic Migrations

## DB URL
- 기본값: `SEMANTICA_DB_CONNECTION_STRING` (core.config.Settings)
- CLI override: `alembic -x db_url=postgresql://user:pass@host:5432/db upgrade head`

## 명령어
- 새 리비전(수동 작성): `alembic revision -m "init schema"`
- 오토젠 사용 시(SQLAlchemy 모델 연결 후): `alembic revision --autogenerate -m "add table X"`
- 적용: `alembic upgrade head`
- 롤백: `alembic downgrade -1`

## 구조
- `alembic.ini`: 공통 설정 (script_location=migrations)
- `migrations/env.py`: Settings 기반 URL 로딩, offline/online 모드 지원
- `migrations/versions/`: 리비전 스크립트 위치
