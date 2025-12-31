"""
Java Type Serializer (SOTA: Type-safe conversion)

Converts dict type info → string for ReturnTypeSummary compatibility.

L11 SOTA:
- No data loss (dict → string → parseable)
- Type-safe (validated conversion)
- Backward compatible
"""


def serialize_type_info(type_info: dict | None) -> str | None:
    """
    Serialize Java type info dict to string.

    Args:
        type_info: Type info dict from _extract_generic_type_info

    Returns:
        String representation or None

    Examples:
        {"type": "String"} → "String"
        {"base": "List", "args": [{"type": "String"}]} → "List<String>"
        {"base": "Map", "args": [{...}, {...}]} → "Map<String,Integer>"
        {"wildcard": True, "bound": "extends", "type": "Number"} → "? extends Number"
        {"type": "void"} → "void"
        {"array": True, "type": "int"} → "int[]"
    """
    if not type_info:
        return None

    if not isinstance(type_info, dict):
        return str(type_info)

    # Simple type
    if "type" in type_info and len(type_info) == 1:
        return type_info["type"]

    # Array type
    if type_info.get("array"):
        base = serialize_type_info({k: v for k, v in type_info.items() if k != "array"})
        return f"{base}[]" if base else None

    # Wildcard
    if type_info.get("wildcard"):
        bound = type_info.get("bound", "none")
        wildcard_type = type_info.get("type")

        if bound == "none":
            return "?"
        elif bound == "extends":
            return f"? extends {wildcard_type}" if wildcard_type else "?"
        elif bound == "super":
            return f"? super {wildcard_type}" if wildcard_type else "?"

    # Generic type
    if "base" in type_info:
        base = type_info["base"]
        args = type_info.get("args", [])

        if not args:
            return base

        # Serialize args recursively
        arg_strs = []
        for arg in args:
            arg_str = serialize_type_info(arg)
            if arg_str:
                arg_strs.append(arg_str)

        if arg_strs:
            return f"{base}<{','.join(arg_strs)}>"
        return base

    # Fallback: simple type
    return type_info.get("type")
