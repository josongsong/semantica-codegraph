"""
Scenario / Golden Tests

Rules:
- Golden JSON 파일 기반
- 검색 품질 회귀 방지
- 순서(order) strict match

Golden 파일 구조:
{
  "query": "search query",
  "expected_nodes": [
    {"symbol": "...", "file": "...", "line": 42}
  ]
}
"""
