# Java 언어 지원

## 개요

CodeGraph는 Java 언어에 대한 전체 IR 생성 및 그래프 분석을 지원합니다.

## 지원 기능

### 1. 구조 파싱

- **File**: Java 소스 파일
- **Class**: 클래스 선언 (중첩 클래스 포함)
- **Interface**: 인터페이스 선언
- **Enum**: 열거형 (CLASS로 표현, `is_enum` 속성)
- **Method**: 메서드 및 생성자
- **Field**: 필드 변수

### 2. Package 및 Import

- Package 선언 추출
- Import 문 파싱 (wildcard 지원)
- FQN(Fully Qualified Name) 생성

### 3. 관계 분석

- **CONTAINS**: 파일→클래스, 클래스→메서드/필드
- **CALLS**: 메서드 호출
- **INHERITS**: 클래스 상속 (extends)
- **IMPLEMENTS**: 인터페이스 구현

### 4. 제어 흐름

- Cyclomatic Complexity 계산
- Loop 감지 (for, while, do-while, enhanced-for)
- Try-catch 감지
- Branch 카운트 (if, switch)

## 사용 예시

```python
from src.contexts.code_foundation.infrastructure.generators.java_generator import JavaIRGenerator
from src.contexts.code_foundation.infrastructure.parsing import SourceFile

code = """
package com.example;

import java.util.List;

public class HelloWorld {
    private String message;
    
    public HelloWorld(String msg) {
        this.message = msg;
    }
    
    public void printMessage() {
        System.out.println(message);
    }
}
"""

source = SourceFile.from_content(
    file_path="src/main/java/com/example/HelloWorld.java",
    content=code,
    language="java",
)

generator = JavaIRGenerator(repo_id="my_project")
ir_doc = generator.generate(source, snapshot_id="v1")

# 생성된 노드: File, Class, Method(2), Field, Import
# 생성된 엣지: CONTAINS, IMPORTS, CALLS
```

## 지원 Tree-sitter 노드 타입

### 선언
- `class_declaration`
- `interface_declaration`
- `enum_declaration`
- `method_declaration`
- `field_declaration`

### 구문
- `package_declaration`
- `import_declaration`
- `superclass` (extends)
- `super_interfaces` (implements)
- `extends_interfaces` (interface extends)

### 제어 흐름
- `if_statement`
- `switch_statement`, `switch_expression`
- `for_statement`, `enhanced_for_statement`
- `while_statement`, `do_statement`
- `try_statement`, `try_with_resources_statement`

### 호출
- `method_invocation`

## 제한사항

### 현재 지원하지 않음
- Annotation 상세 분석
- Generic 타입 파라미터
- Lambda 표현식
- Type 추론
- Cross-file 타입 해석

### 향후 추가 예정
- Java type checker 통합 (javac API)
- Annotation processor 지원
- Generic 타입 분석
- Lambda 및 method reference

## 통합

Java generator는 다음에 자동 통합됩니다:

1. **SOTAIRBuilder**: `.java` 파일 감지 시 자동 사용
2. **ParserRegistry**: `java` 언어로 등록됨
3. **분석 파이프라인**: Python, TypeScript와 동일한 워크플로우

## 성능

일반적인 Java 클래스 파일 (500-1000 LOC):
- 파싱: ~2-5ms
- IR 생성: ~1-3ms
- 총 시간: ~5-10ms

## 테스트

```bash
# Java generator 검증
python verify_java_support.py

# 단위 테스트 (conftest 충돌 회피)
python tests/test_java_generator.py
```

## 관련 파일

- Generator: `src/contexts/code_foundation/infrastructure/generators/java_generator.py`
- 테스트: `tests/test_java_generator.py`
- 검증: `verify_java_support.py`
