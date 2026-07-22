"""Prompt identity IDs and control-plane hashing (TASK-021)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from yoda.mind.evaluation.data import PromptIdentity

INTENT_CLASSIFIER_PROMPT_ID = "intent_classifier/v1"
SKILL_SELECTOR_PROMPT_ID = "skill_selector/v1"
SKILL_EXECUTOR_PROMPT_ID = "skill_executor/v1"
GROUNDED_DELIVERY_PROMPT_ID = "grounded_delivery/v1"

__all__ = [
    "GROUNDED_DELIVERY_PROMPT_ID",
    "INTENT_CLASSIFIER_PROMPT_ID",
    "PromptIdentityCore",
    "SKILL_EXECUTOR_PROMPT_ID",
    "SKILL_SELECTOR_PROMPT_ID",
    "skill_workflow_prompt_id",
]


def skill_workflow_prompt_id(skill_name: str) -> str:
    return f"{skill_name}/v1"


class PromptIdentityCore:
    @staticmethod
    def hash_control_plane(parts: Sequence[str]) -> str:
        payload = b"\x00".join(part.encode("utf-8") for part in parts)
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def intent_identity() -> PromptIdentity:
        from yoda.mind.cognition import (
            INTENT_CLASSIFICATION_PROMPT,
            INTENT_CLASSIFIER_PROMPT_ID as prompt_id,
        )

        return PromptIdentity(
            prompt_id=prompt_id,
            prompt_hash=PromptIdentityCore.hash_control_plane(
                (INTENT_CLASSIFICATION_PROMPT,),
            ),
        )

    @staticmethod
    def selection_identity(catalog_control_text: str) -> PromptIdentity:
        from yoda.mind.agent.core.react_loop import (
            SELECTION_SYSTEM_PROMPT,
            SKILL_SELECTOR_PROMPT_ID as prompt_id,
        )

        return PromptIdentity(
            prompt_id=prompt_id,
            prompt_hash=PromptIdentityCore.hash_control_plane(
                (SELECTION_SYSTEM_PROMPT, catalog_control_text),
            ),
        )

    @staticmethod
    def execution_identity(
        skill_name: str,
        workflow_text: str,
        tool_schemas_canonical_json: str,
    ) -> list[PromptIdentity]:
        from yoda.mind.agent.core.react_loop import (
            EXECUTION_SYSTEM_PROMPT,
            SKILL_EXECUTOR_PROMPT_ID as prompt_id,
        )

        executor = PromptIdentity(
            prompt_id=prompt_id,
            prompt_hash=PromptIdentityCore.hash_control_plane(
                (
                    EXECUTION_SYSTEM_PROMPT,
                    workflow_text,
                    tool_schemas_canonical_json,
                ),
            ),
        )
        skill = PromptIdentity(
            prompt_id=skill_workflow_prompt_id(skill_name),
            prompt_hash=PromptIdentityCore.hash_control_plane((workflow_text,)),
        )
        return [executor, skill]

    @staticmethod
    def delivery_identity() -> PromptIdentity:
        from yoda.mind.agent.core.delivery_core import (
            GROUNDED_DELIVERY_PROMPT_ID as prompt_id,
            GROUNDED_DELIVERY_RULES_TEMPLATE,
        )

        return PromptIdentity(
            prompt_id=prompt_id,
            prompt_hash=PromptIdentityCore.hash_control_plane(
                (GROUNDED_DELIVERY_RULES_TEMPLATE,),
            ),
        )
