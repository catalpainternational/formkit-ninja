"""
Main code generator orchestrator.

Composes all components to generate code from FormKit schemas.
"""

import json
from pathlib import Path
from typing import Dict, List, Union

from formkit_ninja.parser.type_convert import NodePath
from formkit_ninja.schemas import Schemas

from .processor import NodePathProcessor
from .python_generator import PythonGenerator
from .renderer import TemplateRenderer
from .writer import FileWriter


class CodeGenerator:
    """Main orchestrator - composes all components."""
    
    def __init__(self):
        """Initialize the code generator with all components."""
        self.processor = NodePathProcessor()
        self.renderer = TemplateRenderer()
        self.writer = FileWriter()
        self.python_generator = PythonGenerator(self.renderer, self.writer)
    
    def generate_from_schema(self, schema_dict: Dict, output_dir: Union[str, Path]) -> None:
        """
        Generate code from a single schema dictionary.
        
        Args:
            schema_dict: FormKit schema as dictionary
            output_dir: Directory to write generated files
        """
        output_dir = Path(output_dir)
        nodepaths = self.processor.process_schema(schema_dict)
        self.python_generator.generate_all(nodepaths, output_dir)
    
    def generate_from_schemas(self, schemas_dict: Dict[str, Dict], output_dir: Union[str, Path]) -> None:
        """
        Generate code from multiple schemas.
        
        Args:
            schemas_dict: Dictionary mapping schema names to schema dictionaries
            output_dir: Directory to write generated files
        """
        output_dir = Path(output_dir)
        nodepaths = self.processor.process_schemas(schemas_dict)
        self.python_generator.generate_all(nodepaths, output_dir)
    
    def generate_from_schema_file(self, file_path: Union[str, Path], output_dir: Union[str, Path]) -> None:
        """
        Generate code from a schema JSON file.
        
        Args:
            file_path: Path to the schema JSON file
            output_dir: Directory to write generated files
        """
        file_path = Path(file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            schema_dict = json.load(f)
        self.generate_from_schema(schema_dict, output_dir)
    
    def generate_from_database(self, schema_name: str, output_dir: Union[str, Path]) -> None:
        """
        Generate code from a schema stored in the database.
        
        Args:
            schema_name: Name of the schema in the database
            output_dir: Directory to write generated files
        """
        # TODO: Implement database loading when needed
        raise NotImplementedError("Database loading not implemented yet")
    
    def generate_from_existing_schemas(self, output_dir: Union[str, Path]) -> None:
        """
        Generate code from all existing schema files in formkit_ninja/schemas/.
        
        Args:
            output_dir: Directory to write generated files
        """
        schemas = Schemas()
        schemas_dict = {}
        
        for schema_name in schemas.list_schemas():
            schemas_dict[schema_name] = schemas.as_json(schema_name)
        
        self.generate_from_schemas(schemas_dict, output_dir)

