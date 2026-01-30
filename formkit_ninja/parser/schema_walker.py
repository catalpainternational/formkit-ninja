"""
Schema traversal utilities for FormKit schemas.

This module provides SchemaWalker, a focused traversal helper used to collect
NodePath instances in a consistent order.
"""

from __future__ import annotations

from typing import List, Protocol, Union

from formkit_ninja.formkit_schema import FormKitSchema
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.type_convert import NodePath

SchemaInput = Union[List[dict], FormKitSchema]


class SchemaVisitor(Protocol):
    """Protocol for SchemaWalker visitors."""

    def on_node(self, node_path: NodePath) -> None:
        """Handle a NodePath during traversal."""


class SchemaWalker:
    """Traverse FormKit schemas and collect NodePath instances."""

    def __init__(self, config: GeneratorConfig) -> None:
        self.config = config

    def collect_nodepaths(
        self,
        schema: SchemaInput,
        *,
        abstract_base_info: dict[str, bool] | None = None,
    ) -> List[NodePath]:
        """Collect NodePath instances from a schema in pre-order."""
        nodepaths: List[NodePath] = []
        shared_abstract_info = abstract_base_info or {}

        schema_dicts: List[dict] = []
        if isinstance(schema, FormKitSchema):
            for node in schema.__root__:
                if isinstance(node, str):
                    continue
                schema_dicts.append(node.dict(exclude_none=True))
        else:
            schema_dicts = schema

        def traverse_node(node_dict: dict, parent_path: NodePath | None = None) -> None:
            temp_path = self.config.node_path_class.from_obj(node_dict)
            node = temp_path.node

            if parent_path is not None:
                node_path = parent_path / node
            else:
                node_path = self.config.node_path_class(node)

            node_path._config = self.config
            node_path._abstract_base_info = shared_abstract_info
            nodepaths.append(node_path)

            children = node_dict.get("children", [])
            if children:
                for child_dict in children:
                    if isinstance(child_dict, str):
                        continue
                    traverse_node(child_dict, node_path)

        for node_dict in schema_dicts:
            traverse_node(node_dict)

        return nodepaths

    def walk(self, schema: SchemaInput, visitor: SchemaVisitor) -> None:
        """Walk a schema and invoke visitor for each NodePath."""
        for node_path in self.collect_nodepaths(schema):
            visitor.on_node(node_path)
