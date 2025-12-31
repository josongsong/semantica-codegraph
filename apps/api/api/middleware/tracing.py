"""
Tracing Middleware (RFC-SEM-022 SOTA)

OpenTelemetry 통합 분산 트레이싱.

SOTA Features:
- OpenTelemetry span 자동 생성
- W3C Trace Context 전파 (traceparent 헤더)
- 레거시 X-Trace-ID 호환
- 로그에 trace_id/span_id 자동 연결
"""

import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

# OTEL imports (optional)
try:
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind, Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    OTEL_AVAILABLE = True
    _tracer = trace.get_tracer("semantica.api")
    _propagator = TraceContextTextMapPropagator()
except ImportError:
    OTEL_AVAILABLE = False
    _tracer = None
    _propagator = None


class TracingMiddleware(BaseHTTPMiddleware):
    """
    Tracing Middleware (RFC-SEM-022 SOTA).

    OpenTelemetry 분산 트레이싱 + 레거시 호환.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Request → Response with distributed tracing.

        1. W3C traceparent 헤더에서 context 추출 (OTEL)
        2. 없으면 X-Trace-ID 사용 (레거시)
        3. 둘 다 없으면 새 trace 생성
        """
        trace_id = None
        span_id = None

        if OTEL_AVAILABLE and _tracer:
            # Extract W3C Trace Context
            carrier = dict(request.headers)
            ctx = _propagator.extract(carrier)

            # Start span with extracted context
            with _tracer.start_as_current_span(
                f"{request.method} {request.url.path}",
                context=ctx,
                kind=SpanKind.SERVER,
            ) as span:
                # Get trace/span IDs
                span_ctx = span.get_span_context()
                trace_id = format(span_ctx.trace_id, "032x")
                span_id = format(span_ctx.span_id, "016x")

                # Store in request state
                request.state.trace_id = trace_id
                request.state.span_id = span_id

                # Add attributes
                span.set_attribute("http.method", request.method)
                span.set_attribute("http.url", str(request.url))
                span.set_attribute("http.route", request.url.path)

                # Bind to logger
                logger.bind(trace_id=trace_id, span_id=span_id)

                try:
                    response = await call_next(request)

                    # Record response
                    span.set_attribute("http.status_code", response.status_code)
                    if response.status_code >= 400:
                        span.set_status(Status(StatusCode.ERROR))

                    # Add headers
                    response.headers["X-Trace-ID"] = trace_id
                    response.headers["X-Span-ID"] = span_id

                    return response

                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        else:
            # Fallback: legacy trace_id only
            trace_id = (
                request.headers.get("X-Trace-ID")
                or request.headers.get("x-trace-id")
                or f"trace_{uuid.uuid4().hex[:16]}"
            )

            request.state.trace_id = trace_id
            logger.bind(trace_id=trace_id)

            response = await call_next(request)
            response.headers["X-Trace-ID"] = trace_id

            return response


def get_trace_id_from_request(request: Request) -> str:
    """
    Request에서 trace_id 추출 (Dependency).

    Usage:
        @router.get("/example")
        async def example(
            request: Request,
            trace_id: str = Depends(get_trace_id_from_request)
        ):
            logger.info("Processing", trace_id=trace_id)
    """
    if hasattr(request.state, "trace_id"):
        return request.state.trace_id

    # Fallback
    return "trace_unknown"
