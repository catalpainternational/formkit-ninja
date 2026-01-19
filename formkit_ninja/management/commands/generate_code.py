"""
Django management command to generate Python code from FormKit schemas.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from formkit_ninja.generator import CodeGenerator


class Command(BaseCommand):
    """Django management command for code generation."""
    
    help = 'Generate Python code files from FormKit JSON schemas'
    
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--output-dir',
            type=str,
            default='./generated/',
            help='Output directory for generated files (default: ./generated/)'
        )
        parser.add_argument(
            '--schema',
            type=str,
            help='Path to a specific schema JSON file'
        )
        parser.add_argument(
            '--schema-name',
            type=str,
            help='Name of schema from formkit_ninja/schemas/ directory'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Generate from all schemas in formkit_ninja/schemas/'
        )
        parser.add_argument(
            '--backup',
            action='store_true',
            help='Backup existing files with .bak extension'
        )
    
    def handle(self, *args, **options):
        """Handle the command execution."""
        output_dir = Path(options['output_dir'])
        backup = options['backup']
        
        # Create output directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)
        
        generator = CodeGenerator()
        
        try:
            if options['schema']:
                # Generate from specific schema file
                schema_path = Path(options['schema'])
                if not schema_path.exists():
                    raise CommandError(f"Schema file not found: {schema_path}")
                
                self.stdout.write(f"Generating code from schema file: {schema_path}")
                generator.generate_from_schema_file(schema_path, output_dir)
                
            elif options['schema_name']:
                # Generate from schema name in schemas directory
                from formkit_ninja.schemas import Schemas
                schemas = Schemas()
                
                if options['schema_name'] not in schemas.list_schemas():
                    available = ', '.join(schemas.list_schemas())
                    raise CommandError(
                        f"Schema '{options['schema_name']}' not found. "
                        f"Available schemas: {available}"
                    )
                
                self.stdout.write(f"Generating code from schema: {options['schema_name']}")
                schema_dict = schemas.as_json(options['schema_name'])
                generator.generate_from_schema(schema_dict, output_dir)
                
            elif options['all']:
                # Generate from all schemas
                self.stdout.write("Generating code from all schemas")
                generator.generate_from_existing_schemas(output_dir)
                
            else:
                raise CommandError(
                    "Please specify --schema, --schema-name, or --all. "
                    "Use --help for more information."
                )
            
            # List generated files
            generated_files = list(output_dir.glob("*.py"))
            if generated_files:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully generated {len(generated_files)} files:"
                    )
                )
                for file_path in generated_files:
                    self.stdout.write(f"  - {file_path}")
            else:
                self.stdout.write(
                    self.style.WARNING("No files were generated")
                )
                
        except Exception as e:
            raise CommandError(f"Error generating code: {e}")

