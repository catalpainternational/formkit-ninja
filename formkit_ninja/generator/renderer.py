"""
Template rendering component for code generation.

Handles Jinja2 template rendering using existing templates.
"""

from jinja2 import Environment, PackageLoader, select_autoescape


class TemplateRenderer:
    """Handles Jinja2 template rendering using existing templates."""
    
    def __init__(self):
        self._environment = None
    
    def get_environment(self) -> Environment:
        """Get the Jinja2 environment configured for template rendering."""
        if self._environment is None:
            self._environment = Environment(
                loader=PackageLoader("formkit_ninja.parser", "templates"),
                autoescape=select_autoescape(),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        return self._environment
    
    def render_template(self, template_name: str, **context) -> str:
        """
        Render a template with the given context.
        
        Args:
            template_name: Name of the template file (e.g., "models.py.jinja2")
            **context: Template context variables
            
        Returns:
            Rendered template content as string
        """
        env = self.get_environment()
        template = env.get_template(template_name)
        return template.render(**context)

