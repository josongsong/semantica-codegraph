"""
환경변수 로더 (SOTA: 안전한 .env 로딩)

.env 파일 권한 문제 해결
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class SafeEnvLoader:
    """
    안전한 환경변수 로더

    .env 파일 권한 문제를 우회하면서도
    환경변수를 안전하게 로드
    """

    @staticmethod
    def load_openai_key() -> str | None:
        """
        OpenAI API Key 로드 (SOTA: 다중 소스)

        우선순위:
        1. 환경변수 (SEMANTICA_OPENAI_API_KEY)
        2. 환경변수 (OPENAI_API_KEY)
        3. .env 파일 (직접 파싱)
        4. None
        """
        # 1. 환경변수 우선
        key = os.getenv("SEMANTICA_OPENAI_API_KEY")
        if key:
            logger.info("OpenAI Key loaded from SEMANTICA_OPENAI_API_KEY")
            return key

        key = os.getenv("OPENAI_API_KEY")
        if key:
            logger.info("OpenAI Key loaded from OPENAI_API_KEY")
            return key

        # 2. .env 파일 직접 파싱 (python-dotenv 우회)
        try:
            env_path = Path.cwd() / ".env"
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("SEMANTICA_OPENAI_API_KEY="):
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if key:
                                logger.info("OpenAI Key loaded from .env file")
                                return key
                        elif line.startswith("OPENAI_API_KEY="):
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if key:
                                logger.info("OpenAI Key loaded from .env file")
                                return key
        except Exception as e:
            logger.warning(f"Failed to read .env file: {e}")

        # 3. None
        logger.warning("No OpenAI API Key found")
        return None

    @staticmethod
    def load_model_name() -> str:
        """
        모델명 로드

        우선순위:
        1. SEMANTICA_LITELLM_MODEL
        2. LITELLM_MODEL
        3. 기본값 (gpt-4o-mini)
        """
        model = os.getenv("SEMANTICA_LITELLM_MODEL")
        if model:
            return model

        model = os.getenv("LITELLM_MODEL")
        if model:
            return model

        # .env 파일 직접 파싱
        try:
            env_path = Path.cwd() / ".env"
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("SEMANTICA_LITELLM_MODEL="):
                            model = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if model:
                                return model
        except Exception as e:
            logger.warning(f"Failed to read .env for model: {e}")

        # 기본값
        return "gpt-4o-mini"

    @staticmethod
    def load_all() -> dict[str, str]:
        """
        모든 설정 로드

        Returns:
            {
                "api_key": "sk-...",
                "model": "gpt-4o-mini",
            }
        """
        return {
            "api_key": SafeEnvLoader.load_openai_key() or "",
            "model": SafeEnvLoader.load_model_name(),
        }


# Singleton 인스턴스
ENV_CONFIG = SafeEnvLoader.load_all()
