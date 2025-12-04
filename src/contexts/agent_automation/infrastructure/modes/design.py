"""
Design Mode

Generates architecture and implementation plans for complex tasks.

Features:
- Requirement analysis
- Complexity assessment
- Architecture design
- Implementation planning
- Testing strategy
- Design documentation
"""

import json
from typing import TYPE_CHECKING, Any

from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.symbol_graph.models import SymbolGraph
from src.common.observability import get_logger

logger = get_logger(__name__)


@mode_registry.register(AgentMode.DESIGN)
class DesignMode(BaseModeHandler):
    """
    Design mode for architecture design and implementation planning.

    Flow:
    1. Analyze requirements and assess complexity
    2. Understand existing structure (via Semantica Graph if available)
    3. Generate architecture design (LLM or template-based)
    4. Create implementation plan
    5. Define testing strategy
    6. Generate design document

    Transitions:
    - design_approved → IMPLEMENTATION (simple design)
    - design_approved → MULTI_FILE_EDITING (complex, multi-file design)
    """

    def __init__(self, llm_client=None, graph_client=None):
        """
        Initialize Design mode.

        Args:
            llm_client: Optional LLM client for AI-powered design generation
            graph_client: Optional Semantica Graph client for structure analysis
        """
        super().__init__(AgentMode.DESIGN)
        self.llm = llm_client
        self.graph = graph_client

    async def enter(self, context: ModeContext) -> None:
        """Enter design mode."""
        await super().enter(context)
        self.logger.info(f"🎨 Design mode: {context.current_task}")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute design mode.

        Args:
            task: Design task with requirements
            context: Shared mode context

        Returns:
            Result with design, implementation plan, and testing strategy
        """
        self.logger.info(f"Designing: {task.query}")

        # 1. Analyze requirements
        requirements = self._analyze_requirements(task)
        complexity = self._assess_complexity(requirements)

        # 2. Get existing structure
        existing_structure = await self._get_existing_structure(context)

        # 3. Generate design (LLM or template)
        design = await self._generate_design(requirements, existing_structure, complexity)

        # 4. Create implementation plan
        implementation_plan = self._create_implementation_plan(design)

        # 5. Create testing strategy
        testing_strategy = self._create_testing_strategy(design)

        # 6. Generate design document
        design_doc = self._create_design_document(design, implementation_plan, testing_strategy)

        # 7. Update context
        context.current_task = design["summary"]
        for component in design["architecture"]["components"]:
            context.add_file(component["file"])

        return self._create_result(
            data={
                "design": design,
                "implementation_plan": implementation_plan,
                "testing_strategy": testing_strategy,
                "document": design_doc,
                "complexity": complexity,
            },
            trigger="design_approved",  # Trigger transition to IMPLEMENTATION
            explanation=f"Design: {len(design['architecture']['components'])} components, "
            f"{len(implementation_plan)} steps",
        )

    def _analyze_requirements(self, task: Task) -> dict[str, Any]:
        """
        Analyze requirements from task query.

        Args:
            task: Task with user query

        Returns:
            Dictionary with functional/non-functional requirements
        """
        query = task.query.lower()

        requirements = {"functional": [], "non_functional": [], "constraints": []}

        # Functional requirements (keyword-based analysis)
        functional_keywords = {
            "add": "새 기능 추가",
            "create": "새 기능 추가",
            "authentication": "인증 시스템",
            "auth": "인증 시스템",
            "login": "로그인 기능",
            "payment": "결제 처리",
            "notification": "알림 시스템",
            "api": "API 엔드포인트",
            "database": "데이터베이스 연동",
            "user": "사용자 관리",
        }

        for keyword, req in functional_keywords.items():
            if keyword in query:
                if req not in requirements["functional"]:
                    requirements["functional"].append(req)

        # Non-functional requirements
        non_functional_keywords = {
            "secure": "보안",
            "security": "보안",
            "performance": "성능",
            "fast": "성능",
            "scalable": "확장성",
            "reliable": "안정성",
            "real-time": "실시간 처리",
        }

        for keyword, req in non_functional_keywords.items():
            if keyword in query:
                if req not in requirements["non_functional"]:
                    requirements["non_functional"].append(req)

        # Ensure at least one functional requirement
        if not requirements["functional"]:
            requirements["functional"].append("기능 구현")

        return requirements

    def _assess_complexity(self, requirements: dict) -> str:
        """
        Assess complexity based on requirements.

        Args:
            requirements: Requirements dictionary

        Returns:
            "low", "medium", or "high"
        """
        functional_count = len(requirements["functional"])
        non_functional_count = len(requirements["non_functional"])
        total = functional_count + non_functional_count

        if total <= 2:
            return "low"
        elif total <= 5:
            return "medium"
        else:
            return "high"

    async def _get_existing_structure(self, context: ModeContext) -> dict:
        """
        Get existing code structure from context and Semantica Graph.

        Args:
            context: Mode context with current files/symbols

        Returns:
            Dictionary with existing structure info including:
            - files: Current working files
            - symbols: Current symbols (classes, functions)
            - dependencies: Import/call relationships
            - patterns: Detected architectural patterns
        """
        structure = {
            "files": context.current_files,
            "symbols": context.current_symbols,
            "dependencies": [],
            "patterns": [],
            "classes": [],
            "functions": [],
            "imports": [],
        }

        # Integrate with Semantica Graph API
        if self.graph:
            try:
                graph = self.graph
                from src.contexts.code_foundation.infrastructure.symbol_graph.models import RelationKind, SymbolKind

                # Extract classes
                classes = graph.get_symbols_by_kind(SymbolKind.CLASS)
                structure["classes"] = [
                    {"name": c.name, "fqn": c.fqn, "file": c.span.start_line if c.span else None}
                    for c in classes[:20]  # Limit for performance
                ]

                # Extract functions
                functions = graph.get_symbols_by_kind(SymbolKind.FUNCTION)
                methods = graph.get_symbols_by_kind(SymbolKind.METHOD)
                structure["functions"] = [{"name": f.name, "fqn": f.fqn} for f in (functions + methods)[:30]]

                # Extract import relationships
                import_relations = graph.get_relations_by_kind(RelationKind.IMPORTS)
                structure["imports"] = [
                    {
                        "from": graph.get_symbol(r.source_id).fqn if graph.get_symbol(r.source_id) else r.source_id,
                        "to": graph.get_symbol(r.target_id).fqn if graph.get_symbol(r.target_id) else r.target_id,
                    }
                    for r in import_relations[:20]
                ]

                # Extract call dependencies
                call_relations = graph.get_relations_by_kind(RelationKind.CALLS)
                structure["dependencies"] = [
                    {
                        "caller": graph.get_symbol(r.source_id).name if graph.get_symbol(r.source_id) else r.source_id,
                        "callee": graph.get_symbol(r.target_id).name if graph.get_symbol(r.target_id) else r.target_id,
                    }
                    for r in call_relations[:30]
                ]

                # Detect patterns (inheritance)
                inheritance_relations = graph.get_relations_by_kind(RelationKind.INHERITS)
                if inheritance_relations:
                    structure["patterns"].append(
                        {
                            "type": "inheritance",
                            "count": len(inheritance_relations),
                            "examples": [self._format_inheritance(graph, r) for r in inheritance_relations[:5]],
                        }
                    )

                self.logger.debug(
                    f"Graph analysis: {len(structure['classes'])} classes, "
                    f"{len(structure['functions'])} functions, "
                    f"{len(structure['dependencies'])} dependencies"
                )

            except Exception as e:
                self.logger.warning(f"Failed to analyze graph structure: {e}")

        return structure

    def _format_inheritance(self, graph: "SymbolGraph", r: Any) -> str:
        """Format inheritance relationship for display."""
        source = graph.get_symbol(r.source_id)
        target = graph.get_symbol(r.target_id)
        source_name = source.name if source else "?"
        target_name = target.name if target else "?"
        return f"{source_name} extends {target_name}"

    async def _generate_design(self, requirements: dict, existing_structure: dict, complexity: str) -> dict:
        """
        Generate architecture design.

        Args:
            requirements: Requirements dictionary
            existing_structure: Existing code structure
            complexity: Complexity level

        Returns:
            Design dictionary with architecture, components, etc.
        """
        if self.llm:
            # Try LLM-based design generation
            try:
                return await self._generate_design_with_llm(requirements, existing_structure, complexity)
            except Exception as e:
                self.logger.warning(f"LLM design generation failed: {e}, using template")

        # Fallback: Template-based design
        return self._create_template_design(requirements, complexity)

    async def _generate_design_with_llm(self, requirements: dict, existing_structure: dict, complexity: str) -> dict:
        """
        Generate design using LLM.

        Args:
            requirements: Requirements dictionary
            existing_structure: Existing structure
            complexity: Complexity level

        Returns:
            Design dictionary
        """
        if self.llm is None:
            return {}

        prompt = self._build_design_prompt(requirements, existing_structure, complexity)

        response = await self.llm.complete(
            messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=2000
        )

        content = response.get("content", "{}")

        # Parse JSON from response
        try:
            # Try to extract JSON from markdown code blocks
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            else:
                json_str = content

            design = json.loads(json_str)
            return design

        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"Failed to parse LLM response as JSON: {e}")
            raise RuntimeError("LLM response is not valid JSON") from e

    def _build_design_prompt(self, requirements: dict, existing_structure: dict, complexity: str) -> str:
        """Build LLM prompt for design generation."""
        prompt = f"""You are a senior software architect. Design a solution for the following requirements:

Requirements:
- Functional: {", ".join(requirements["functional"])}
- Non-functional: {", ".join(requirements["non_functional"]) if requirements["non_functional"] else "None"}

Existing Structure:
- Files: {existing_structure["files"] if existing_structure["files"] else "None"}
- Symbols: {existing_structure["symbols"] if existing_structure["symbols"] else "None"}

Complexity: {complexity}

Provide a design with:
1. Architecture components (classes/modules)
2. Data flow
3. Implementation steps (ordered)
4. Potential risks and mitigations

Return ONLY valid JSON in this exact format:
{{
    "summary": "Brief design summary",
    "architecture": {{
        "components": [
            {{
                "name": "ComponentName",
                "file": "src/path/to/file.py",
                "responsibilities": ["Responsibility 1", "Responsibility 2"]
            }}
        ],
        "data_flow": "Brief description of data flow",
        "dependencies": ["dependency1", "dependency2"]
    }},
    "implementation_plan": [
        {{
            "step": 1,
            "action": "Create component",
            "file": "src/path/to/file.py",
            "estimated_lines": 100
        }}
    ],
    "risks": [
        {{
            "risk": "Risk description",
            "mitigation": "Mitigation strategy"
        }}
    ]
}}
"""
        return prompt

    def _create_template_design(self, requirements: dict, complexity: str) -> dict:
        """
        Create template-based design (fallback).

        Args:
            requirements: Requirements dictionary
            complexity: Complexity level

        Returns:
            Design dictionary
        """
        component_name = "MainComponent"
        if requirements["functional"]:
            # Use first requirement for naming
            first_req = requirements["functional"][0]
            if "인증" in first_req or "auth" in first_req.lower():
                component_name = "AuthService"
            elif "결제" in first_req or "payment" in first_req.lower():
                component_name = "PaymentService"
            elif "알림" in first_req or "notification" in first_req.lower():
                component_name = "NotificationService"
            elif "API" in first_req:
                component_name = "APIHandler"

        return {
            "summary": f"Design for {', '.join(requirements['functional'])}",
            "architecture": {
                "components": [
                    {
                        "name": component_name,
                        "file": f"src/{component_name.lower()}.py",
                        "responsibilities": requirements["functional"],
                    }
                ],
                "data_flow": "Input → Process → Output",
                "dependencies": [],
            },
            "implementation_plan": [
                {
                    "step": 1,
                    "action": f"Create {component_name}",
                    "file": f"src/{component_name.lower()}.py",
                    "estimated_lines": 100,
                }
            ],
            "risks": [],
        }

    def _create_implementation_plan(self, design: dict) -> list[dict]:
        """
        Create implementation plan from design.

        Args:
            design: Design dictionary

        Returns:
            List of implementation steps
        """
        # If design already has implementation_plan, use it
        if "implementation_plan" in design and design["implementation_plan"]:
            return design["implementation_plan"]

        # Otherwise, generate from components
        plan = []
        for i, component in enumerate(design["architecture"]["components"]):
            plan.append(
                {
                    "step": i + 1,
                    "action": f"Implement {component['name']}",
                    "file": component["file"],
                    "estimated_lines": 100,
                }
            )

        return plan

    def _create_testing_strategy(self, design: dict) -> dict:
        """
        Create testing strategy from design.

        Args:
            design: Design dictionary

        Returns:
            Testing strategy dictionary
        """
        if "testing_strategy" in design:
            return design["testing_strategy"]

        components = design["architecture"]["components"]

        return {
            "unit_tests": [f"test_{c['name'].lower()}" for c in components],
            "integration_tests": ["test_integration"],
            "e2e_tests": ["test_e2e_flow"],
        }

    def _create_design_document(self, design: dict, implementation_plan: list, testing_strategy: dict) -> str:
        """
        Generate design document in Markdown format.

        Args:
            design: Design dictionary
            implementation_plan: Implementation plan
            testing_strategy: Testing strategy

        Returns:
            Markdown document string
        """
        doc = f"""# Design Document

## Summary
{design["summary"]}

## Architecture

### Components
"""
        for comp in design["architecture"]["components"]:
            doc += f"- **{comp['name']}** ([{comp['file']}]({comp['file']}))\n"
            responsibilities = comp.get("responsibilities", [])
            if responsibilities:
                doc += f"  - {', '.join(responsibilities)}\n"

        doc += f"""
### Data Flow
{design["architecture"]["data_flow"]}

### Dependencies
{", ".join(design["architecture"].get("dependencies", [])) or "None"}

## Implementation Plan
"""
        for step in implementation_plan:
            doc += f"{step['step']}. {step['action']} ([{step['file']}]({step['file']}))\n"

        doc += """
## Testing Strategy
"""
        doc += f"- **Unit Tests**: {', '.join(testing_strategy['unit_tests'])}\n"
        doc += f"- **Integration Tests**: {', '.join(testing_strategy['integration_tests'])}\n"

        if "e2e_tests" in testing_strategy:
            doc += f"- **E2E Tests**: {', '.join(testing_strategy['e2e_tests'])}\n"

        if design.get("risks"):
            doc += """
## Risks & Mitigations
"""
            for risk in design["risks"]:
                doc += f"- **Risk**: {risk['risk']}\n"
                doc += f"  - **Mitigation**: {risk.get('mitigation', 'TBD')}\n"

        return doc

    async def exit(self, context: ModeContext) -> None:
        """Exit design mode."""
        self.logger.info("Design mode complete")
        await super().exit(context)
