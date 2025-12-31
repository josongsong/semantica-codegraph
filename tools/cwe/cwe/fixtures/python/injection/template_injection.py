"""
Template Injection Test Fixtures (SSTI)

Real-world Server-Side Template Injection vulnerabilities
Focuses on Jinja2 (Flask), Mako, Tornado
"""

from flask import render_template_string
from jinja2 import Template as Jinja2Template
from mako.template import Template as MakoTemplate


def template_injection_vulnerable_1(user_input):
    """
    VULNERABLE: Flask SSTI - Classic RCE

    Real attack: user_input = "{{config.items()}}"
    Result: Leaks Flask config (SECRET_KEY, etc.)

    Critical attack: "{{''.__class__.__mro__[1].__subclasses__()[396]('cat /etc/passwd',shell=True,stdout=-1).communicate()}}"
    Result: Remote Code Execution
    """
    # VULNERABLE: Direct template rendering
    template = f"Hello {user_input}!"

    result = render_template_string(template)  # SINK: SSTI
    return result


def template_injection_vulnerable_2(name):
    """
    VULNERABLE: Jinja2 direct template injection

    Real attack: name = "{{7*7}}"
    Result: Renders "49" - proves code execution
    """
    # VULNERABLE
    template = Jinja2Template(f"Welcome, {name}!")  # SINK: jinja2.from_string equivalent

    result = template.render()
    return result


def template_injection_vulnerable_3(user_template):
    """
    VULNERABLE: User-controlled template

    Real attack: user_template = "{{''.__class__}}"
    Result: Accesses Python internals
    """
    # VULNERABLE: Entire template from user
    template = Jinja2Template(user_template)  # SINK: jinja2 template

    result = template.render(data="test")
    return result


def template_injection_vulnerable_4(user_content):
    """
    VULNERABLE: Mako SSTI

    Real attack: user_content = "${open('/etc/passwd').read()}"
    Result: File read via template execution
    """
    # VULNERABLE
    template = MakoTemplate(f"<div>{user_content}</div>")  # SINK: mako.template

    result = template.render()
    return result


def template_injection_vulnerable_5(greeting):
    """
    VULNERABLE: Tornado template injection

    Real attack: greeting = "{% import os %}{{os.system('ls')}}"
    Result: Command execution
    """
    from tornado.template import Template as TornadoTemplate

    # VULNERABLE
    template = TornadoTemplate(f"<h1>{greeting}</h1>")  # SINK: tornado.template

    result = template.generate()
    return result


def template_injection_safe_1(user_input):
    """
    SAFE: Pre-compiled template with autoescape
    """
    from jinja2 import Environment, select_autoescape

    env = Environment(autoescape=select_autoescape(["html", "xml"]))

    # SAFE: Pre-defined template, user_input only as variable
    template = env.from_string("Hello {{ name }}!")

    result = template.render(name=user_input)  # SAFE: autoescape enabled
    return result


def template_injection_safe_2(user_input):
    """
    SAFE: Manual escaping
    """
    from markupsafe import escape

    # SAFE: Escaped
    safe_input = escape(user_input)

    template = f"Hello {safe_input}!"
    # Note: Still risky to use render_template_string, but input is escaped

    return template


def template_injection_safe_3(user_input):
    """
    SAFE: Using sanitizer
    """
    # SAFE: Sanitized
    clean_input = escape_template(user_input)

    result = render_template_string(f"Hello {clean_input}!")
    return result


# Helpers


def escape_template(value):
    """Template sanitizer"""
    # Remove dangerous template syntax
    dangerous = ["{", "}", "[", "]", "%", "$", "\\"]
    for char in dangerous:
        value = value.replace(char, "")
    return value
