"""
프로파일 설정 테스트
"""

import os

import pytest

from codegraph_shared.infra.config.profiles import Profile, ProfileConfig, reset_profile_config


class TestProfileConfig:
    """프로파일 설정 테스트"""

    def setup_method(self):
        """각 테스트 전에 프로파일 초기화"""
        reset_profile_config()
        # 기존 환경변수 백업
        self._original_profile = os.getenv("SEMANTICA_PROFILE")

    def teardown_method(self):
        """각 테스트 후에 환경변수 복원"""
        if self._original_profile:
            os.environ["SEMANTICA_PROFILE"] = self._original_profile
        elif "SEMANTICA_PROFILE" in os.environ:
            del os.environ["SEMANTICA_PROFILE"]
        reset_profile_config()

    def test_default_profile_is_local(self):
        """기본 프로파일은 local"""
        if "SEMANTICA_PROFILE" in os.environ:
            del os.environ["SEMANTICA_PROFILE"]

        config = ProfileConfig()
        assert config.profile == Profile.LOCAL
        assert config.is_local()
        assert not config.is_cloud()

    def test_local_profile_settings(self):
        """Local 프로파일 설정"""
        config = ProfileConfig(profile="local")

        assert config.profile == Profile.LOCAL
        assert config.is_local()
        assert not config.enable_multi_agent
        assert not config.enable_monitoring
        assert config.log_level == "DEBUG"

    def test_cloud_profile_settings(self):
        """Cloud 프로파일 설정"""
        config = ProfileConfig(profile="cloud")

        assert config.profile == Profile.CLOUD
        assert config.is_cloud()
        assert config.use_redis
        assert config.use_memgraph
        assert config.enable_multi_agent
        assert config.enable_monitoring
        assert config.log_level == "INFO"

    def test_dev_profile_settings(self):
        """Dev 프로파일 설정"""
        config = ProfileConfig(profile="dev")

        assert config.profile == Profile.DEV
        assert config.use_redis
        assert config.use_memgraph
        assert config.enable_multi_agent
        assert config.log_level == "DEBUG"

    def test_prod_profile_settings(self):
        """Prod 프로파일 설정"""
        config = ProfileConfig(profile="prod")

        assert config.profile == Profile.PROD
        assert config.is_cloud()
        assert config.use_redis
        assert config.use_memgraph
        assert config.enable_multi_agent
        assert config.enable_monitoring
        assert config.log_level == "WARNING"

    def test_profile_from_env_variable(self):
        """환경변수에서 프로파일 읽기"""
        os.environ["SEMANTICA_PROFILE"] = "cloud"

        config = ProfileConfig()
        assert config.profile == Profile.CLOUD

    def test_invalid_profile_defaults_to_local(self):
        """잘못된 프로파일은 local로 기본값"""
        config = ProfileConfig(profile="invalid_profile")

        assert config.profile == Profile.LOCAL

    def test_redis_service_check(self):
        """Redis 서비스 체크"""
        # Redis URL이 없으면 False
        if "SEMANTICA_REDIS_URL" in os.environ:
            del os.environ["SEMANTICA_REDIS_URL"]

        config = ProfileConfig(profile="local")
        # Local에서는 Redis 선택적

        # 환경변수로 명시적 설정
        os.environ["SEMANTICA_USE_REDIS"] = "true"
        reset_profile_config()
        config = ProfileConfig(profile="local")
        assert config.should_use_redis()

        os.environ["SEMANTICA_USE_REDIS"] = "false"
        reset_profile_config()
        config = ProfileConfig(profile="local")
        assert not config.should_use_redis()

    def test_multi_agent_control(self):
        """Multi-Agent 활성화 제어"""
        # Local: 비활성화
        config = ProfileConfig(profile="local")
        assert not config.should_enable_multi_agent()

        # Cloud: 활성화
        config = ProfileConfig(profile="cloud")
        assert config.should_enable_multi_agent()

    def test_monitoring_control(self):
        """모니터링 활성화 제어"""
        # Local: 비활성화
        config = ProfileConfig(profile="local")
        assert not config.should_enable_monitoring()

        # Cloud: 활성화
        config = ProfileConfig(profile="cloud")
        assert config.should_enable_monitoring()


class TestProfileIntegration:
    """프로파일 통합 테스트"""

    def test_local_minimal_setup(self):
        """Local 프로파일 - 최소 구성"""
        # Redis, Memgraph 환경변수 제거
        env_backup = {}
        for key in ["SEMANTICA_REDIS_URL", "SEMANTICA_MEMGRAPH_URI"]:
            if key in os.environ:
                env_backup[key] = os.environ[key]
                del os.environ[key]

        try:
            reset_profile_config()
            config = ProfileConfig(profile="local")

            # 최소 구성에서는 Redis, Memgraph 없이도 작동
            assert not config.should_use_redis()  # 메모리 모드
            assert not config.should_use_memgraph()  # 경량 모드

        finally:
            # 환경변수 복원
            for key, value in env_backup.items():
                os.environ[key] = value
            reset_profile_config()

    def test_cloud_full_setup(self):
        """Cloud 프로파일 - 완전 구성"""
        config = ProfileConfig(profile="cloud")

        # Cloud에서는 모든 서비스 필요
        assert config.should_use_redis()
        assert config.should_use_memgraph()
        assert config.should_enable_multi_agent()
        assert config.should_enable_monitoring()
