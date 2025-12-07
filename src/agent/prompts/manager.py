"""중앙화된 Prompt 관리

모든 Agent 프롬프트를 중앙에서 관리하여:
- 프롬프트 버전 관리 용이
- A/B 테스트 가능
- 프롬프트 튜닝 시 코드 변경 불필요
- 나중에 DB나 파일로 분리 가능
"""


class PromptManager:
    """모든 Agent 프롬프트 중앙 관리"""

    # Intent Classification
    INTENT_CLASSIFICATION = """
You are an AI coding assistant. Classify the user's intent.

User input: {user_input}

Available intents:
- FIX_BUG: Fix existing bugs or errors
- ADD_FEATURE: Add new functionality
- REFACTOR: Improve code structure
- EXPLAIN_CODE: Explain how code works
- REVIEW_CODE: Review code quality

Return JSON:
{{
    "intent": "FIX_BUG",
    "confidence": 0.9,
    "reasoning": "User explicitly mentions fixing a bug"
}}
"""

    # Code Generation (Week 13에서 사용)
    CODE_GENERATION = """
You are a senior {language} developer.

Context:
{context}

Plan:
{plan}

Task:
{task}

Generate high-quality code that:
1. Follows best practices
2. Includes error handling
3. Has clear comments
4. Is production-ready

Return JSON:
{{
    "code": "...",
    "explanation": "...",
    "tests_needed": ["..."]
}}
"""

    # Code Review (Week 11에서 사용)
    CODE_REVIEW = """
You are a code reviewer. Review the following code change.

File: {file_path}
Change:
{diff}

Check for:
1. Security issues
2. Bug potential
3. Code quality
4. Best practices

Return JSON:
{{
    "approved": true/false,
    "issues": [
        {{"severity": "high", "message": "...", "line": 10}}
    ],
    "suggestions": ["..."]
}}
"""

    @staticmethod
    def format(template: str, **kwargs) -> str:
        """프롬프트 포맷팅"""
        return template.format(**kwargs)

    @classmethod
    def get_intent_prompt(cls, user_input: str) -> str:
        """Intent 분류 프롬프트"""
        return cls.format(cls.INTENT_CLASSIFICATION, user_input=user_input)

    @classmethod
    def get_code_gen_prompt(cls, context: str, plan: str, task: str, language: str = "python") -> str:
        """코드 생성 프롬프트"""
        return cls.format(cls.CODE_GENERATION, context=context, plan=plan, task=task, language=language)

    @classmethod
    def get_review_prompt(cls, file_path: str, diff: str) -> str:
        """코드 리뷰 프롬프트"""
        return cls.format(cls.CODE_REVIEW, file_path=file_path, diff=diff)
