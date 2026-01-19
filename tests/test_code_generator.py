"""
Tests for the code generator functionality.

Tests the complete code generation pipeline from FormKit schemas to Python files.
"""

import json
import tempfile
from pathlib import Path

import pytest

from formkit_ninja.generator import CodeGenerator
from formkit_ninja.generator.processor import NodePathProcessor
from formkit_ninja.generator.python_generator import PythonGenerator
from formkit_ninja.generator.renderer import TemplateRenderer
from formkit_ninja.generator.writer import FileWriter


def test_template_renderer():
    """Test template rendering functionality."""
    renderer = TemplateRenderer()
    
    # Test basic template rendering
    result = renderer.render_template('models.py.jinja2', nodepaths=[])
    assert 'from django.db import models' in result
    assert 'Don\'t make changes to this code directly' in result


def test_file_writer():
    """Test file writing functionality."""
    writer = FileWriter()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = Path(temp_dir) / 'test_file.py'
        content = 'print("Hello, World!")'
        
        writer.write_file(test_file, content)
        
        assert test_file.exists()
        assert test_file.read_text() == content


def test_nodepath_processor_process_schema_to_nodepaths():
    """Test NodePath processing from schema."""
    processor = NodePathProcessor()
    
    # Use a working schema from the schemas directory
    with open('formkit_ninja/schemas/EXAMPLE.json', 'r') as f:
        schema = json.load(f)
    
    nodepaths = processor.process_schema(schema)
    
    # Should have at least one NodePath
    assert len(nodepaths) >= 1
    
    # All NodePaths should have valid classnames
    for np in nodepaths:
        assert np.classname
        assert isinstance(np.classname, str)


def test_python_generator_generate_models_file():
    """Test models.py file generation."""
    renderer = TemplateRenderer()
    writer = FileWriter()
    generator = PythonGenerator(renderer, writer)
    
    processor = NodePathProcessor()
    with open('formkit_ninja/schemas/EXAMPLE.json', 'r') as f:
        schema = json.load(f)
    
    nodepaths = processor.process_schema(schema)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        generator.generate_models_file(nodepaths, output_dir)
        
        models_file = output_dir / 'models.py'
        assert models_file.exists()
        
        content = models_file.read_text()
        assert 'from django.db import models' in content
        assert 'class ' in content and '(models.Model):' in content


def test_python_generator_generate_admin_file():
    """Test admin.py file generation."""
    renderer = TemplateRenderer()
    writer = FileWriter()
    generator = PythonGenerator(renderer, writer)
    
    processor = NodePathProcessor()
    with open('formkit_ninja/schemas/EXAMPLE.json', 'r') as f:
        schema = json.load(f)
    
    nodepaths = processor.process_schema(schema)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        generator.generate_admin_file(nodepaths, output_dir)
        
        admin_file = output_dir / 'admin.py'
        assert admin_file.exists()
        
        content = admin_file.read_text()
        assert 'from django.contrib import admin' in content
        assert 'class ' in content and 'Admin(admin.ModelAdmin):' in content


def test_python_generator_generate_api_file():
    """Test api.py file generation."""
    renderer = TemplateRenderer()
    writer = FileWriter()
    generator = PythonGenerator(renderer, writer)
    
    processor = NodePathProcessor()
    with open('formkit_ninja/schemas/EXAMPLE.json', 'r') as f:
        schema = json.load(f)
    
    nodepaths = processor.process_schema(schema)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        generator.generate_api_file(nodepaths, output_dir)
        
        api_file = output_dir / 'api.py'
        assert api_file.exists()
        
        content = api_file.read_text()
        assert 'from ninja import Router' in content
        assert 'def ' in content and '(request):' in content


def test_python_generator_generate_schemas_file():
    """Test schemas.py file generation."""
    renderer = TemplateRenderer()
    writer = FileWriter()
    generator = PythonGenerator(renderer, writer)
    
    processor = NodePathProcessor()
    with open('formkit_ninja/schemas/EXAMPLE.json', 'r') as f:
        schema = json.load(f)
    
    nodepaths = processor.process_schema(schema)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        generator.generate_schemas_file(nodepaths, output_dir)
        
        schemas_file = output_dir / 'schemas.py'
        assert schemas_file.exists()
        
        content = schemas_file.read_text()
        assert 'from ninja import Schema' in content
        assert 'class ' in content and 'Schema(Schema):' in content


def test_python_generator_generate_schemas_in_file():
    """Test schemas_in.py file generation."""
    renderer = TemplateRenderer()
    writer = FileWriter()
    generator = PythonGenerator(renderer, writer)
    
    processor = NodePathProcessor()
    with open('formkit_ninja/schemas/EXAMPLE.json', 'r') as f:
        schema = json.load(f)
    
    nodepaths = processor.process_schema(schema)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        generator.generate_schemas_in_file(nodepaths, output_dir)
        
        schemas_in_file = output_dir / 'schemas_in.py'
        assert schemas_in_file.exists()
        
        content = schemas_in_file.read_text()
        assert 'from pydantic import BaseModel' in content
        assert 'class ' in content and '(BaseModel):' in content


def test_python_generator_generate_all():
    """Test complete file generation."""
    renderer = TemplateRenderer()
    writer = FileWriter()
    generator = PythonGenerator(renderer, writer)
    
    processor = NodePathProcessor()
    with open('formkit_ninja/schemas/EXAMPLE.json', 'r') as f:
        schema = json.load(f)
    
    nodepaths = processor.process_schema(schema)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        generator.generate_all(nodepaths, output_dir)
        
        # Check all files are generated
        expected_files = ['models.py', 'admin.py', 'api.py', 'schemas.py', 'schemas_in.py']
        for filename in expected_files:
            assert (output_dir / filename).exists()


def test_code_generator_integration():
    """Test complete code generator integration."""
    generator = CodeGenerator()
    
    with open('formkit_ninja/schemas/EXAMPLE.json', 'r') as f:
        schema = json.load(f)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        generator.generate_from_schema(schema, output_dir)
        
        # Check all files are generated
        expected_files = ['models.py', 'admin.py', 'api.py', 'schemas.py', 'schemas_in.py']
        for filename in expected_files:
            assert (output_dir / filename).exists()


def test_management_command_schema_name():
    """Test management command with schema name."""
    from django.core.management import call_command
    from io import StringIO
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output = StringIO()
        call_command(
            'generate_code',
            '--schema-name', 'EXAMPLE',
            '--output-dir', temp_dir,
            stdout=output
        )
        
        # Check files were generated
        expected_files = ['models.py', 'admin.py', 'api.py', 'schemas.py', 'schemas_in.py']
        for filename in expected_files:
            assert (Path(temp_dir) / filename).exists()


def test_management_command_schema_file():
    """Test management command with schema file."""
    from django.core.management import call_command
    from io import StringIO
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output = StringIO()
        call_command(
            'generate_code',
            '--schema', 'formkit_ninja/schemas/EXAMPLE.json',
            '--output-dir', temp_dir,
            stdout=output
        )
        
        # Check files were generated
        expected_files = ['models.py', 'admin.py', 'api.py', 'schemas.py', 'schemas_in.py']
        for filename in expected_files:
            assert (Path(temp_dir) / filename).exists()