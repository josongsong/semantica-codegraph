"""
Overload Resolution Analyzer

오버로드된 함수의 정확한 타겟 결정
"""

from dataclasses import dataclass


@dataclass
class OverloadCandidate:
    """오버로드 후보"""

    function_id: str
    function_name: str
    param_types: list[str]
    return_type: str | None
    is_overload: bool


@dataclass
class CallSiteResolution:
    """호출 지점 resolution 결과"""

    call_location: str
    candidates: list[OverloadCandidate]
    resolved: OverloadCandidate | None
    reason: str


class OverloadResolver:
    """
    Overload Resolution

    기능:
    - @overload decorator가 있는 함수 그룹 찾기
    - 호출 지점의 argument types 추론
    - 가장 적합한 overload 선택
    """

    def __init__(self):
        self._overload_groups: dict[str, list[OverloadCandidate]] = {}

    def register_overloads(self, nodes: list[any]):
        """오버로드 함수들을 그룹화"""
        self._overload_groups.clear()

        for node in nodes:
            if not hasattr(node, "name") or not hasattr(node, "attrs"):
                continue

            decorators = node.attrs.get("decorators", [])

            # @overload가 있거나, 같은 이름의 함수가 여러 개면 overload
            if "overload" in decorators or self._is_potential_overload(node, nodes):
                func_name = node.name

                # Extract param types
                param_types = self._extract_param_types(node)
                return_type = self._extract_return_type(node)

                candidate = OverloadCandidate(
                    function_id=node.id,
                    function_name=func_name,
                    param_types=param_types,
                    return_type=return_type,
                    is_overload="overload" in decorators,
                )

                if func_name not in self._overload_groups:
                    self._overload_groups[func_name] = []
                self._overload_groups[func_name].append(candidate)

    def resolve_call(
        self,
        function_name: str,
        arg_types: list[str],
        call_location: str = "",
    ) -> CallSiteResolution:
        """
        호출 지점에서 정확한 overload 결정

        Args:
            function_name: 호출된 함수 이름
            arg_types: 인자 타입들 (추론된 것)
            call_location: 호출 위치

        Returns:
            Resolution 결과
        """
        candidates = self._overload_groups.get(function_name, [])

        if not candidates:
            return CallSiteResolution(
                call_location=call_location, candidates=[], resolved=None, reason="No overloads found"
            )

        if len(candidates) == 1:
            return CallSiteResolution(
                call_location=call_location, candidates=candidates, resolved=candidates[0], reason="Only one candidate"
            )

        # Try exact match
        for candidate in candidates:
            if self._types_match(arg_types, candidate.param_types):
                return CallSiteResolution(
                    call_location=call_location, candidates=candidates, resolved=candidate, reason="Exact type match"
                )

        # Try compatible match
        for candidate in candidates:
            if self._types_compatible(arg_types, candidate.param_types):
                return CallSiteResolution(
                    call_location=call_location, candidates=candidates, resolved=candidate, reason="Compatible types"
                )

        # Return first non-overload (implementation)
        for candidate in candidates:
            if not candidate.is_overload:
                return CallSiteResolution(
                    call_location=call_location,
                    candidates=candidates,
                    resolved=candidate,
                    reason="Fallback to implementation",
                )

        # No clear resolution
        return CallSiteResolution(
            call_location=call_location, candidates=candidates, resolved=None, reason="Ambiguous overload"
        )

    def _is_potential_overload(self, node: any, all_nodes: list[any]) -> bool:
        """같은 이름의 함수가 여러 개인지 체크"""
        if not hasattr(node, "name"):
            return False

        same_name_count = sum(1 for n in all_nodes if hasattr(n, "name") and n.name == node.name and n.id != node.id)

        return same_name_count > 0

    def _extract_param_types(self, node: any) -> list[str]:
        """함수 노드에서 parameter types 추출"""
        # Would need to access signature/parameter info
        # For now, return empty list
        return []

    def _extract_return_type(self, node: any) -> str | None:
        """함수 노드에서 return type 추출"""
        # Would need to access signature info
        return None

    def _types_match(self, arg_types: list[str], param_types: list[str]) -> bool:
        """타입이 정확히 일치하는지"""
        if len(arg_types) != len(param_types):
            return False

        for arg_type, param_type in zip(arg_types, param_types, strict=False):
            if arg_type != param_type:
                return False

        return True

    def _types_compatible(self, arg_types: list[str], param_types: list[str]) -> bool:
        """타입이 호환 가능한지 (subtype 등)"""
        if len(arg_types) != len(param_types):
            return False

        # Simple compatibility check
        # In production, would need full type hierarchy
        for arg_type, param_type in zip(arg_types, param_types, strict=False):
            if arg_type == param_type:
                continue
            if param_type == "Any":
                continue
            if arg_type in param_type or param_type in arg_type:
                continue
            return False

        return True

    def get_overload_groups(self) -> dict[str, list[OverloadCandidate]]:
        """모든 overload 그룹 조회"""
        return self._overload_groups.copy()

    def has_overloads(self, function_name: str) -> bool:
        """함수가 오버로드되어 있는지"""
        return function_name in self._overload_groups and len(self._overload_groups[function_name]) > 1
