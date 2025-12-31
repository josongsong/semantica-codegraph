"""
IR Generator Adapter

Multi-language IR generation for IRGeneratorPort.
"""

from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.models import ASTDocument, IRDocument
from codegraph_engine.code_foundation.domain.ports import IRGeneratorPort
from codegraph_engine.code_foundation.infrastructure.generators.base import IRGenerator as InfraIRGenerator
from codegraph_engine.code_foundation.infrastructure.generators.java_generator import _JavaIRGenerator
from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
from codegraph_engine.code_foundation.infrastructure.generators.typescript_generator import _TypeScriptIRGenerator
from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile

logger = get_logger(__name__)


class MultiLanguageIRGeneratorAdapter:
    """
    IRGeneratorPort adapter supporting multiple languages.

    Delegates to language-specific generators.
    """

    def __init__(self, repo_id: str = "default"):
        """
        Initialize adapter.

        Args:
            repo_id: Repository ID
        """
        self._repo_id = repo_id
        self._generators: dict[str, InfraIRGenerator] = {
            "python": _PythonIRGenerator(repo_id),
            "typescript": _TypeScriptIRGenerator(repo_id),
            "java": _JavaIRGenerator(repo_id),
        }

    def generate(self, ast_doc: ASTDocument) -> IRDocument:
        """
        Generate IR from AST.

        Args:
            ast_doc: AST document

        Returns:
            IRDocument

        Raises:
            ValueError: Language not supported or generation failed
        """
        lang = ast_doc.language.value
        generator = self._generators.get(lang)

        if generator is None:
            raise ValueError(
                f"Language not supported for IR generation: {lang}. Supported: {list(self._generators.keys())}"
            )

        # Create SourceFile wrapper
        source_file = SourceFile(
            file_path=ast_doc.file_path,
            content=ast_doc.source_code,
            language=lang,
        )

        try:
            # Generate IR (infrastructure model)
            infra_ir_doc = generator.generate(source_file, snapshot_id="default")

            # Convert to domain model
            return self._convert_to_domain_ir(infra_ir_doc)

        except Exception as e:
            logger.error("IR generation failed", language=lang, error=str(e))
            raise ValueError(f"IR generation failed for {lang}: {e}") from e

    def _convert_to_domain_ir(self, infra_ir: Any) -> IRDocument:
        """
        Convert infrastructure IRDocument to domain IRDocument.

        Args:
            infra_ir: Infrastructure IR model

        Returns:
            Domain IRDocument

        Note:
            This assumes IRDocument in domain and infrastructure are compatible.
            If not, add proper conversion logic here.
        """
        # FIXME: Check if domain.models.IRDocument and infrastructure.ir.models.IRDocument
        # are compatible. If not, add conversion logic.
        return infra_ir


def create_ir_generator_adapter(repo_id: str = "default") -> IRGeneratorPort:
    """Create production-grade IRGeneratorPort adapter."""
    return MultiLanguageIRGeneratorAdapter(repo_id)
