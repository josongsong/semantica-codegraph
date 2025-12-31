"""
Domain contracts for template parsing.
"""

from .template_ports import (
    SlotContextKind,
    EscapeMode,
    TemplateSlotContract,
    TemplateElementContract,
    TemplateDocContract,
    TemplateParserPort,
    TemplateLinkPort,
    TemplateQueryPort,
    TemplateParseError,
    TemplateLinkError,
    TemplateValidationError,
)

__all__ = [
    "SlotContextKind",
    "EscapeMode",
    "TemplateSlotContract",
    "TemplateElementContract",
    "TemplateDocContract",
    "TemplateParserPort",
    "TemplateLinkPort",
    "TemplateQueryPort",
    "TemplateParseError",
    "TemplateLinkError",
    "TemplateValidationError",
]
