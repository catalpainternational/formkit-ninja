"""
NodePath processing component for code generation.

Converts schemas to NodePath objects for template rendering.
"""

from typing import Dict, List, Union

from formkit_ninja.parser.type_convert import NodePath


class NodePathProcessor:
    """Converts schemas to NodePath objects for template rendering."""
    
    def process_schema(self, schema_dict: Dict) -> List[NodePath]:
        """
        Convert a single schema dictionary to NodePath objects.
        
        Args:
            schema_dict: FormKit schema as dictionary
            
        Returns:
            List of NodePath objects
        """
        # Create NodePath from the schema
        root_node = NodePath.from_obj(schema_dict)
        
        # Collect all nodes (root and all children)
        all_nodes = []
        self._collect_all_nodes(root_node, all_nodes)
        
        return all_nodes
    
    def process_schemas(self, schemas_dict: Dict[str, Dict]) -> List[NodePath]:
        """
        Convert multiple schemas to NodePath objects.
        
        Args:
            schemas_dict: Dictionary mapping schema names to schema dictionaries
            
        Returns:
            List of all NodePath objects from all schemas
        """
        all_nodes = []
        
        for schema_name, schema_dict in schemas_dict.items():
            schema_nodes = self.process_schema(schema_dict)
            all_nodes.extend(schema_nodes)
        
        return all_nodes
    
    def _collect_all_nodes(self, node: NodePath, collected: List[NodePath]) -> None:
        """
        Recursively collect all nodes from a NodePath tree.
        
        Args:
            node: Current NodePath to process
            collected: List to collect nodes into
        """
        # Add current node if it's a group or repeater (models we want to generate)
        if node.is_group or node.is_repeater:
            collected.append(node)
        
        # Process children recursively
        for child in node.children:
            child_nodepath = node / child
            self._collect_all_nodes(child_nodepath, collected)
