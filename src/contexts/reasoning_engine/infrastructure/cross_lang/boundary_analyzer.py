"""
Service Boundary Analyzer (SOTA)

OpenAPI/Protobuf/GraphQL schema 기반 boundary 자동 추출

Features:
- OpenAPI 3.0/Swagger parsing
- Protobuf schema parsing
- GraphQL schema parsing
- REST endpoint detection
- gRPC method detection
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from .value_flow_graph import BoundarySpec, Confidence

logger = logging.getLogger(__name__)


class OpenAPIBoundaryExtractor:
    """
    OpenAPI/Swagger spec에서 boundary 추출

    Example:
        extractor = OpenAPIBoundaryExtractor()
        boundaries = extractor.extract_from_file("openapi.yaml")
    """

    def extract_from_file(self, spec_file: str) -> list[BoundarySpec]:
        """
        Extract boundaries from OpenAPI spec file

        Args:
            spec_file: Path to openapi.yaml or swagger.json

        Returns:
            List of BoundarySpec
        """
        logger.info(f"Extracting OpenAPI boundaries from {spec_file}")

        path = Path(spec_file)
        if not path.exists():
            logger.warning(f"OpenAPI spec not found: {spec_file}")
            return []

        # Parse YAML or JSON
        try:
            import yaml

            with open(path) as f:
                if path.suffix in [".yaml", ".yml"]:
                    spec = yaml.safe_load(f)
                else:
                    spec = json.load(f)
        except Exception as e:
            logger.error(f"Failed to parse OpenAPI spec: {e}")
            return []

        return self.extract_from_spec(spec)

    def extract_from_spec(self, spec: dict) -> list[BoundarySpec]:
        """
        Extract boundaries from OpenAPI spec dict

        Args:
            spec: OpenAPI spec dictionary

        Returns:
            List of BoundarySpec
        """
        boundaries = []

        # Get service name
        service_name = spec.get("info", {}).get("title", "unknown_service")

        # Get base path
        base_path = spec.get("basePath", "")

        # Parse paths
        paths = spec.get("paths", {})

        for endpoint, methods in paths.items():
            full_endpoint = base_path + endpoint

            for http_method, operation in methods.items():
                if http_method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    continue

                # Extract request schema
                request_schema = self._extract_request_schema(operation)

                # Extract response schema
                response_schema = self._extract_response_schema(operation)

                boundary = BoundarySpec(
                    boundary_type="rest_api",
                    service_name=service_name,
                    endpoint=full_endpoint,
                    request_schema=request_schema,
                    response_schema=response_schema,
                    http_method=http_method.upper(),
                    confidence=Confidence.HIGH,
                )

                boundaries.append(boundary)

        logger.info(f"Extracted {len(boundaries)} REST API boundaries")
        return boundaries

    def _extract_request_schema(self, operation: dict) -> dict[str, str]:
        """Extract request schema from operation"""
        schema = {}

        # Parameters (query, path, header)
        parameters = operation.get("parameters", [])
        for param in parameters:
            name = param.get("name")
            param_type = param.get("type", "string")
            if name:
                schema[name] = param_type

        # Request body (OpenAPI 3.0)
        request_body = operation.get("requestBody", {})
        content = request_body.get("content", {})

        # Try JSON content
        json_content = content.get("application/json", {})
        body_schema = json_content.get("schema", {})

        if body_schema:
            # Flatten schema properties
            properties = body_schema.get("properties", {})
            for name, prop in properties.items():
                prop_type = prop.get("type", "any")
                schema[name] = prop_type

        return schema

    def _extract_response_schema(self, operation: dict) -> dict[str, str]:
        """Extract response schema from operation"""
        schema = {}

        # Responses
        responses = operation.get("responses", {})

        # Try 200/201 response
        for status_code in ["200", "201", "default"]:
            response = responses.get(status_code)
            if not response:
                continue

            # OpenAPI 3.0
            content = response.get("content", {})
            json_content = content.get("application/json", {})
            response_schema = json_content.get("schema", {})

            if response_schema:
                properties = response_schema.get("properties", {})
                for name, prop in properties.items():
                    prop_type = prop.get("type", "any")
                    schema[name] = prop_type
                break

        return schema


class ProtobufBoundaryExtractor:
    """
    Protobuf schema에서 boundary 추출

    Parses .proto files to extract gRPC service definitions
    """

    def extract_from_file(self, proto_file: str) -> list[BoundarySpec]:
        """
        Extract boundaries from .proto file

        Args:
            proto_file: Path to .proto file

        Returns:
            List of BoundarySpec
        """
        logger.info(f"Extracting Protobuf boundaries from {proto_file}")

        path = Path(proto_file)
        if not path.exists():
            logger.warning(f"Proto file not found: {proto_file}")
            return []

        content = path.read_text(encoding="utf-8")
        return self.extract_from_content(content)

    def extract_from_content(self, content: str) -> list[BoundarySpec]:
        """
        Parse .proto content

        Args:
            content: .proto file content

        Returns:
            List of BoundarySpec
        """
        boundaries = []

        # Parse service definitions
        # Pattern: service ServiceName { ... }
        service_pattern = r"service\s+(\w+)\s*\{([^}]+)\}"

        for match in re.finditer(service_pattern, content, re.DOTALL):
            service_name = match.group(1)
            service_body = match.group(2)

            # Parse RPC methods
            # Pattern: rpc MethodName (RequestType) returns (ResponseType);
            rpc_pattern = r"rpc\s+(\w+)\s*\(\s*(\w+)\s*\)\s*returns\s*\(\s*(\w+)\s*\)"

            for rpc_match in re.finditer(rpc_pattern, service_body):
                method_name = rpc_match.group(1)
                request_type = rpc_match.group(2)
                response_type = rpc_match.group(3)

                # Extract message schemas
                request_schema = self._extract_message_schema(content, request_type)
                response_schema = self._extract_message_schema(content, response_type)

                boundary = BoundarySpec(
                    boundary_type="grpc",
                    service_name=service_name,
                    endpoint=method_name,
                    request_schema=request_schema,
                    response_schema=response_schema,
                    grpc_method=method_name,
                    confidence=Confidence.HIGH,
                )

                boundaries.append(boundary)

        logger.info(f"Extracted {len(boundaries)} gRPC boundaries")
        return boundaries

    def _extract_message_schema(self, content: str, message_name: str) -> dict[str, str]:
        """
        Extract message schema from proto content

        Args:
            content: Full .proto content
            message_name: Message type name

        Returns:
            {field_name: type}
        """
        schema = {}

        # Pattern: message MessageName { ... }
        message_pattern = rf"message\s+{message_name}\s*\{{([^}}]+)\}}"

        match = re.search(message_pattern, content, re.DOTALL)
        if not match:
            return schema

        message_body = match.group(1)

        # Parse fields
        # Pattern: type field_name = number;
        field_pattern = r"(\w+)\s+(\w+)\s*=\s*\d+"

        for field_match in re.finditer(field_pattern, message_body):
            field_type = field_match.group(1)
            field_name = field_match.group(2)

            # Map proto types to generic types
            type_map = {
                "string": "string",
                "int32": "int",
                "int64": "int",
                "bool": "bool",
                "double": "float",
                "float": "float",
                "bytes": "bytes",
            }

            generic_type = type_map.get(field_type, field_type)
            schema[field_name] = generic_type

        return schema


class GraphQLBoundaryExtractor:
    """
    GraphQL schema에서 boundary 추출
    """

    def extract_from_file(self, schema_file: str) -> list[BoundarySpec]:
        """
        Extract boundaries from GraphQL schema file

        Args:
            schema_file: Path to schema.graphql

        Returns:
            List of BoundarySpec
        """
        logger.info(f"Extracting GraphQL boundaries from {schema_file}")

        path = Path(schema_file)
        if not path.exists():
            logger.warning(f"GraphQL schema not found: {schema_file}")
            return []

        content = path.read_text(encoding="utf-8")
        return self.extract_from_content(content)

    def extract_from_content(self, content: str) -> list[BoundarySpec]:
        """
        Parse GraphQL schema content

        Args:
            content: GraphQL schema content

        Returns:
            List of BoundarySpec
        """
        boundaries = []

        # Parse Query type
        query_boundaries = self._extract_type_boundaries(content, "Query", "graphql_query")
        boundaries.extend(query_boundaries)

        # Parse Mutation type
        mutation_boundaries = self._extract_type_boundaries(content, "Mutation", "graphql_mutation")
        boundaries.extend(mutation_boundaries)

        logger.info(f"Extracted {len(boundaries)} GraphQL boundaries")
        return boundaries

    def _extract_type_boundaries(self, content: str, type_name: str, boundary_type: str) -> list[BoundarySpec]:
        """Extract boundaries from Query or Mutation type"""
        boundaries = []

        # Pattern: type TypeName { ... }
        type_pattern = rf"type\s+{type_name}\s*\{{([^}}]+)\}}"

        match = re.search(type_pattern, content, re.DOTALL)
        if not match:
            return boundaries

        type_body = match.group(1)

        # Parse fields
        # Pattern: fieldName(arg1: Type1, arg2: Type2): ReturnType
        field_pattern = r"(\w+)\s*(\([^)]*\))?\s*:\s*(\w+)"

        for field_match in re.finditer(field_pattern, type_body):
            field_name = field_match.group(1)
            args_str = field_match.group(2) or "()"
            return_type = field_match.group(3)

            # Parse arguments
            request_schema = self._parse_args(args_str)

            # Response schema
            response_schema = {"result": return_type}

            boundary = BoundarySpec(
                boundary_type="graphql",
                service_name="graphql_service",
                endpoint=field_name,
                request_schema=request_schema,
                response_schema=response_schema,
                graphql_type=type_name,
                confidence=Confidence.HIGH,
            )

            boundaries.append(boundary)

        return boundaries

    def _parse_args(self, args_str: str) -> dict[str, str]:
        """Parse GraphQL arguments"""
        schema = {}

        # Remove parentheses
        args_str = args_str.strip("()")

        if not args_str:
            return schema

        # Pattern: argName: Type
        arg_pattern = r"(\w+)\s*:\s*(\w+)"

        for arg_match in re.finditer(arg_pattern, args_str):
            arg_name = arg_match.group(1)
            arg_type = arg_match.group(2)
            schema[arg_name] = arg_type

        return schema


class BoundaryAnalyzer:
    """
    Unified boundary analyzer

    Supports OpenAPI, Protobuf, GraphQL

    Example:
        analyzer = BoundaryAnalyzer(workspace_root="/path/to/project")
        boundaries = analyzer.discover_all()
    """

    def __init__(self, workspace_root: str):
        """
        Initialize boundary analyzer

        Args:
            workspace_root: Project root directory
        """
        self.workspace_root = Path(workspace_root)

        self.openapi_extractor = OpenAPIBoundaryExtractor()
        self.protobuf_extractor = ProtobufBoundaryExtractor()
        self.graphql_extractor = GraphQLBoundaryExtractor()

        logger.info(f"BoundaryAnalyzer initialized: {workspace_root}")

    def discover_all(self) -> list[BoundarySpec]:
        """
        Auto-discover all boundaries in workspace

        Scans for:
        - openapi.yaml, swagger.json
        - *.proto files
        - schema.graphql

        Returns:
            List of BoundarySpec
        """
        logger.info("Auto-discovering service boundaries...")

        all_boundaries = []

        # Find OpenAPI specs
        openapi_files = list(self.workspace_root.rglob("openapi.yaml"))
        openapi_files.extend(self.workspace_root.rglob("openapi.yml"))
        openapi_files.extend(self.workspace_root.rglob("swagger.json"))

        for spec_file in openapi_files:
            boundaries = self.openapi_extractor.extract_from_file(str(spec_file))
            all_boundaries.extend(boundaries)

        # Find Protobuf files
        proto_files = list(self.workspace_root.rglob("*.proto"))

        for proto_file in proto_files:
            boundaries = self.protobuf_extractor.extract_from_file(str(proto_file))
            all_boundaries.extend(boundaries)

        # Find GraphQL schemas
        graphql_files = list(self.workspace_root.rglob("schema.graphql"))
        graphql_files.extend(self.workspace_root.rglob("*.graphql"))

        for schema_file in graphql_files:
            boundaries = self.graphql_extractor.extract_from_file(str(schema_file))
            all_boundaries.extend(boundaries)

        logger.info(f"Discovered {len(all_boundaries)} service boundaries")
        return all_boundaries

    def match_boundary_to_code(self, boundary: BoundarySpec, ir_documents: list[Any]) -> tuple[str | None, str | None]:
        """
        Match boundary to actual code locations

        Finds:
        - Server implementation (handler/controller)
        - Client call site

        Args:
            boundary: BoundarySpec
            ir_documents: List of IRDocument (from code foundation)

        Returns:
            (server_file, client_file)
        """
        server_file = None
        client_file = None

        # Heuristic matching
        endpoint_name = boundary.endpoint.strip("/").replace("/", "_")

        for ir_doc in ir_documents:
            file_path = ir_doc.file_path

            # Check if file contains handler/controller
            if any(keyword in file_path.lower() for keyword in ["handler", "controller", "api", "route"]):
                # Check if function name matches endpoint
                for node in ir_doc.nodes:
                    if endpoint_name.lower() in node.name.lower():
                        server_file = file_path
                        break

            # Check if file contains client calls
            if any(keyword in file_path.lower() for keyword in ["client", "service", "api"]):
                # Check for HTTP/gRPC client usage
                for node in ir_doc.nodes:
                    if endpoint_name.lower() in node.name.lower():
                        client_file = file_path

        return server_file, client_file
