"""
OpenTelemetry Setup

OTEL SDK 초기화 및 자동 계측 설정.
"""

import logging
from typing import Any

# Avoid circular import - use logging directly
logger = logging.getLogger(__name__)

# OTEL 의존성 체크
try:
    from opentelemetry import metrics as otel_metrics
    from opentelemetry import trace as otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    OTEL_AVAILABLE = True
    logger.info("opentelemetry_sdk_available")
except ImportError as e:
    OTEL_AVAILABLE = False
    logger.warning(
        "opentelemetry_sdk_not_available",
        error=str(e),
        install_command="pip install opentelemetry-api opentelemetry-sdk",
    )


class OTelSetup:
    """
    OpenTelemetry 초기화 및 설정.

    Features:
    - Metrics export to Prometheus + OTLP
    - Traces export to OTLP (Jaeger/Tempo)
    - Resource attributes (service name, version, etc.)
    """

    def __init__(
        self,
        service_name: str = "codegraph",
        service_version: str = "0.1.0",
        otel_endpoint: str | None = None,
        deployment_environment: str = "development",
        insecure: bool = True,
        tls_cert_path: str | None = None,
        enable_prometheus: bool = True,
        enable_otlp: bool = True,
        enable_tracing: bool = True,
    ):
        """
        Initialize OTEL setup.

        Args:
            service_name: Service name for resource attributes
            service_version: Service version
            otel_endpoint: OTLP endpoint (e.g., "http://localhost:4317")
            deployment_environment: Deployment environment (development, staging, production)
            insecure: Use insecure connection (True for dev, False for production)
            tls_cert_path: TLS certificate path for secure connections (production)
            enable_prometheus: Enable Prometheus exporter
            enable_otlp: Enable OTLP exporter
            enable_tracing: Enable distributed tracing
        """
        if not OTEL_AVAILABLE:
            raise ImportError("OpenTelemetry SDK not installed")

        self.service_name = service_name
        self.service_version = service_version
        self.otel_endpoint = otel_endpoint
        self.deployment_environment = deployment_environment
        self.insecure = insecure
        self.tls_cert_path = tls_cert_path
        self.enable_prometheus = enable_prometheus
        self.enable_otlp = enable_otlp
        self.enable_tracing = enable_tracing

        self._meter_provider: MeterProvider | None = None
        self._tracer_provider: TracerProvider | None = None

    def setup(self) -> None:
        """
        Setup OpenTelemetry SDK.

        Initializes:
        - Resource attributes
        - MeterProvider (metrics)
        - TracerProvider (traces)
        - Exporters (Prometheus, OTLP)
        """
        logger.info(
            f"OTEL setup starting: service={self.service_name}, version={self.service_version}, "
            f"prometheus={self.enable_prometheus}, otlp={self.enable_otlp}, tracing={self.enable_tracing}"
        )

        # 1. Create resource
        resource = self._create_resource()

        # 2. Setup metrics
        if self.enable_prometheus or self.enable_otlp:
            self._setup_metrics(resource)

        # 3. Setup tracing
        if self.enable_tracing:
            self._setup_tracing(resource)

        logger.info("otel_setup_complete")

    def _create_resource(self) -> "Resource":
        """Create resource with service attributes."""
        return Resource(
            attributes={
                SERVICE_NAME: self.service_name,
                SERVICE_VERSION: self.service_version,
                "deployment.environment": self.deployment_environment,
            }
        )

    def _setup_metrics(self, resource: "Resource") -> None:
        """
        Setup metrics with Prometheus and/or OTLP exporters.

        Args:
            resource: Resource attributes
        """
        readers = []

        # Prometheus exporter (pull-based, /metrics endpoint)
        if self.enable_prometheus:
            try:
                # PrometheusMetricReader automatically registers with prometheus_client.REGISTRY
                # No need to specify port - it uses the global registry that FastAPI /metrics exposes
                prometheus_reader = PrometheusMetricReader()
                readers.append(prometheus_reader)
                logger.info("Prometheus exporter enabled - metrics available at /metrics endpoint")
            except Exception as e:
                logger.warning("prometheus_exporter_failed", exc_info=e)

        # OTLP exporter (push-based, to collector)
        if self.enable_otlp and self.otel_endpoint:
            try:
                exporter_kwargs = {
                    "endpoint": self.otel_endpoint,
                    "insecure": self.insecure,
                }

                # Production TLS 설정
                if not self.insecure and self.tls_cert_path:
                    from grpc import ssl_channel_credentials

                    with open(self.tls_cert_path, "rb") as f:
                        cert_data = f.read()
                    exporter_kwargs["credentials"] = ssl_channel_credentials(cert_data)

                otlp_exporter = OTLPMetricExporter(**exporter_kwargs)
                otlp_reader = PeriodicExportingMetricReader(
                    otlp_exporter,
                    export_interval_millis=60000,  # 1분
                )
                readers.append(otlp_reader)
                logger.info(f"OTLP metric exporter enabled: endpoint={self.otel_endpoint}")
            except Exception as e:
                logger.warning("otlp_metric_exporter_failed", exc_info=e)

        # Create MeterProvider
        if readers:
            self._meter_provider = MeterProvider(
                resource=resource,
                metric_readers=readers,
            )
            otel_metrics.set_meter_provider(self._meter_provider)
            logger.info(f"Meter provider initialized with {len(readers)} readers")
        else:
            logger.warning("no_metric_readers_configured")

    def _setup_tracing(self, resource: "Resource") -> None:
        """
        Setup distributed tracing with OTLP exporter.

        Args:
            resource: Resource attributes
        """
        if not self.otel_endpoint:
            logger.warning("tracing_disabled_no_endpoint")
            return

        try:
            # OTLP trace exporter
            exporter_kwargs = {
                "endpoint": self.otel_endpoint,
                "insecure": self.insecure,
            }

            # Production TLS 설정
            if not self.insecure and self.tls_cert_path:
                from grpc import ssl_channel_credentials

                with open(self.tls_cert_path, "rb") as f:
                    cert_data = f.read()
                exporter_kwargs["credentials"] = ssl_channel_credentials(cert_data)

            otlp_exporter = OTLPSpanExporter(**exporter_kwargs)

            # Batch span processor (async export)
            span_processor = BatchSpanProcessor(otlp_exporter)

            # Create TracerProvider
            self._tracer_provider = TracerProvider(resource=resource)
            self._tracer_provider.add_span_processor(span_processor)

            # Set global tracer provider
            otel_trace.set_tracer_provider(self._tracer_provider)

            logger.info(f"Tracer provider initialized: endpoint={self.otel_endpoint}")
        except Exception as e:
            logger.warning("tracer_provider_failed", exc_info=e)

    def get_meter(self, name: str, version: str = "0.1.0") -> Any:
        """
        Get meter for instrumentation.

        Args:
            name: Meter name (usually __name__)
            version: Meter version

        Returns:
            Meter instance
        """
        if not OTEL_AVAILABLE:
            raise ImportError("OpenTelemetry SDK not installed")

        return otel_metrics.get_meter(name, version)

    def get_tracer(self, name: str, version: str = "0.1.0") -> Any:
        """
        Get tracer for instrumentation.

        Args:
            name: Tracer name (usually __name__)
            version: Tracer version

        Returns:
            Tracer instance
        """
        if not OTEL_AVAILABLE:
            raise ImportError("OpenTelemetry SDK not installed")

        return otel_trace.get_tracer(name, version)

    def shutdown(self) -> None:
        """Shutdown OTEL providers (flush pending data)."""
        if self._meter_provider:
            self._meter_provider.shutdown()
            logger.info("meter_provider_shutdown")

        if self._tracer_provider:
            self._tracer_provider.shutdown()
            logger.info("tracer_provider_shutdown")


# Global OTEL setup instance
_otel_setup: OTelSetup | None = None

# Callbacks to invoke after setup
_setup_callbacks: list[callable] = []


def register_setup_callback(callback: callable) -> None:
    """
    Register a callback to be called when OTEL is setup.

    Useful for metrics modules that need to initialize after OTEL is ready.

    Args:
        callback: Function to call (takes no arguments)
    """
    _setup_callbacks.append(callback)


def setup_otel(
    service_name: str = "codegraph",
    service_version: str = "0.1.0",
    otel_endpoint: str | None = None,
    deployment_environment: str = "development",
    insecure: bool = True,
    tls_cert_path: str | None = None,
    enable_prometheus: bool = True,
    enable_otlp: bool = False,
    enable_tracing: bool = False,
) -> OTelSetup | None:
    """
    Setup OpenTelemetry (global singleton).

    Args:
        service_name: Service name
        service_version: Service version
        otel_endpoint: OTLP endpoint
        deployment_environment: Deployment environment (development, staging, production)
        insecure: Use insecure connection (True for dev, False for production)
        tls_cert_path: TLS certificate path for secure connections (production)
        enable_prometheus: Enable Prometheus exporter
        enable_otlp: Enable OTLP exporter
        enable_tracing: Enable distributed tracing

    Returns:
        OTelSetup instance or None if OTEL not available
    """
    global _otel_setup

    if not OTEL_AVAILABLE:
        logger.warning("otel_not_available")
        return None

    if _otel_setup is not None:
        logger.warning("otel_already_setup")
        return _otel_setup

    try:
        _otel_setup = OTelSetup(
            service_name=service_name,
            service_version=service_version,
            otel_endpoint=otel_endpoint,
            deployment_environment=deployment_environment,
            insecure=insecure,
            tls_cert_path=tls_cert_path,
            enable_prometheus=enable_prometheus,
            enable_otlp=enable_otlp,
            enable_tracing=enable_tracing,
        )
        _otel_setup.setup()

        # Invoke registered callbacks
        for callback in _setup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning("otel_callback_failed", exc_info=e)

        return _otel_setup
    except Exception as e:
        logger.error("otel_setup_failed", exc_info=e)
        return None


def get_otel_setup() -> OTelSetup | None:
    """Get global OTEL setup instance."""
    return _otel_setup


def get_meter(name: str, version: str = "0.1.0") -> Any:
    """
    Get meter (convenience function).

    Args:
        name: Meter name
        version: Meter version

    Returns:
        Meter instance or None if OTEL not setup
    """
    if _otel_setup:
        return _otel_setup.get_meter(name, version)
    return None


def get_tracer(name: str, version: str = "0.1.0") -> Any:
    """
    Get tracer (convenience function).

    Args:
        name: Tracer name
        version: Tracer version

    Returns:
        Tracer instance or None if OTEL not setup
    """
    if _otel_setup:
        return _otel_setup.get_tracer(name, version)
    return None


def shutdown_otel() -> None:
    """Shutdown OTEL (flush pending data)."""
    global _otel_setup
    if _otel_setup:
        _otel_setup.shutdown()
        _otel_setup = None
