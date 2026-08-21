"""Label-independent template and slot assignment machinery."""

from __future__ import annotations

import hashlib
import json
import string
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .artifacts import sha256_bytes
from .generator import GeneratedCaseSpec
from .grammar import FROZEN_STRUCTURES, StructureId
from .schema import Stage0Case, StructuredCaseSpec

_ALLOWED_FIELDS = frozenset(
    {
        "action",
        "subject",
        "p_condition",
        "q_condition",
        "p_now",
        "q_now",
        "p_previous",
        "lifecycle",
    }
)
_FORBIDDEN_FIELDS = frozenset({"truth_label", "structure_id", "case_id", "case_set_hash"})


@dataclass(frozen=True, slots=True)
class TextTemplate:
    commitment: str
    trigger_condition: str
    prior_state: str
    observed_event: str
    lifecycle_state: str | None = None

    def validate(self) -> None:
        formatter = string.Formatter()
        for template in (
            self.commitment,
            self.trigger_condition,
            self.prior_state,
            self.observed_event,
            self.lifecycle_state,
        ):
            if template is None:
                continue
            fields = {field for _, field, _, _ in formatter.parse(template) if field}
            if fields & _FORBIDDEN_FIELDS:
                raise ValueError("template references hidden or revealing metadata")
            unknown = fields - _ALLOWED_FIELDS
            if unknown:
                raise ValueError(f"unsupported template fields: {sorted(unknown)}")


@dataclass(frozen=True, slots=True)
class SlotValues:
    action: str
    subject: str
    p_condition: str
    q_condition: str


@dataclass(frozen=True, slots=True)
class TemplateBank:
    version_id: str
    authorship_source: str
    templates: Mapping[StructureId, tuple[TextTemplate, ...]]
    slots: tuple[SlotValues, ...]
    exact_bytes: bytes
    sha256: str

    @classmethod
    def from_bytes(cls, content: bytes) -> TemplateBank:
        digest = sha256_bytes(content)
        raw = json.loads(content)
        templates = {
            StructureId(key): tuple(TextTemplate(**item) for item in values)
            for key, values in raw["templates"].items()
        }
        slots = tuple(SlotValues(**item) for item in raw["slots"])
        bank = cls(
            version_id=raw["version_id"],
            authorship_source=raw["authorship_source"],
            templates=templates,
            slots=slots,
            exact_bytes=content,
            sha256=digest,
        )
        bank.validate()
        return bank

    def validate(self) -> None:
        if set(self.templates) != set(FROZEN_STRUCTURES):
            raise ValueError("template bank must cover exactly the five frozen structures")
        if not self.slots:
            raise ValueError("template bank needs at least one slot set")
        if not self.version_id or not self.authorship_source:
            raise ValueError("template provenance fields must be non-empty")
        for values in self.templates.values():
            if not values:
                raise ValueError("each frozen structure needs at least one template")
            for template in values:
                template.validate()
        if sha256_bytes(self.exact_bytes) != self.sha256:
            raise ValueError("template-bank hash mismatch")


@dataclass(frozen=True, slots=True)
class TextAssignment:
    template_index: int
    slot_index: int


def _choice(seed: str, namespace: str, case: StructuredCaseSpec, size: int) -> int:
    # Deliberately excludes truth-bearing booleans and any truth label.
    material = (
        f"{seed}\x00{namespace}\x00{case.case_id}\x00{case.structure_id.value}\x00{case.ordinal}"
    )
    return int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big") % size


def assignment_for(seed: str, case: StructuredCaseSpec, bank: TemplateBank) -> TextAssignment:
    templates = bank.templates[case.structure_id]
    return TextAssignment(
        template_index=_choice(seed, "template", case, len(templates)),
        slot_index=_choice(seed, "slots", case, len(bank.slots)),
    )


def _render_context(spec: StructuredCaseSpec, slots: SlotValues) -> dict[str, str]:
    return {
        "action": slots.action,
        "subject": slots.subject,
        "p_condition": slots.p_condition,
        "q_condition": slots.q_condition,
        "p_now": "satisfied" if spec.p_now else "unmet",
        "q_now": "satisfied" if spec.q_now else "unmet",
        "p_previous": "satisfied" if spec.p_previous else "unmet",
        "lifecycle": spec.lifecycle_state.value if spec.lifecycle_state else "not applicable",
    }


def textualize_case(
    generated: GeneratedCaseSpec,
    *,
    seed: str,
    bank: TemplateBank,
) -> Stage0Case:
    """Render one case; truth is metadata and never influences assignment."""

    assignment = assignment_for(seed, generated.spec, bank)
    template = bank.templates[generated.spec.structure_id][assignment.template_index]
    context: Mapping[str, Any] = _render_context(generated.spec, bank.slots[assignment.slot_index])
    lifecycle = template.lifecycle_state.format_map(context) if template.lifecycle_state else None
    return Stage0Case(
        case_id=generated.spec.case_id,
        commitment=template.commitment.format_map(context),
        trigger_condition=template.trigger_condition.format_map(context),
        prior_state=template.prior_state.format_map(context),
        observed_event=template.observed_event.format_map(context),
        lifecycle_state=lifecycle,
        structured_spec=generated.spec,
        truth_label=generated.truth_label,
        structure_id=generated.spec.structure_id,
        authorship_source=bank.authorship_source,
        version_id=bank.version_id,
    )
