"""Pure preference aliasing, host normalization, and tool-call preparation."""

from __future__ import annotations

import copy
import ipaddress
from urllib.parse import urlparse

from yoda.mind.agent.data.agent_data import (
    AgentPhase,
    ProtocolIssue,
    ProtocolIssueCategory,
    RequestConstraints,
    ToolCallRequest,
)
from yoda.mind.memory.data.user_profile import UserProfile

_SEARCH_WEB = "search_web"
_LEGACY_WEB_SEARCH = "web_search"
_PREF_BUCKET_KEYS = ("skill_preferences", "skill_preferences_to_add")


class ExecutionContextCore:
    @staticmethod
    def effective_skill_preferences(
        profile: UserProfile,
        skill_name: str,
    ) -> list[str]:
        prefs = profile.skill_preferences or {}
        if skill_name == _SEARCH_WEB:
            return ExecutionContextCore._dedupe_case_insensitive(
                list(prefs.get(_SEARCH_WEB, []))
                + list(prefs.get(_LEGACY_WEB_SEARCH, [])),
            )
        return list(prefs.get(skill_name, []))

    @staticmethod
    def normalize_host(value: str) -> str:
        raw = value.strip()
        if not raw:
            raise ValueError("empty host")
        if "*" in raw or raw.startswith("."):
            raise ValueError(f"invalid host form: {value!r}")

        candidate = raw
        if "://" not in candidate and "/" not in candidate and "@" not in candidate:
            host = candidate
        else:
            parsed = urlparse(
                candidate if "://" in candidate else f"https://{candidate}",
            )
            if parsed.scheme not in ("http", "https"):
                raise ValueError(f"unsupported scheme: {value!r}")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError(f"credentials not allowed: {value!r}")
            if not parsed.hostname:
                raise ValueError(f"missing hostname: {value!r}")
            host = parsed.hostname

        if host.endswith("."):
            host = host[:-1]
        if not host:
            raise ValueError(f"empty host after normalize: {value!r}")

        try:
            ipaddress.ip_address(host)
            raise ValueError(f"IP literals not allowed: {value!r}")
        except ValueError as exc:
            if "IP literals" in str(exc):
                raise

        labels = host.split(".")
        if any(not label or not ExecutionContextCore._is_dns_label(label) for label in labels):
            raise ValueError(f"invalid DNS labels: {value!r}")

        try:
            return host.lower().encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"invalid IDNA host: {value!r}") from exc

    @staticmethod
    def normalize_request_constraints(
        constraints: RequestConstraints,
    ) -> RequestConstraints:
        strict: list[str] = []
        seen_strict: set[str] = set()
        for item in constraints.strict_source_domains:
            host = ExecutionContextCore.normalize_host(item)
            key = host.casefold()
            if key in seen_strict:
                continue
            seen_strict.add(key)
            strict.append(host)

        soft: list[str] = []
        seen_soft: set[str] = set()
        for item in constraints.soft_source_domains:
            host = ExecutionContextCore.normalize_host(item)
            key = host.casefold()
            if key in seen_strict or key in seen_soft:
                continue
            seen_soft.add(key)
            soft.append(host)

        return RequestConstraints(
            strict_source_domains=strict,
            soft_source_domains=soft,
        )

    @staticmethod
    def prepare_tool_requests(
        requests: list[ToolCallRequest],
        constraints: RequestConstraints,
    ) -> tuple[list[ToolCallRequest], ProtocolIssue | None]:
        strict = list(constraints.strict_source_domains)
        strict_set = {h.casefold() for h in strict}
        prepared: list[ToolCallRequest] = []

        for req in requests:
            if req.tool_name == "web_search":
                result = ExecutionContextCore._prepare_web_search(
                    req, strict, strict_set,
                )
                if isinstance(result, ProtocolIssue):
                    return [], result
                prepared.append(result)
            elif req.tool_name == "web_extract" and strict:
                issue = ExecutionContextCore._validate_web_extract(req, strict)
                if issue is not None:
                    return [], issue
                prepared.append(req)
            elif req.tool_name == "schedule_task":
                args = dict(req.arguments)
                args["request_constraints"] = {
                    "strict_source_domains": list(constraints.strict_source_domains),
                    "soft_source_domains": list(constraints.soft_source_domains),
                }
                prepared.append(
                    ToolCallRequest(tool_name=req.tool_name, arguments=args),
                )
            else:
                prepared.append(req)

        return prepared, None

    @staticmethod
    def canonicalize_profile_update_fields(fields: dict) -> dict:
        out = copy.deepcopy(fields)
        for key in _PREF_BUCKET_KEYS:
            bucket = out.get(key)
            if not isinstance(bucket, dict):
                continue
            out[key] = ExecutionContextCore._canonicalize_pref_bucket(bucket)
        return out

    @staticmethod
    def _canonicalize_pref_bucket(bucket: dict) -> dict:
        result: dict[str, list[str]] = {}
        for skill, values in bucket.items():
            if skill == _LEGACY_WEB_SEARCH:
                continue
            result[skill] = list(values) if isinstance(values, list) else values

        if _LEGACY_WEB_SEARCH in bucket:
            legacy = list(bucket.get(_LEGACY_WEB_SEARCH) or [])
            canonical = list(result.get(_SEARCH_WEB) or [])
            result[_SEARCH_WEB] = ExecutionContextCore._dedupe_case_insensitive(
                canonical + legacy,
            )
        return result

    @staticmethod
    def _prepare_web_search(
        req: ToolCallRequest,
        strict: list[str],
        strict_set: set[str],
    ) -> ToolCallRequest | ProtocolIssue:
        args = dict(req.arguments)
        if not strict:
            return ToolCallRequest(tool_name=req.tool_name, arguments=args)

        provided = args.get("include_domains")
        if provided is None:
            args["include_domains"] = list(strict)
            return ToolCallRequest(tool_name=req.tool_name, arguments=args)

        if not isinstance(provided, list) or len(provided) == 0:
            return ProtocolIssue(
                stage=AgentPhase.EXECUTION,
                category=ProtocolIssueCategory.INVALID_CONSTRAINT,
            )

        try:
            normalized = [
                ExecutionContextCore.normalize_host(str(item)) for item in provided
            ]
        except ValueError:
            return ProtocolIssue(
                stage=AgentPhase.EXECUTION,
                category=ProtocolIssueCategory.INVALID_CONSTRAINT,
            )

        provided_set = {h.casefold() for h in normalized}
        if provided_set != strict_set:
            return ProtocolIssue(
                stage=AgentPhase.EXECUTION,
                category=ProtocolIssueCategory.INVALID_CONSTRAINT,
            )

        args["include_domains"] = list(strict)
        return ToolCallRequest(tool_name=req.tool_name, arguments=args)

    @staticmethod
    def _validate_web_extract(
        req: ToolCallRequest,
        strict: list[str],
    ) -> ProtocolIssue | None:
        urls = req.arguments.get("urls")
        if not isinstance(urls, list) or not urls:
            return ProtocolIssue(
                stage=AgentPhase.EXECUTION,
                category=ProtocolIssueCategory.INVALID_CONSTRAINT,
            )
        for url in urls:
            try:
                host = ExecutionContextCore.normalize_host(str(url))
            except ValueError:
                return ProtocolIssue(
                    stage=AgentPhase.EXECUTION,
                    category=ProtocolIssueCategory.INVALID_CONSTRAINT,
                )
            if not ExecutionContextCore._host_allowed(host, strict):
                return ProtocolIssue(
                    stage=AgentPhase.EXECUTION,
                    category=ProtocolIssueCategory.INVALID_CONSTRAINT,
                )
        return None

    @staticmethod
    def _host_allowed(host: str, allowed: list[str]) -> bool:
        host_cf = host.casefold()
        for base in allowed:
            base_cf = base.casefold()
            if host_cf == base_cf or host_cf.endswith(f".{base_cf}"):
                return True
        return False

    @staticmethod
    def _dedupe_case_insensitive(values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out

    @staticmethod
    def _is_dns_label(label: str) -> bool:
        if len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        return all(ch.isalnum() or ch == "-" for ch in label)
