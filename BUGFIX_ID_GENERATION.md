# Critical Bug Fix: ID Generation

## 문제

regex 치환 실수로 모든 `generate_logical_id()` 호출이 잘못된 인자 전달:

```python
# 잘못된 코드 (Before)
id=generate_logical_id(
    repo_id=NodeKind.METHOD,  # ❌ Enum 값
    kind=NodeKind.METHOD,
    file_path=NodeKind.METHOD,  # ❌ Enum 값  
    fqn=NodeKind.METHOD  # ❌ Enum 값
)
```

## 영향받은 메서드

1. `_process_import()` - Import 노드
2. `_process_class()` - Class 노드  
3. `_process_interface()` - Interface 노드
4. `_process_enum()` - Enum 노드
5. `_process_method()` - Method 노드
6. `_process_field()` - Field 노드

**총 6개 메서드, 모든 노드 타입 영향**

## 수정 내용

```python
# 올바른 코드 (After)
id=generate_logical_id(
    repo_id=self.repo_id,  # ✓ 실제 repo ID
    kind=NodeKind.METHOD,
    file_path=self._source.file_path,  # ✓ 실제 파일 경로
    fqn=method_fqn,  # ✓ 실제 FQN
)
```

## 검증

```bash
python -c "..." # ID validation script
```

**결과**:
```
✓ IR 생성 성공!
Nodes: 5
  File       | ID: file:my_project:Calculator.java
  Import     | ID: import:my_project:Calculator.java:util.List
  Class      | ID: class:my_project:Calculator.java:Calculator.Calculator
  Field      | ID: field:my_project:Calculator.java:Calculator.value
  Method     | ID: method:my_project:Calculator.java:Calculator.add

✓ 모든 ID가 올바르게 생성됨!
```

## 교훈

1. **Regex 치환 후 반드시 검증 필요**
2. **통합 테스트 강화 필요** - ID 형식 검증 추가
3. **Type checking** - mypy로 잡을 수 있었을 문제

## 후속 조치

- [x] 모든 generate_logical_id 호출 수정
- [x] 검증 스크립트 실행
- [ ] 통합 테스트에 ID 검증 추가
- [ ] mypy strict mode 활성화
