"""PromptIdentityCore hashing and stage identity helpers (TASK-021)."""

from __future__ import annotations

import hashlib

from yoda.mind.evaluation.data import PromptIdentity
from yoda.mind.evaluation.prompt_identity_core import (
    GROUNDED_DELIVERY_PROMPT_ID,
    INTENT_CLASSIFIER_PROMPT_ID,
    SKILL_EXECUTOR_PROMPT_ID,
    SKILL_SELECTOR_PROMPT_ID,
    PromptIdentityCore,
    skill_workflow_prompt_id,
)


def test_hash_control_plane_is_stable_sha256_over_ordered_parts() -> None:
    parts = ("alpha", "beta", "gamma")
    expected = hashlib.sha256(b"\x00".join(p.encode("utf-8") for p in parts)).hexdigest()
    assert PromptIdentityCore.hash_control_plane(parts) == expected
    assert PromptIdentityCore.hash_control_plane(parts) == PromptIdentityCore.hash_control_plane(
        list(parts),
    )


def test_hash_control_plane_order_matters() -> None:
    assert PromptIdentityCore.hash_control_plane(("a", "b")) != PromptIdentityCore.hash_control_plane(
        ("b", "a"),
    )


def test_hash_control_plane_independent_of_user_text() -> None:
    control = ("system-rules", "catalog")
    with_user = PromptIdentityCore.hash_control_plane((*control, "user said hello"))
    without_user = PromptIdentityCore.hash_control_plane(control)
    assert with_user != without_user
    # Control-plane helpers must not bake user text into stage identities.
    selection = PromptIdentityCore.selection_identity("catalog-v1")
    assert "hello" not in selection.prompt_hash
    assert selection.prompt_id == SKILL_SELECTOR_PROMPT_ID


def test_skill_workflow_prompt_id() -> None:
    assert skill_workflow_prompt_id("search_web") == "search_web/v1"


def test_intent_identity_stable_and_versioned() -> None:
    first = PromptIdentityCore.intent_identity()
    second = PromptIdentityCore.intent_identity()
    assert first == second
    assert first.prompt_id == INTENT_CLASSIFIER_PROMPT_ID
    assert len(first.prompt_hash) == 64


def test_selection_identity_includes_catalog_control_text() -> None:
    a = PromptIdentityCore.selection_identity("catalog-a")
    b = PromptIdentityCore.selection_identity("catalog-b")
    assert a.prompt_id == SKILL_SELECTOR_PROMPT_ID
    assert a.prompt_hash != b.prompt_hash


def test_execution_identity_returns_executor_and_skill_prompts() -> None:
    identities = PromptIdentityCore.execution_identity(
        "search_web",
        "workflow text",
        '[{"name":"web_search"}]',
    )
    assert [item.prompt_id for item in identities] == [
        SKILL_EXECUTOR_PROMPT_ID,
        "search_web/v1",
    ]
    assert all(isinstance(item, PromptIdentity) for item in identities)
    assert identities[0].prompt_hash != identities[1].prompt_hash


def test_delivery_identity_excludes_source_text_variance() -> None:
    identity = PromptIdentityCore.delivery_identity()
    assert identity.prompt_id == GROUNDED_DELIVERY_PROMPT_ID
    assert len(identity.prompt_hash) == 64
    # Same template every call — no per-run source_text / timestamps.
    assert identity == PromptIdentityCore.delivery_identity()


def test_production_prompt_id_constants_match_helpers() -> None:
    from yoda.mind.agent.core.delivery_core import (
        GROUNDED_DELIVERY_PROMPT_ID as delivery_id,
    )
    from yoda.mind.agent.core.react_loop import (
        SKILL_EXECUTOR_PROMPT_ID as executor_id,
        SKILL_SELECTOR_PROMPT_ID as selector_id,
    )
    from yoda.mind.cognition import INTENT_CLASSIFIER_PROMPT_ID as intent_id

    assert intent_id == INTENT_CLASSIFIER_PROMPT_ID
    assert selector_id == SKILL_SELECTOR_PROMPT_ID
    assert executor_id == SKILL_EXECUTOR_PROMPT_ID
    assert delivery_id == GROUNDED_DELIVERY_PROMPT_ID
    assert PromptIdentityCore.intent_identity().prompt_id == intent_id
    assert PromptIdentityCore.delivery_identity().prompt_id == delivery_id
