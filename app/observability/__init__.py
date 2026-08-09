"""Operational signals for Oga Foreman.

The package deliberately uses small standard-library implementations.  Cloud
Logging, Cloud Trace, and Cloud Monitoring can consume the same structured
events later without making the domain code depend on a vendor SDK.
"""

from .context import CorrelationContext, bind_context, current_context, new_correlation_context
from .health import HealthCheck, HealthRegistry, create_health_router
from .logging import configure_logging, log_event
from .metrics import MetricRegistry, metrics
from .probes import configuration_probe, firestore_probe, storage_probe
from .tracing import TraceSpan, new_trace_id

__all__ = [
    "CorrelationContext",
    "HealthCheck",
    "HealthRegistry",
    "MetricRegistry",
    "TraceSpan",
    "bind_context",
    "configure_logging",
    "create_health_router",
    "current_context",
    "log_event",
    "metrics",
    "configuration_probe",
    "firestore_probe",
    "storage_probe",
    "new_correlation_context",
    "new_trace_id",
]
