"""Small bounded metric registry used by local runs and Cloud Monitoring adapters."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Mapping


@dataclass(frozen=True, slots=True)
class MetricSample:
    name: str
    kind: str
    labels: tuple[tuple[str, str], ...]
    value: float


class MetricRegistry:
    """Counter and histogram registry with bounded label cardinality."""

    def __init__(self, *, allowed_label_values: Mapping[str, frozenset[str]] | None = None) -> None:
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = {}
        self._lock = RLock()
        self._allowed = dict(allowed_label_values or {})

    def increment(
        self,
        name: str,
        *,
        value: float = 1,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + float(value)

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        if value < 0:
            raise ValueError("histogram observations cannot be negative")
        key = self._key(name, labels)
        with self._lock:
            samples = self._histograms.setdefault(key, [])
            samples.append(float(value))

    def timer(self, name: str, *, labels: Mapping[str, str] | None = None) -> "MetricTimer":
        return MetricTimer(self, name, labels or {})

    def snapshot(self) -> tuple[MetricSample, ...]:
        with self._lock:
            samples: list[MetricSample] = []
            for (name, labels), value in self._counters.items():
                samples.append(MetricSample(name, "counter", labels, value))
            for (name, labels), values in self._histograms.items():
                if values:
                    samples.append(
                        MetricSample(name, "histogram_count", labels, float(len(values)))
                    )
                    samples.append(MetricSample(name, "histogram_sum", labels, sum(values)))
            return tuple(sorted(samples, key=lambda item: (item.name, item.kind, item.labels)))

    def prometheus_text(self) -> str:
        lines: list[str] = []
        for sample in self.snapshot():
            label_text = ""
            if sample.labels:
                label_text = (
                    "{"
                    + ",".join(
                        f'{key}="{value.replace(chr(92), chr(92) + chr(92)).replace(chr(34), chr(92) + chr(34))}"'
                        for key, value in sample.labels
                    )
                    + "}"
                )
            lines.append(f"{sample.name}_{sample.kind}{label_text} {sample.value}")
        return "\n".join(lines) + ("\n" if lines else "")

    def _key(
        self, name: str, labels: Mapping[str, str] | None
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        if not name or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_" for char in name):
            raise ValueError("metric names must use lowercase letters, numbers, and underscores")
        normalized = tuple(sorted((str(key), str(value)) for key, value in (labels or {}).items()))
        if len(normalized) > 8:
            raise ValueError("metrics may have at most eight labels")
        for key, value in normalized:
            allowed = self._allowed.get(key)
            if allowed is not None and value not in allowed:
                raise ValueError(f"label value {value!r} is not allowed for {key}")
        return name, normalized


class MetricTimer:
    def __init__(self, registry: MetricRegistry, name: str, labels: Mapping[str, str]) -> None:
        self._registry = registry
        self._name = name
        self._labels = labels
        self._started = monotonic()

    def observe(self) -> float:
        elapsed = monotonic() - self._started
        self._registry.observe(self._name, elapsed, labels=self._labels)
        return elapsed

    def __enter__(self) -> "MetricTimer":
        return self

    def __exit__(self, *_: object) -> None:
        self.observe()


metrics = MetricRegistry(
    allowed_label_values={
        "method": frozenset({"GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"}),
        "status_class": frozenset({"2xx", "3xx", "4xx", "5xx"}),
        "workflow": frozenset(
            {
                "daily_site_update",
                "material_shortage",
                "blocker_delay",
                "daily_brief",
                "approval_continuation",
            }
        ),
    }
)

__all__ = ["MetricRegistry", "MetricSample", "MetricTimer", "metrics"]
