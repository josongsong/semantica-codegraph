"""
LATS Prompt Templates (v9)

역할별로 최적화된 프롬프트
"""


class LATSPrompts:
    """LATS 프롬프트 모음"""

    # ========================================================================
    # Generator Prompts (창의성 중시)
    # ========================================================================

    GENERATE_NEXT_THOUGHTS = """
당신은 **창의적 문제 해결자**입니다.

현재 상황:
{current_state}

해결할 문제:
{problem}

다음으로 시도할 수 있는 {k}가지 접근 방법을 제안하세요.

**중요**:
- 각 접근은 서로 달라야 합니다 (다양성 중요!)
- 구체적이고 실행 가능해야 합니다
- 창의적으로 생각하되, 실현 가능성도 고려하세요

형식:
1. [접근 방법 1]
2. [접근 방법 2]
3. [접근 방법 3]
"""

    GENERATE_COMPLETE_STRATEGY = """
당신은 **전문 소프트웨어 엔지니어**입니다.

문제:
{problem}

사고 과정:
{thought_path}

위 사고 과정에 따라 **완전한 코드 변경**을 생성하세요.

**중요**:
- 실행 가능한 코드를 작성하세요
- 기존 코드 스타일을 유지하세요
- 주석을 추가하여 의도를 명확히 하세요

출력 형식:
파일경로:
```python
코드 내용
```
"""

    # ========================================================================
    # Verifier Prompts (비판적 평가)
    # ========================================================================

    EVALUATE_THOUGHT = """
당신은 **비판적 검토자**입니다.

다음 접근 방법을 **엄격하게** 평가하세요:

접근: {partial_thought}

평가 기준:
1. 구체성: 추상적인가 구체적인가?
2. 실현 가능성: 코드로 구현 가능한가?
3. 논리성: 순서가 논리적인가?
4. 완전성: 누락된 단계가 없는가?

**중요**:
- 실행 가능한 코드가 아니어도 괜찮습니다 (계획 단계)
- 0.0 ~ 1.0 사이 점수로 평가하세요
- 객관적이고 비판적으로 판단하세요

점수만 출력: [0.0 ~ 1.0]
"""

    EVALUATE_THOUGHT_STRICT = """
당신은 **매우 까칠한 코드 리뷰어**입니다. (Devil's Advocate)

다음 접근을 **비판적으로** 평가하세요:

접근: {partial_thought}

**중요**:
- 무조건 꼬투리를 잡으세요
- "될 것 같다"는 믿지 마세요
- 환각(Hallucination) 가능성을 의심하세요
- 존재하지 않는 함수/라이브러리를 쓰지 않았는지 확인하세요

**평가 기준**:
1. 실제로 구현 가능한가? (환각 아닌가?)
2. 문법적으로 맞는가?
3. 논리적 오류는 없는가?

점수: 0.0 (매우 의심스러움) ~ 1.0 (확실함)

**점수만 출력하되, 의심스러우면 0.3 이하로 주세요.**
"""

    VERIFY_STRATEGY = """
당신은 **코드 리뷰어**입니다.

다음 코드 변경을 **엄격하게** 검토하세요:

코드:
{code_changes}

요구사항:
{requirements}

검토 항목:
1. 요구사항 충족 여부
2. 문법 오류 (Syntax)
3. 논리 오류 (Logic)
4. 보안 문제
5. 성능 이슈

**판정**: ACCEPT / REVISE / REJECT

이유:
[구체적 이유]

점수: [0.0 ~ 1.0]
"""

    # ========================================================================
    # Utility Methods
    # ========================================================================

    @staticmethod
    def format_generate_next_thoughts(
        current_state: str,
        problem: str,
        k: int = 3,
    ) -> str:
        """Generator 프롬프트 포맷팅"""
        return LATSPrompts.GENERATE_NEXT_THOUGHTS.format(
            current_state=current_state,
            problem=problem,
            k=k,
        )

    @staticmethod
    def format_evaluate_thought(
        partial_thought: str,
        use_strict: bool = False,
    ) -> str:
        """Verifier 프롬프트 포맷팅"""
        template = LATSPrompts.EVALUATE_THOUGHT_STRICT if use_strict else LATSPrompts.EVALUATE_THOUGHT

        return template.format(partial_thought=partial_thought)

    @staticmethod
    def format_generate_complete_strategy(
        problem: str,
        thought_path: list[str],
    ) -> str:
        """Strategy Generator 프롬프트 포맷팅"""
        thought_summary = "\n".join(f"{i + 1}. {thought}" for i, thought in enumerate(thought_path))

        return LATSPrompts.GENERATE_COMPLETE_STRATEGY.format(
            problem=problem,
            thought_path=thought_summary,
        )

    @staticmethod
    def format_verify_strategy(
        code_changes: dict[str, str],
        requirements: str,
    ) -> str:
        """Strategy Verifier 프롬프트 포맷팅"""
        code_summary = "\n\n".join(f"File: {path}\n```python\n{content}\n```" for path, content in code_changes.items())

        return LATSPrompts.VERIFY_STRATEGY.format(
            code_changes=code_summary,
            requirements=requirements,
        )
