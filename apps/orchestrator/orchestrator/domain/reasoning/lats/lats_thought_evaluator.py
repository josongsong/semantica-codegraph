"""
LATS Thought Evaluator (v9)

중간 단계 Thought 평가 (Heuristic + LLM 혼합)
"""

import ast
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.orchestrator.orchestrator.adapters.llm.base import BaseLLMAdapter

logger = logging.getLogger(__name__)


class LATSThoughtEvaluator:
    """
    LATS Thought Evaluator (Domain Service)

    책임:
    1. 중간 단계 Thought의 품질 평가
    2. Static Analysis + LLM 혼합 평가

    전략:
    - Heuristic Rule (40%)
    - LLM Self-Reflection (60%)

    SOTA:
    - AST-based Validation
    - Multi-criteria Scoring
    """

    def __init__(self, llm: "BaseLLMAdapter"):
        """
        Args:
            llm: LLM Adapter
        """
        self.llm = llm

        logger.info("LATSThoughtEvaluator initialized")

    async def evaluate(
        self,
        partial_thought: str,
        context: dict | None = None,
        verifier_model: str | None = None,
        temperature: float = 0.2,
    ) -> float:
        """
        중간 Thought 평가 (P2-3: Cross-Model Verification)

        Args:
            partial_thought: 평가할 Thought
            context: 컨텍스트 (Optional)
            verifier_model: Verifier 전용 모델 (예: claude-3.5-sonnet)
            temperature: LLM Temperature (Verifier는 낮게)

        Returns:
            0.0 ~ 1.0 (높을수록 유망)
        """
        context = context or {}

        # 1. Heuristic Score (40%)
        heuristic_score = self._heuristic_evaluation(partial_thought)

        # 2. LLM Score (60%) - Verifier Model 사용!
        llm_score = await self._llm_evaluation(
            partial_thought,
            context,
            verifier_model=verifier_model,
            temperature=temperature,
        )

        # Weighted Average
        final_score = 0.4 * heuristic_score + 0.6 * llm_score

        logger.debug(
            f"Thought eval: heuristic={heuristic_score:.2f}, "
            f"llm={llm_score:.2f}, final={final_score:.2f}, "
            f"verifier={verifier_model or 'default'}"
        )

        return final_score

    def _heuristic_evaluation(self, thought: str) -> float:
        """
        Heuristic Rule 기반 평가

        체크 항목:
        1. 길이 (너무 짧거나 길면 감점)
        2. 키워드 (구체적 행동: "파일", "함수", "클래스" 등)
        3. 문법 오류 (AST Parsing 시도)
        4. 논리 흐름 (순서대로 진행되는가)

        Returns:
            0.0 ~ 1.0
        """
        score = 0.5  # 기본 점수

        # 1. 길이 체크
        word_count = len(thought.split())
        if 5 <= word_count <= 50:
            score += 0.1
        elif word_count < 3:
            score -= 0.2

        # 2. 구체성 체크 (키워드)
        concrete_keywords = [
            "파일",
            "함수",
            "클래스",
            "메서드",
            "변수",
            "읽기",
            "쓰기",
            "추가",
            "수정",
            "삭제",
            "file",
            "function",
            "class",
            "method",
            "variable",
            "read",
            "write",
            "add",
            "modify",
            "delete",
            "import",
            "def",
            "return",
        ]

        keyword_count = sum(1 for kw in concrete_keywords if kw in thought.lower())
        score += min(0.2, keyword_count * 0.05)

        # 3. AST Parsing 시도 (코드 조각이 포함되어 있다면)
        if "```" in thought or "def " in thought or "class " in thought:
            code_snippets = self._extract_code_snippets(thought)

            for snippet in code_snippets:
                if self._is_valid_python_syntax(snippet):
                    score += 0.1
                else:
                    score -= 0.1  # 문법 오류는 감점

        # 4. 순서 표현 (단계적 접근)
        if any(marker in thought for marker in ["1.", "2.", "먼저", "다음", "first", "then", "step"]):
            score += 0.1

        return max(0.0, min(1.0, score))

    def _extract_code_snippets(self, thought: str) -> list[str]:
        """
        코드 블록 추출

        Args:
            thought: Thought 텍스트

        Returns:
            코드 조각 리스트
        """
        snippets = []

        # Markdown code block
        if "```" in thought:
            parts = thought.split("```")
            for i in range(1, len(parts), 2):
                code = parts[i]
                # 언어 태그 제거 (```python → python)
                if "\n" in code:
                    code = "\n".join(code.split("\n")[1:])
                snippets.append(code.strip())

        return snippets

    def _is_valid_python_syntax(self, code: str) -> bool:
        """
        Python 문법 체크 (AST Parsing)

        Args:
            code: Python 코드

        Returns:
            문법 유효 여부
        """
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False
        except Exception:
            return False

    async def _llm_evaluation(
        self,
        thought: str,
        context: dict,
        verifier_model: str | None = None,
        temperature: float = 0.2,
    ) -> float:
        """
        LLM 기반 평가 (P2-3: Verifier Model 사용)

        프롬프트 엔지니어링:
        - "실행 가능성"이 아닌 "논리적 완결성" 평가
        - "0.0 ~ 1.0" 직접 출력하게 유도
        - Verifier 역할: 비판적 평가 (Echo chamber 방지)

        Args:
            thought: Thought
            context: 컨텍스트
            verifier_model: Verifier 전용 모델 (Generator와 다른 모델)
            temperature: Temperature (Verifier는 낮게, 0.2)

        Returns:
            평가 점수 (0.0 ~ 1.0)
        """
        # Verifier Prompt (비판적 관점)
        prompt = f"""
You are a **critical code reviewer** evaluating a partial solution plan.

Plan: {thought}

Rate this plan's **logical completeness** from 0.0 to 1.0.

Criteria:
1. Specificity (Is it concrete or abstract?)
2. Feasibility (Can it be implemented?)
3. Logic Flow (Does it follow a logical sequence?)
4. Completeness (Are there any missing steps?)

**IMPORTANT**: Be CRITICAL. Only give high scores (>0.7) if truly excellent.

Output ONLY a number between 0.0 and 1.0.
Example: 0.7
"""

        # Verifier Model 사용!
        llm_kwargs = {
            "temperature": temperature,  # Verifier는 낮은 temperature
            "max_tokens": 10,
        }

        if verifier_model:
            llm_kwargs["model"] = verifier_model

        try:
            response = await self.llm.generate(prompt=prompt, **llm_kwargs)

            score = float(response.strip())
            score = max(0.0, min(1.0, score))

            return score

        except ValueError:
            logger.warning(f"LLM returned non-numeric: {response}, using default 0.5")
            return 0.5  # Fallback

        except Exception as e:
            logger.warning(f"LLM evaluation failed: {e}, using default 0.5")
            return 0.5  # Fallback
