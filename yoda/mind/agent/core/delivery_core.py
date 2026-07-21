"""Pure delivery claim policy and authoritative renderer instructions."""

from __future__ import annotations

import json

from yoda.mind.agent.data.outcome_data import (
    AllowedClaim,
    ClarificationResult,
    DeliveryPayload,
    ExecutionOutcome,
    JobKind,
    OutcomeStatus,
    ProhibitedClaim,
    ResultKind,
    StaticMessageDelivery,
    UserOperation,
)

DELIVERY_INSTRUCTION_PREFIX = "GROUNDED DELIVERY:"

_BASE_PROHIBITIONS: tuple[ProhibitedClaim, ...] = (
    ProhibitedClaim.INTERNAL_DETAILS,
    ProhibitedClaim.CHANGED_CERTAINTY,
    ProhibitedClaim.UNPROVED_SIDE_EFFECT,
)


class DeliveryCore:
    @staticmethod
    def build_payload(
        result: ExecutionOutcome | ClarificationResult | StaticMessageDelivery,
    ) -> DeliveryPayload:
        if isinstance(result, ClarificationResult):
            return DeliveryPayload(
                status="clarification",
                operation=UserOperation.REQUESTED_WORK,
                source_text=result.question,
                facts=("status=clarification",),
                allowed_claims=(),
                prohibited_claims=(
                    ProhibitedClaim.UNPROVED_SIDE_EFFECT,
                    ProhibitedClaim.INTERNAL_DETAILS,
                    ProhibitedClaim.CHANGED_CERTAINTY,
                ),
                next_step=None,
                language_policy="match_recent_user",
            )

        if isinstance(result, StaticMessageDelivery):
            return DeliveryPayload(
                status="success",
                operation=UserOperation.DELIVER_STORED_MESSAGE,
                source_text=result.reminder_text,
                facts=(
                    "status=success",
                    f"result_kind={ResultKind.STORED_MESSAGE_DELIVERED}",
                ),
                allowed_claims=(AllowedClaim.STORED_TEXT_DELIVERED,),
                prohibited_claims=(
                    ProhibitedClaim.LIVE_RECOMPUTATION,
                    *_BASE_PROHIBITIONS,
                ),
                next_step=None,
                language_policy="preserve_source",
            )

        if result.status is OutcomeStatus.FAILURE:
            return DeliveryPayload(
                status="failure",
                operation=result.operation,
                source_text=result.summary,
                facts=(
                    "status=failure",
                    f"failure_category={result.failure_category}",
                ),
                allowed_claims=(AllowedClaim.SAFE_LIMITATION,),
                prohibited_claims=_BASE_PROHIBITIONS,
                next_step=result.next_step,
                language_policy="match_recent_user",
            )

        return DeliveryCore._success_payload(result)

    @staticmethod
    def build_instruction(
        payload: DeliveryPayload,
        current_time_utc: str,
    ) -> str:
        allowed = ", ".join(claim.value for claim in payload.allowed_claims) or "(none)"
        prohibited = (
            ", ".join(claim.value for claim in payload.prohibited_claims) or "(none)"
        )
        next_step = payload.next_step.value if payload.next_step else "(none)"
        language = payload.language_policy
        untrusted = json.dumps(
            {
                "status": payload.status,
                "operation": payload.operation.value,
                "source_text": payload.source_text,
                "facts": list(payload.facts),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        # JSON quoting does not neutralize the surrounding XML-like delimiter.
        untrusted = (
            untrusted.replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
        )
        rules = (
            f"{DELIVERY_INSTRUCTION_PREFIX} Render only the authorized meaning. "
            f"status={payload.status}; operation={payload.operation.value}; "
            f"allowed_claims=[{allowed}]; prohibited_claims=[{prohibited}]; "
            f"next_step={next_step}; language_policy={language}. "
            "Do not add facts, change certainty, disclose internal names, "
            "or imply unproven side effects. "
            "Rephrase source_text only within those bounds. "
            f"Current time: {current_time_utc}. "
            f'<delivery_data trust="untrusted">{untrusted}</delivery_data>'
        )
        return rules

    @staticmethod
    def _success_payload(outcome: ExecutionOutcome) -> DeliveryPayload:
        facts = [
            "status=success",
            f"operation={outcome.operation.value}",
            f"result_kind={outcome.result_kind}",
        ]
        if outcome.job_kind is not None:
            facts.append(f"job_kind={outcome.job_kind.value}")
        if outcome.schedule is not None:
            facts.append(f"schedule={outcome.schedule}")
        if outcome.scheduled_operation is not None:
            facts.append(
                f"scheduled_operation={outcome.scheduled_operation.value}",
            )

        if outcome.result_kind is ResultKind.SCHEDULED_JOB:
            if outcome.job_kind is JobKind.MESSAGE:
                allowed = (AllowedClaim.STORED_TEXT_SCHEDULED,)
                prohibited = (
                    ProhibitedClaim.LIVE_RECOMPUTATION,
                    ProhibitedClaim.FUTURE_RESULT,
                    *_BASE_PROHIBITIONS,
                )
            else:
                allowed = (AllowedClaim.DYNAMIC_OPERATION_SCHEDULED,)
                prohibited = (
                    ProhibitedClaim.FUTURE_RESULT,
                    *_BASE_PROHIBITIONS,
                )
        elif outcome.result_kind is ResultKind.PICTURE_SENT:
            allowed = (AllowedClaim.PICTURE_SENT,)
            prohibited = _BASE_PROHIBITIONS
        elif outcome.result_kind is ResultKind.STORED_MESSAGE_DELIVERED:
            allowed = (AllowedClaim.STORED_TEXT_DELIVERED,)
            prohibited = (
                ProhibitedClaim.LIVE_RECOMPUTATION,
                *_BASE_PROHIBITIONS,
            )
        else:
            allowed = (AllowedClaim.OPERATION_COMPLETED,)
            prohibited = (
                ProhibitedClaim.UNCREATED_JOB,
                *_BASE_PROHIBITIONS,
            )

        return DeliveryPayload(
            status="success",
            operation=outcome.operation,
            source_text=outcome.summary,
            facts=tuple(facts),
            allowed_claims=allowed,
            prohibited_claims=prohibited,
            next_step=None,
            language_policy="match_recent_user",
        )
