"""
Indexing Metrics Collection

Indexing 관련 메트릭을 수집합니다.
- 파일 처리량
- 청크 생성 속도
- 에러율
- 인덱싱 latency
"""

from src.infra.observability import get_logger
from src.infra.observability.otel_setup import get_meter

logger = get_logger(__name__)

# Get OTEL meter
_meter = None


def _get_meter():
    """Get or create OTEL meter."""
    global _meter
    if _meter is None:
        _meter = get_meter(__name__)
    return _meter


# ============================================================================
# Metric Instruments
# ============================================================================

# Counters
_indexing_jobs_total = None
_indexing_files_total = None
_indexing_chunks_total = None
_indexing_errors_total = None

# Histograms
_indexing_duration_histogram = None
_indexing_file_size_histogram = None
_indexing_chunks_per_file_histogram = None

# Gauges (for throughput)
_indexing_files_per_second_gauge = None


def _init_instruments():
    """Initialize OTEL metric instruments."""
    global _indexing_jobs_total, _indexing_files_total, _indexing_chunks_total, _indexing_errors_total
    global _indexing_duration_histogram, _indexing_file_size_histogram, _indexing_chunks_per_file_histogram
    global _indexing_files_per_second_gauge

    meter = _get_meter()
    if meter is None:
        return

    try:
        # Counters
        _indexing_jobs_total = meter.create_counter(
            name="indexing.jobs.total",
            description="Total number of indexing jobs",
            unit="1",
        )

        _indexing_files_total = meter.create_counter(
            name="indexing.files.total",
            description="Total number of files indexed",
            unit="1",
        )

        _indexing_chunks_total = meter.create_counter(
            name="indexing.chunks.total",
            description="Total number of chunks created",
            unit="1",
        )

        _indexing_errors_total = meter.create_counter(
            name="indexing.errors.total",
            description="Total number of indexing errors",
            unit="1",
        )

        # Histograms
        _indexing_duration_histogram = meter.create_histogram(
            name="indexing.duration",
            description="Indexing job duration",
            unit="s",
        )

        _indexing_file_size_histogram = meter.create_histogram(
            name="indexing.file_size",
            description="File size distribution",
            unit="bytes",
        )

        _indexing_chunks_per_file_histogram = meter.create_histogram(
            name="indexing.chunks_per_file",
            description="Number of chunks per file",
            unit="1",
        )

        # Gauge
        _indexing_files_per_second_gauge = meter.create_up_down_counter(
            name="indexing.files_per_second",
            description="File processing throughput",
            unit="files/s",
        )

        logger.info("indexing_metrics_initialized")
    except Exception as e:
        logger.warning("indexing_metrics_init_failed", error=str(e))


# Initialize on module import
_init_instruments()


# ============================================================================
# Metric Recording Functions
# ============================================================================


def record_indexing_job(
    mode: str = "full",
    status: str = "success",
    repo_id: str | None = None,
) -> None:
    """
    Record indexing job count.

    Args:
        mode: Indexing mode (e.g., "full", "incremental", "impact")
        status: Job status ("success", "failed", "cancelled")
        repo_id: Optional repository ID
    """
    if _indexing_jobs_total is None:
        return

    try:
        attributes = {
            "mode": mode,
            "status": status,
        }
        if repo_id:
            attributes["repo_id"] = repo_id

        _indexing_jobs_total.add(1, attributes)
    except Exception as e:
        logger.debug("record_indexing_job_failed", error=str(e))


def record_files_indexed(
    count: int,
    language: str = "unknown",
    mode: str = "full",
    repo_id: str | None = None,
) -> None:
    """
    Record number of files indexed.

    Args:
        count: Number of files
        language: Programming language
        mode: Indexing mode
        repo_id: Optional repository ID
    """
    if _indexing_files_total is None:
        return

    try:
        attributes = {
            "language": language,
            "mode": mode,
        }
        if repo_id:
            attributes["repo_id"] = repo_id

        _indexing_files_total.add(count, attributes)
    except Exception as e:
        logger.debug("record_files_indexed_failed", error=str(e))


def record_chunks_created(
    count: int,
    chunk_type: str = "code",
    repo_id: str | None = None,
) -> None:
    """
    Record number of chunks created.

    Args:
        count: Number of chunks
        chunk_type: Chunk type (e.g., "code", "document", "symbol")
        repo_id: Optional repository ID
    """
    if _indexing_chunks_total is None:
        return

    try:
        attributes = {
            "chunk_type": chunk_type,
        }
        if repo_id:
            attributes["repo_id"] = repo_id

        _indexing_chunks_total.add(count, attributes)
    except Exception as e:
        logger.debug("record_chunks_created_failed", error=str(e))


def record_indexing_error(
    error_type: str,
    stage: str = "unknown",
    repo_id: str | None = None,
) -> None:
    """
    Record indexing error.

    Args:
        error_type: Error type (e.g., "parse_error", "timeout", "oom")
        stage: Indexing stage (e.g., "parsing", "ir_building", "chunking")
        repo_id: Optional repository ID
    """
    if _indexing_errors_total is None:
        return

    try:
        attributes = {
            "error_type": error_type,
            "stage": stage,
        }
        if repo_id:
            attributes["repo_id"] = repo_id

        _indexing_errors_total.add(1, attributes)
    except Exception as e:
        logger.debug("record_indexing_error_failed", error=str(e))


def record_indexing_duration(
    duration_seconds: float,
    mode: str = "full",
    status: str = "success",
) -> None:
    """
    Record indexing job duration.

    Args:
        duration_seconds: Duration in seconds
        mode: Indexing mode
        status: Job status
    """
    if _indexing_duration_histogram is None:
        return

    try:
        attributes = {
            "mode": mode,
            "status": status,
        }

        _indexing_duration_histogram.record(duration_seconds, attributes)
    except Exception as e:
        logger.debug("record_indexing_duration_failed", error=str(e))


def record_file_size(
    size_bytes: int,
    language: str = "unknown",
) -> None:
    """
    Record file size.

    Args:
        size_bytes: File size in bytes
        language: Programming language
    """
    if _indexing_file_size_histogram is None:
        return

    try:
        attributes = {"language": language}

        _indexing_file_size_histogram.record(size_bytes, attributes)
    except Exception as e:
        logger.debug("record_file_size_failed", error=str(e))


def record_chunks_per_file(
    chunk_count: int,
    language: str = "unknown",
) -> None:
    """
    Record number of chunks per file.

    Args:
        chunk_count: Number of chunks
        language: Programming language
    """
    if _indexing_chunks_per_file_histogram is None:
        return

    try:
        attributes = {"language": language}

        _indexing_chunks_per_file_histogram.record(chunk_count, attributes)
    except Exception as e:
        logger.debug("record_chunks_per_file_failed", error=str(e))


def record_throughput(
    files_per_second: float,
    mode: str = "full",
) -> None:
    """
    Record file processing throughput.

    Args:
        files_per_second: Files processed per second
        mode: Indexing mode
    """
    if _indexing_files_per_second_gauge is None:
        return

    try:
        attributes = {"mode": mode}

        # Record as scaled integer (multiply by 100 to preserve precision)
        _indexing_files_per_second_gauge.add(int(files_per_second * 100), attributes)
    except Exception as e:
        logger.debug("record_throughput_failed", error=str(e))


# ============================================================================
# Helper Functions
# ============================================================================


def calculate_throughput(files_processed: int, duration_seconds: float) -> float:
    """
    Calculate file processing throughput.

    Args:
        files_processed: Number of files processed
        duration_seconds: Duration in seconds

    Returns:
        Files per second
    """
    if duration_seconds <= 0:
        return 0.0
    return files_processed / duration_seconds


def calculate_error_rate(errors: int, total: int) -> float:
    """
    Calculate error rate.

    Args:
        errors: Number of errors
        total: Total number of operations

    Returns:
        Error rate (0.0 to 1.0)
    """
    if total == 0:
        return 0.0
    return errors / total
