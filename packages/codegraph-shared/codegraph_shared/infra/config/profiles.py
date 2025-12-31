"""
프로파일 기반 설정

환경별로 다른 설정을 적용합니다:
- local: 로컬 개발/랩탑 환경 (Redis, Memgraph 비활성화)
- cloud: 클라우드/프로덕션 환경 (모든 서비스 필수)
- dev: 개발 서버 환경
- prod: 프로덕션 환경

Laptop Mode (local):
    - PostgreSQL, Qdrant, Tantivy만 필수
    - Redis: 비활성화 (L1 메모리 캐시만)
    - Memgraph: 비활성화 (UnifiedGraphIndex 인메모리)
    - 정적분석 완전 동작 (외부 그래프 DB 불필요)

Server Mode (cloud/prod):
    - Redis: 분산 캐시, Multi-Agent 락
    - Memgraph: VFG 영속화, Rust Taint Engine
    - 대규모 코드베이스 최적화

사용법:
    export SEMANTICA_PROFILE=local  # 랩탑/개발
    export SEMANTICA_PROFILE=cloud  # 서버/프로덕션
"""

import os
from enum import Enum


class Profile(str, Enum):
    """환경 프로파일"""

    LOCAL = "local"  # 로컬 개발 (최소 의존성)
    CLOUD = "cloud"  # 클라우드/프로덕션 (모든 기능)
    DEV = "dev"  # 개발 서버
    PROD = "prod"  # 프로덕션


class ProfileConfig:
    """프로파일별 설정"""

    def __init__(self, profile: str | None = None):
        """
        Args:
            profile: 프로파일 이름 (None이면 환경변수에서 읽음)
        """
        profile_str = profile or os.getenv("SEMANTICA_PROFILE", Profile.LOCAL.value)

        try:
            self.profile = Profile(profile_str.lower())
        except ValueError:
            import sys

            print(f"⚠️  알 수 없는 프로파일: {profile_str}, 기본값(local) 사용", file=sys.stderr)
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
        """로컬 개발/랩탑 환경 설정"""
        import sys

        # Print to stderr to avoid polluting MCP stdout
        print("🏠 Profile: LOCAL (랩탑 모드)", file=sys.stderr)

        # Redis: 비활성화 (L1 메모리 캐시만 사용)
        self.use_redis = False

        # Memgraph: 비활성화 (UnifiedGraphIndex 인메모리 사용)
        self.use_memgraph = False

        # PostgreSQL: 선호 (없으면 SQLite 자동 fallback)
        self.use_postgres = self._check_service_available("postgres", optional=True)

        # Qdrant: 선호 (없으면 인메모리 fallback)
        self.use_qdrant = self._check_service_available("qdrant", optional=True)

        # Multi-Agent: 비활성화 (단일 에이전트)
        self.enable_multi_agent = False

        # 모니터링: 비활성화
        self.enable_monitoring = False

        # 로깅 레벨
        self.log_level = "DEBUG"

        print("  ⚡ Storage: auto-detect (PostgreSQL → SQLite fallback)", file=sys.stderr)
        print("  ⚡ Vector: auto-detect (Qdrant → in-memory fallback)", file=sys.stderr)
        print("  ⚠️  Redis: 비활성화 (L1 메모리 캐시)", file=sys.stderr)
        print("  ⚠️  Memgraph: 비활성화 (UnifiedGraphIndex)", file=sys.stderr)
        print("  🚫 Multi-Agent: 비활성화", file=sys.stderr)
        print("  🚫 Monitoring: 비활성화", file=sys.stderr)

    def _apply_cloud(self):
        """클라우드/프로덕션 환경 설정"""
        import sys

        print("☁️  Profile: CLOUD (클라우드)", file=sys.stderr)

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

        print("  ✅ 모든 서비스 활성화")
        print("  ✅ Multi-Agent: 활성화")
        print("  ✅ Monitoring: 활성화")

    def _apply_dev(self):
        """개발 서버 환경 설정"""
        import sys

        print("🔧 Profile: DEV (개발 서버)", file=sys.stderr)

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

        print("  ✅ 모든 DB 서비스 활성화")
        print("  ✅ Multi-Agent: 활성화")
        mon_icon = "✅" if self.enable_monitoring else "⚠️ "
        mon_status = "활성화" if self.enable_monitoring else "비활성화"
        print(f"  {mon_icon} Monitoring: {mon_status}")

    def _apply_prod(self):
        """프로덕션 환경 설정"""
        import sys

        print("🚀 Profile: PROD (프로덕션)", file=sys.stderr)

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

        print("  ✅ 모든 서비스 필수")
        print("  ✅ Multi-Agent: 활성화")
        print("  ✅ Monitoring: 필수")

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
_profile_config: ProfileConfig | None = None


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
