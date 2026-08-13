"""Canonical material identity, units, and append-only stock ledger."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import AwareDatetime, ConfigDict, Field, field_validator, model_validator

from .models import CanonicalId, DomainModel, IdempotencyKey


class UnknownMaterialUnitError(ValueError):
    code = "VALIDATION_FAILED"


class MaterialUnitMismatchError(ValueError):
    code = "VALIDATION_FAILED"


_UNIT_ALIASES: dict[str, str] = {
    "bag": "bags",
    "bags": "bags",
    "block": "blocks",
    "blocks": "blocks",
    "piece": "pieces",
    "pieces": "pieces",
    "pc": "pieces",
    "pcs": "pieces",
    "unit": "units",
    "units": "units",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "ton": "tonnes",
    "tons": "tonnes",
    "tonne": "tonnes",
    "tonnes": "tonnes",
    "metric ton": "tonnes",
    "metric tons": "tonnes",
    "litre": "litres",
    "litres": "litres",
    "liter": "litres",
    "liters": "litres",
    "l": "litres",
    "metre": "metres",
    "metres": "metres",
    "meter": "metres",
    "meters": "metres",
    "m": "metres",
    "square metre": "m2",
    "square metres": "m2",
    "square meter": "m2",
    "square meters": "m2",
    "m2": "m2",
    "m²": "m2",
    "cubic metre": "m3",
    "cubic metres": "m3",
    "cubic meter": "m3",
    "cubic meters": "m3",
    "m3": "m3",
    "m³": "m3",
    "sheet": "sheets",
    "sheets": "sheets",
    "roll": "rolls",
    "rolls": "rolls",
    "trip": "trips",
    "trips": "trips",
    "load": "loads",
    "loads": "loads",
    "length": "lengths",
    "lengths": "lengths",
    "box": "boxes",
    "boxes": "boxes",
    "bucket": "buckets",
    "buckets": "buckets",
    "gallon": "gallons",
    "gallons": "gallons",
}


def normalize_material_name(value: str) -> str:
    """Normalize a display name or alias without treating it as identity."""

    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    normalized = " ".join(normalized.split())
    if not normalized:
        raise ValueError("material name or alias cannot be empty")
    if len(normalized) > 300:
        raise ValueError("normalized material name is too long")
    return normalized


def canonicalize_unit(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = " ".join(normalized.replace("_", " ").split())
    try:
        return _UNIT_ALIASES[normalized]
    except KeyError as exc:
        raise UnknownMaterialUnitError(f"unknown material unit: {value}") from exc


def ensure_same_unit(material_unit: str, requested_unit: str) -> str:
    canonical_material = canonicalize_unit(material_unit)
    canonical_requested = canonicalize_unit(requested_unit)
    if canonical_material != canonical_requested:
        raise MaterialUnitMismatchError(
            f"material uses {canonical_material}; received {canonical_requested}"
        )
    return canonical_material


class MaterialLedgerEntry(DomainModel):
    """One immutable quantity delta in a material's canonical unit."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: CanonicalId
    project_id: CanonicalId
    material_id: CanonicalId
    quantity_delta: Decimal
    unit: str = Field(min_length=1, max_length=100)
    balance_after: Decimal = Field(ge=0)
    reason: str = Field(min_length=1, max_length=5_000)
    source_event_id: CanonicalId | None = None
    agent_run_id: CanonicalId | None = None
    actor_id: CanonicalId | Literal["system"]
    idempotency_key: IdempotencyKey
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("quantity_delta")
    @classmethod
    def validate_non_zero_delta(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("quantity_delta cannot be zero")
        return value

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        canonical = canonicalize_unit(value)
        if canonical != value:
            raise ValueError("ledger unit must already be canonical")
        return value

    @model_validator(mode="after")
    def validate_balance(self) -> Self:
        if self.balance_after - self.quantity_delta < 0:
            raise ValueError("ledger entry implies an invalid negative prior balance")
        return self


__all__ = [
    "MaterialLedgerEntry",
    "MaterialUnitMismatchError",
    "UnknownMaterialUnitError",
    "canonicalize_unit",
    "ensure_same_unit",
    "normalize_material_name",
]
