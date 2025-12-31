"""Tests for Centralized Logging Configuration"""

import logging
import tempfile
from pathlib import Path

import pytest

from codegraph_shared.common.logging_config import (
    AgentLogFormatter,
    get_agent_logger,
    setup_agent_logging,
    setup_cli_logging,
)


class TestLoggingSetup:
    """Test centralized logging setup"""

    def test_setup_agent_logging_file_only(self):
        """파일 로깅만 설정"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            logger = setup_agent_logging(log_file=log_file, console=False, level=logging.DEBUG)

            assert logger.level == logging.DEBUG
            assert len(logger.handlers) == 1
            assert isinstance(logger.handlers[0], logging.FileHandler)
            assert not logger.propagate

    def test_setup_agent_logging_console_only(self):
        """콘솔 로깅만 설정"""
        logger = setup_agent_logging(log_file=None, console=True, level=logging.INFO)

        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)

    def test_setup_agent_logging_both(self):
        """파일 + 콘솔 로깅"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            logger = setup_agent_logging(log_file=log_file, console=True, level=logging.WARNING)

            assert len(logger.handlers) == 2
            handler_types = {type(h) for h in logger.handlers}
            assert logging.FileHandler in handler_types
            assert logging.StreamHandler in handler_types

    def test_setup_agent_logging_creates_dir(self):
        """로그 디렉터리 자동 생성"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "nested" / "dir" / "test.log"

            logger = setup_agent_logging(log_file=log_file)

            assert log_file.parent.exists()

    def test_setup_agent_logging_no_duplicates(self):
        """중복 호출 시 핸들러 중복 방지"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            logger1 = setup_agent_logging(log_file=log_file, console=True)
            handler_count1 = len(logger1.handlers)

            logger2 = setup_agent_logging(log_file=log_file, console=True)
            handler_count2 = len(logger2.handlers)

            assert handler_count1 == handler_count2 == 2
            assert logger1 is logger2  # Same logger instance

    def test_setup_agent_logging_custom_name(self):
        """커스텀 logger 이름"""
        logger = setup_agent_logging(logger_name="test.custom", console=True)

        assert logger.name == "test.custom"

    def test_get_agent_logger(self):
        """Logger 가져오기"""
        # Setup first
        setup_agent_logging(console=True)

        # Get logger
        logger = get_agent_logger("src.agent.test")

        assert logger.name == "src.agent.test"
        assert isinstance(logger, logging.Logger)

    def test_setup_cli_logging_default(self):
        """CLI logging default 설정"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger, log_file = setup_cli_logging(verbose=False, log_dir=Path(tmpdir))

            assert log_file == Path(tmpdir) / "agent_v8.log"
            assert logger.level == logging.INFO
            # verbose=False → file only
            assert len(logger.handlers) == 1

    def test_setup_cli_logging_verbose(self):
        """CLI logging verbose 모드"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger, log_file = setup_cli_logging(verbose=True, log_dir=Path(tmpdir))

            assert logger.level == logging.DEBUG
            # verbose=True → file + console
            assert len(logger.handlers) == 2

    def test_agent_log_formatter_basic(self):
        """AgentLogFormatter 기본 포맷"""
        formatter = AgentLogFormatter()

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py", lineno=1, msg="Test message", args=(), exc_info=None
        )

        formatted = formatter.format(record)

        assert "test" in formatted
        assert "Test message" in formatted
        assert "INFO" in formatted

    def test_agent_log_formatter_with_details(self):
        """AgentLogFormatter with details"""
        formatter = AgentLogFormatter()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py", lineno=1, msg="Error occurred", args=(), exc_info=None
        )
        record.details = {"field": "test", "value": 123}

        formatted = formatter.format(record)

        assert "Error occurred" in formatted
        assert "Details:" in formatted
        assert "field" in formatted


class TestLoggingIntegration:
    """Test logging in real scenarios"""

    def test_logging_to_file_works(self):
        """파일에 실제로 로그가 기록되는지 확인"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            logger = setup_agent_logging(log_file=log_file, level=logging.INFO)

            logger.info("Test message")
            logger.debug("Debug message")  # Should not appear (level=INFO)
            logger.error("Error message")

            # Read log file
            content = log_file.read_text()

            assert "Test message" in content
            assert "Error message" in content
            assert "Debug message" not in content  # Filtered by level

    def test_logging_with_error_details(self):
        """Error details 로깅"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            logger = setup_agent_logging(log_file=log_file, level=logging.INFO)

            details = {"field": "max_iterations", "value": -1}
            logger.error("Validation failed", extra={"details": details})

            content = log_file.read_text()

            assert "Validation failed" in content
            assert "Details:" in content
            assert "max_iterations" in content

    def test_no_propagation(self):
        """로그가 root logger로 전파되지 않는지 확인"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            logger = setup_agent_logging(log_file=log_file)

            assert not logger.propagate
