# Configuration Specification

본 문서는 환경 설정(Settings) 및 RepoConfig 적용 규칙을 정의한다.

---

## 목적

- 설정 값의 통일된 구조 유지
- 모든 환경(dev/stage/prod)에서 동일한 규칙 적용
- 설정 우선순위 명확화

---

## MUST 규칙

1. 설정은 **Pydantic Settings(BaseSettings)** 기반으로 정의한다.
2. 환경 변수 prefix는 반드시 **SEMANTICA_*** 로 통일한다.
3. 설정 우선순위는 다음과 같다:
   - (1) 환경 변수
   - (2) `.env` 파일
   - (3) 코드 내 기본값
4. Settings는 반드시 단일 파일 config.py에서 정의한다.
5. 각 setting 값은 변경 불가능(immutable)해야 한다.
6. 설정 객체는 DI 컨테이너가 단일 인스턴스로 생성한다.
7. Settings는 레이어 간 직접 import 없이 주입만 가능하다.

---

## 금지 규칙

1. Service/Infra 내부에서 os.getenv 직접 호출
2. Settings 로직을 여러 파일에 분산
3. 환경에 따라 스키마가 달라지는 설정
4. 테스트 코드에서 실제 환경 변수를 직접 수정하는 방식

---

## 문서 간 경계

- 저장소 구조 규칙은 REPO_STRUCTURE_SPEC.md
- 시간/랜덤 Provider 규칙은 TIME_RANDOM_SPEC.md 참고
