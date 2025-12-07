"""
프로파일 기반 설정

환경별로 다른 설정을 적용합니다:
- local: 로컬 개발 환경 (Redis, Memgraph 선택)
- cloud: 클라우드/프로덕션 환경 (모든 서비스 필수)
- dev: 개발 서버 환경
- prod: 프로덕션 환경

사용법:
    export SEMANTICA_PROFILE=local
    export SEMANTICA_PROFILE=cloud
"""

import os
from enum import Enum
from typing import Optional


class Profile(str, Enum):
    """환경 프로파일"""

    LOCAL = "local"  # 로컬 개발 (최소 의존성)
    CLOUD = "cloud"  # 클라우드/프로덕션 (모든 기능)
    DEV = "dev"  # 개발 서버
    PROD = "prod"  # 프로덕션


class ProfileConfig:
    """프로파일별 설정"""

    def __init__(self, profile: Optional[str] = None):
        """
        Args:
            profile: 프로파일 이름 (None이면 환경변수에서 읽음)
        """
        profile_str = profile or os.getenv("SEMANTICA_PROFILE", Profile.LOCAL.value)

        try:
            self.profile = Profile(profile_str.lower())
        except ValueError:
            print(f"⚠️  알 수 없는 프로파일: {profile_str}, 기본값(local) 사용")
            self.profile = Profile.LOCAL

        self._apply_profile()

    def _apply_profile(self):
        """프로파일별 설정 적용"""

        if self.profile == Profile.LOCAL:
            self._apply_local()
        elif self.profile == Profile.CLOUD:
            self._apply_cloud()
        elif self.profile == Profile.DEV:
            self._apply_dev()
        elif self.profile == Profile.PROD:
            self._apply_prod()

    def _apply_local(self):
        """로컬 개발 환경 설정"""
        print("🏠 Profile: LOCAL (로컬 개발)")

        # Redis: 선택적 (없으면 메모리 모드)
        self.use_redis = self._check_service_available("redis", optional=True)

        # Memgraph: 선택적 (없으면 경량 분석)
        self.use_memgraph = self._check_service_available("memgraph", optional=True)

        # PostgreSQL: 필수
        self.use_postgres = self._check_service_available("postgres", optional=False)

        # Qdrant: 필수
        self.use_qdrant = self._check_service_available("qdrant", optional=False)

        # Multi-Agent: 비활성화 (단일 에이전트)
        self.enable_multi_agent = False

        # 모니터링: 비활성화
        self.enable_monitoring = False

        # 로깅 레벨
        self.log_level = "DEBUG"

        print(f"  ✅ PostgreSQL: 필수")
        print(f"  ✅ Qdrant: 필수")
        print(f"  {'✅' if self.use_redis else '⚠️ '} Redis: {'사용' if self.use_redis else '메모리 모드'}")
        print(f"  {'✅' if self.use_memgraph else '⚠️ '} Memgraph: {'사용' if self.use_memgraph else '경량 분석'}")
        print(f"  🚫 Multi-Agent: 비활성화")
        print(f"  🚫 Monitoring: 비활성화")

    def _apply_cloud(self):
        """클라우드/프로덕션 환경 설정"""
        print("☁️  Profile: CLOUD (클라우드)")

        # 모든 서비스 필수
        self.use_redis = True
        self.use_memgraph = True
        self.use_postgres = True
        self.use_qdrant = True

        # Multi-Agent: 활성화
        self.enable_multi_agent = True

        # 모니터링: 활성화
        self.enable_monitoring = True

        # 로깅 레벨
        self.log_level = "INFO"

        print(f"  ✅ 모든 서비스 활성화")
        print(f"  ✅ Multi-Agent: 활성화")
        print(f"  ✅ Monitoring: 활성화")

    def _apply_dev(self):
        """개발 서버 환경 설정"""
        print("🔧 Profile: DEV (개발 서버)")

        # 대부분 서비스 활성화
        self.use_redis = True
        self.use_memgraph = True
        self.use_postgres = True
        self.use_qdrant = True

        # Multi-Agent: 활성화
        self.enable_multi_agent = True

        # 모니터링: 선택적
        self.enable_monitoring = self._check_monitoring_available()

        # 로깅 레벨
        self.log_level = "DEBUG"

        print(f"  ✅ 모든 DB 서비스 활성화")
        print(f"  ✅ Multi-Agent: 활성화")
        print(
            f"  {'✅' if self.enable_monitoring else '⚠️ '} Monitoring: {'활성화' if self.enable_monitoring else '비활성화'}"
        )

    def _apply_prod(self):
        """프로덕션 환경 설정"""
        print("🚀 Profile: PROD (프로덕션)")

        # 모든 서비스 필수
        self.use_redis = True
        self.use_memgraph = True
        self.use_postgres = True
        self.use_qdrant = True

        # Multi-Agent: 활성화
        self.enable_multi_agent = True

        # 모니터링: 필수
        self.enable_monitoring = True

        # 로깅 레벨
        self.log_level = "WARNING"

        print(f"  ✅ 모든 서비스 필수")
        print(f"  ✅ Multi-Agent: 활성화")
        print(f"  ✅ Monitoring: 필수")

    def _check_service_available(self, service: str, optional: bool = True) -> bool:
        """
        서비스 사용 가능 여부 확인

        Args:
            service: 서비스 이름
            optional: 선택적 서비스인지 여부

        Returns:
            사용 가능 여부
        """
        # 환경변수로 명시적 설정 가능
        env_key = f"SEMANTICA_USE_{service.upper()}"
        env_value = os.getenv(env_key)

        if env_value is not None:
            return env_value.lower() in ("true", "1", "yes")

        # 서비스별 연결 정보 확인
        if service == "redis":
            return bool(os.getenv("SEMANTICA_REDIS_URL"))
        elif service == "memgraph":
            return bool(os.getenv("SEMANTICA_MEMGRAPH_URI"))
        elif service == "postgres":
            return bool(os.getenv("SEMANTICA_DATABASE_URL"))
        elif service == "qdrant":
            return bool(os.getenv("SEMANTICA_QDRANT_URL"))

        # 기본값: 선택적이면 False, 필수면 True
        return not optional

    def _check_monitoring_available(self) -> bool:
        """모니터링 시스템 사용 가능 여부"""
        return bool(os.getenv("SEMANTICA_PROMETHEUS_PORT"))

    def is_local(self) -> bool:
        """로컬 환경인지"""
        return self.profile == Profile.LOCAL

    def is_cloud(self) -> bool:
        """클라우드 환경인지"""
        return self.profile in (Profile.CLOUD, Profile.PROD)

    def should_use_redis(self) -> bool:
        """Redis 사용 여부"""
        return self.use_redis

    def should_use_memgraph(self) -> bool:
        """Memgraph 사용 여부"""
        return self.use_memgraph

    def should_enable_multi_agent(self) -> bool:
        """Multi-Agent 활성화 여부"""
        return self.enable_multi_agent

    def should_enable_monitoring(self) -> bool:
        """모니터링 활성화 여부"""
        return self.enable_monitoring

    def get_log_level(self) -> str:
        """로깅 레벨"""
        return self.log_level


# 전역 프로파일 인스턴스
_profile_config: Optional[ProfileConfig] = None


def get_profile_config() -> ProfileConfig:
    """프로파일 설정 가져오기 (싱글톤)"""
    global _profile_config

    if _profile_config is None:
        _profile_config = ProfileConfig()

    return _profile_config


def reset_profile_config():
    """프로파일 설정 초기화 (테스트용)"""
    global _profile_config
    _profile_config = None
