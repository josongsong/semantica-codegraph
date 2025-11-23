"""
Fake Relational Store for Unit Testing
"""

from typing import Any


class FakeRelationalStore:
    """
    RelationalStorePort Fake 구현.

    in-memory dict 기반 간단한 테이블 저장소.
    """

    def __init__(self):
        self.tables: dict[str, list[dict[str, Any]]] = {}

    def execute(self, query: str, params: dict | None = None) -> list[dict]:
        """쿼리 실행 (mock)."""
        # 실제 SQL 파싱 없이 테스트용 minimal 구현
        return []

    def insert(self, table: str, data: dict[str, Any]) -> str:
        """레코드 삽입."""
        if table not in self.tables:
            self.tables[table] = []

        record = {"id": len(self.tables[table]) + 1, **data}
        self.tables[table].append(record)
        return str(record["id"])

    def select(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """레코드 조회."""
        if table not in self.tables:
            return []

        records = self.tables[table]

        if filters:
            records = [r for r in records if all(r.get(k) == v for k, v in filters.items())]

        return records

    def update(self, table: str, record_id: str, data: dict[str, Any]):
        """레코드 업데이트."""
        if table not in self.tables:
            return

        for record in self.tables[table]:
            if str(record["id"]) == record_id:
                record.update(data)
                break

    def delete(self, table: str, record_id: str):
        """레코드 삭제."""
        if table not in self.tables:
            return

        self.tables[table] = [r for r in self.tables[table] if str(r["id"]) != record_id]

    def clear(self):
        """모든 테이블 삭제."""
        self.tables.clear()
