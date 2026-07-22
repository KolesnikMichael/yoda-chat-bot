"""Privacy-safe routing stage diagnostic formatters (TASK-021)."""

from __future__ import annotations

from yoda.mind.evaluation.data import StageDiagnostic


class RoutingTelemetryCore:
    @staticmethod
    def format_info(diagnostic: StageDiagnostic) -> str:
        return RoutingTelemetryCore._format(diagnostic)

    @staticmethod
    def format_warning(diagnostic: StageDiagnostic) -> str:
        return RoutingTelemetryCore._format(diagnostic)

    @staticmethod
    def _format(diagnostic: StageDiagnostic) -> str:
        parts = [
            f"stage={diagnostic.stage.value}",
            f"outcome={diagnostic.outcome.value}",
        ]
        if diagnostic.model_id is not None:
            parts.append(f"model_id={diagnostic.model_id}")
        for prompt in diagnostic.prompts:
            parts.append(f"prompt_id={prompt.prompt_id}")
            parts.append(f"prompt_hash={prompt.prompt_hash}")
        if diagnostic.detail is not None:
            parts.append(f"detail={diagnostic.detail}")
        return " ".join(parts)
