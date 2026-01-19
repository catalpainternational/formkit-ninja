"""
Python code generator component.

Generates Python files using TemplateRenderer + FileWriter.
"""

from pathlib import Path
from typing import List

from formkit_ninja.parser.type_convert import NodePath

from .renderer import TemplateRenderer
from .writer import FileWriter


class PythonGenerator:
    """Generates Python files using TemplateRenderer + FileWriter."""
    
    def __init__(self, renderer: TemplateRenderer = None, writer: FileWriter = None):
        """
        Initialize the Python generator.
        
        Args:
            renderer: TemplateRenderer instance (creates default if None)
            writer: FileWriter instance (creates default if None)
        """
        self.renderer = renderer or TemplateRenderer()
        self.writer = writer or FileWriter()
    
    def generate_models_file(self, nodepaths: List[NodePath], output_dir: Path) -> None:
        """Generate Django models.py file."""
        content = self.renderer.render_template("models.py.jinja2", nodepaths=nodepaths)
        file_path = output_dir / "models.py"
        self.writer.write_file(file_path, content)
    
    def generate_admin_file(self, nodepaths: List[NodePath], output_dir: Path) -> None:
        """Generate Django admin.py file."""
        content = self.renderer.render_template("admin.py.jinja2", nodepaths=nodepaths)
        file_path = output_dir / "admin.py"
        self.writer.write_file(file_path, content)
    
    def generate_api_file(self, nodepaths: List[NodePath], output_dir: Path) -> None:
        """Generate Django Ninja API file."""
        content = self.renderer.render_template("api.py.jinja2", nodepaths=nodepaths)
        file_path = output_dir / "api.py"
        self.writer.write_file(file_path, content)
    
    def generate_schemas_file(self, nodepaths: List[NodePath], output_dir: Path) -> None:
        """Generate Django Ninja schemas file."""
        content = self.renderer.render_template("schemas.py.jinja2", nodepaths=nodepaths)
        file_path = output_dir / "schemas.py"
        self.writer.write_file(file_path, content)
    
    def generate_schemas_in_file(self, nodepaths: List[NodePath], output_dir: Path) -> None:
        """Generate Pydantic input schemas file."""
        content = self.renderer.render_template("schemas_in.py.jinja2", nodepaths=nodepaths)
        file_path = output_dir / "schemas_in.py"
        self.writer.write_file(file_path, content)
    
    def generate_all(self, nodepaths: List[NodePath], output_dir: Path) -> None:
        """Generate all Python files."""
        self.generate_models_file(nodepaths, output_dir)
        self.generate_admin_file(nodepaths, output_dir)
        self.generate_api_file(nodepaths, output_dir)
        self.generate_schemas_file(nodepaths, output_dir)
        self.generate_schemas_in_file(nodepaths, output_dir)

