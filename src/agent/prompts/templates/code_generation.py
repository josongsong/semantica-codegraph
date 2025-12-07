"""Code Generation Prompt Templates

LLM 기반 코드 생성을 위한 프롬프트
"""

FIX_BUG_TEMPLATE = """당신은 전문 소프트웨어 엔지니어입니다. 버그를 수정해야 합니다.

버그 설명:
{bug_description}

파일: {file_path}

현재 코드:
```python
{existing_code}
```

관련 코드 (참고용):
{related_code}

테스트 케이스:
{test_cases}

지침:
1. 버그의 근본 원인을 분석하세요
2. 다음을 만족하는 수정을 생성하세요:
   - 버그를 완전히 해결
   - 기존 기능 유지
   - 프로젝트 코딩 스타일 준수
   - 최소한의 변경
3. 수정 사항을 설명하세요

출력 형식:
```python
<수정된_전체_코드>
```

설명: <수정 사항에 대한 설명>
"""

ADD_FEATURE_TEMPLATE = """당신은 전문 소프트웨어 엔지니어입니다. 새로운 기능을 구현해야 합니다.

기능 설명:
{feature_description}

대상 파일: {target_file}

프로젝트 구조:
{project_structure}

관련 코드 (참고용):
{related_code}

코딩 스타일 가이드:
{coding_style}

지침:
1. 기능 구현을 설계하세요
2. 다음을 만족하는 코드를 생성하세요:
   - 기능을 완전히 구현
   - 기존 코드와 잘 통합
   - 프로젝트 규칙 준수
   - 문서화 잘 됨
   - 에러 처리 포함
3. 필요한 새 파일 목록
4. 구현 설명

출력 형식:
파일: <파일_경로>
```python
<코드>
```

설명: <구현에 대한 설명>

추가 파일 (필요시):
파일: <다른_파일_경로>
```python
<코드>
```
"""

REFACTOR_TEMPLATE = """당신은 전문 소프트웨어 엔지니어입니다. 코드를 리팩토링해야 합니다.

리팩토링 목표:
{refactor_goal}

파일: {file_path}

현재 코드:
```python
{existing_code}
```

의존성:
{dependencies}

기존 테스트:
{tests}

지침:
1. 목표에 맞게 코드를 리팩토링하세요
2. 다음을 보장하세요:
   - 기능 유지
   - 코드가 더 깔끔하고 유지보수 가능
   - 테스트가 여전히 통과
   - Public API에 Breaking 변경 없음
3. 리팩토링 설명

출력 형식:
```python
<리팩토링된_코드>
```

설명: <변경 사항 설명>
Breaking 변경: <없음 또는 목록>
"""

# 간단한 템플릿 (Mock LLM용)
SIMPLE_FIX_TEMPLATE = """버그 수정: {bug_description}

파일: {file_path}
코드:
```python
{existing_code}
```

수정된 코드를 생성하세요.
"""

SIMPLE_FEATURE_TEMPLATE = """기능 추가: {feature_description}

파일: {target_file}

코드를 생성하세요.
"""

SIMPLE_REFACTOR_TEMPLATE = """리팩토링: {refactor_goal}

파일: {file_path}
코드:
```python
{existing_code}
```

리팩토링된 코드를 생성하세요.
"""
