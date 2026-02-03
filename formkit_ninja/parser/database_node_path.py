"""
DatabaseNodePath: NodePath that reads configuration from database.

This module provides DatabaseNodePath, a NodePath subclass that queries
the CodeGenerationConfig model for type mappings and field arguments,
enabling database-driven code generation configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings

from formkit_ninja.parser.type_convert import NodePath

if TYPE_CHECKING:
    from formkit_ninja.code_generation_config import CodeGenerationConfig


class DatabaseNodePath(NodePath):
    """
    NodePath that reads type mappings from database.

    Priority cascade:
    1. CodeGenerationConfig matching node_name (if exists)
    2. CodeGenerationConfig matching options_pattern
    3. CodeGenerationConfig matching formkit_type
    4. Django settings FORMKIT_NINJA['TYPE_MAPPINGS']
    5. Default TypeConverterRegistry

    Example usage:
        config = GeneratorConfig(
            app_name="myapp",
            output_dir=Path("./generated"),
            node_path_class=DatabaseNodePath,
        )
    """

    def __init__(self, *nodes, **kwargs):
        super().__init__(*nodes, **kwargs)
        self._config_cache: dict[str, CodeGenerationConfig | None] = {}

    def _get_config(self) -> "CodeGenerationConfig | None":
        """
        Get matching CodeGenerationConfig for current node.

        Returns the highest priority config that matches:
        1. node_name (exact match)
        2. options_pattern (startswith match)
        3. formkit_type (exact match, no node_name/options_pattern set)

        Returns:
            Matching CodeGenerationConfig or None
        """
        # Build cache key (include options to handle pattern matching)
        formkit_val = getattr(self.node, "formkit", "")
        name_val = getattr(self.node, "name", "")
        options_val = str(getattr(self.node, "options", ""))
        cache_key = f"{formkit_val}-{name_val}-{options_val}"

        if cache_key in self._config_cache:
            return self._config_cache[cache_key]

        from formkit_ninja.code_generation_config import CodeGenerationConfig

        # Priority 1: Try node_name match (highest priority)
        if hasattr(self.node, "name") and self.node.name:
            config = (
                CodeGenerationConfig.objects.filter(
                    is_active=True,
                    node_name=self.node.name,
                )
                .order_by("-priority")
                .first()
            )
            if config:
                self._config_cache[cache_key] = config
                return config

        # Priority 2: Try options pattern match
        if hasattr(self.node, "options") and self.node.options:
            options_str = str(self.node.options)

            # Build filter - include formkit_type if available
            filter_kwargs = {
                "is_active": True,
                "options_pattern__isnull": False,
            }
            if hasattr(self.node, "formkit"):
                filter_kwargs["formkit_type"] = self.node.formkit

            configs = CodeGenerationConfig.objects.filter(**filter_kwargs).order_by("-priority")

            for cfg in configs:
                if cfg.options_pattern and options_str.startswith(cfg.options_pattern):
                    self._config_cache[cache_key] = cfg
                    return cfg

        # Priority 3: Try formkit_type match (no node_name/options_pattern)
        if hasattr(self.node, "formkit"):
            config = (
                CodeGenerationConfig.objects.filter(
                    is_active=True,
                    formkit_type=self.node.formkit,
                    node_name__isnull=True,
                    options_pattern__isnull=True,
                )
                .order_by("-priority")
                .first()
            )
            if config:
                self._config_cache[cache_key] = config
                return config

        self._config_cache[cache_key] = None
        return None

    def _get_from_settings(self, field: str) -> str | dict | None:
        """
        Get configuration from Django settings.

        Checks FORMKIT_NINJA settings in order:
        1. NAME_MAPPINGS[node.name][field]
        2. OPTIONS_MAPPINGS (pattern match)
        3. TYPE_MAPPINGS[node.formkit][field]

        Args:
            field: Field name ('pydantic_type', 'django_type', 'django_args')

        Returns:
            Configuration value or None
        """
        formkit_settings = getattr(settings, "FORMKIT_NINJA", {})

        # Check NAME_MAPPINGS first (highest priority in settings)
        if hasattr(self.node, "name") and self.node.name:
            name_mappings = formkit_settings.get("NAME_MAPPINGS", {})
            if self.node.name in name_mappings:
                mapping = name_mappings[self.node.name]
                if field in mapping:
                    return mapping[field]

        # Check OPTIONS_MAPPINGS
        if hasattr(self.node, "options") and self.node.options:
            options_str = str(self.node.options)
            options_mappings = formkit_settings.get("OPTIONS_MAPPINGS", {})
            for pattern, mapping in options_mappings.items():
                if options_str.startswith(pattern):
                    if field in mapping:
                        return mapping[field]

        # Check TYPE_MAPPINGS
        if hasattr(self.node, "formkit"):
            type_mappings = formkit_settings.get("TYPE_MAPPINGS", {})
            if self.node.formkit in type_mappings:
                mapping = type_mappings[self.node.formkit]
                if field in mapping:
                    return mapping[field]

        return None

    def to_pydantic_type(self) -> str:
        """
        Get Pydantic type for this node.
        Prioritizes fields already on the node (via super()).
        """
        # 1. Check if it's already on the node
        res = super().to_pydantic_type()
        # super().to_pydantic_type() returns converter.pydantic_type if not found on node.
        # We need to know if it was found on the node or not.
        if hasattr(self.node, "pydantic_field_type") and self.node.pydantic_field_type:
            return res

        # 2. Check database config
        config = self._get_config()
        if config and config.pydantic_type:
            return config.pydantic_type

        # Check Django settings
        settings_type = self._get_from_settings("pydantic_type")
        if settings_type:
            return str(settings_type)

        # Fall back to parent implementation (default converters)
        return super().to_pydantic_type()

    def to_django_type(self) -> str:
        """
        Get Django field type for this node.
        Prioritizes fields already on the node (via super()).
        """
        # 1. Check if it's already on the node
        if hasattr(self.node, "django_field_type") and self.node.django_field_type:
            return self.node.django_field_type

        # 2. Check database config
        config = self._get_config()
        if config and config.django_type:
            return config.django_type

        # Check Django settings
        settings_type = self._get_from_settings("django_type")
        if settings_type:
            return str(settings_type)

        # Fall back to parent implementation
        return super().to_django_type()

    def to_django_args(self) -> str:
        """
        Get Django field arguments for this node.
        Prioritizes fields already on the node (via super()).
        """
        # 1. Check if it's already on the node
        if hasattr(self.node, "django_field_args") and self.node.django_field_args:
            return super().to_django_args()

        # 2. Check database config
        config = self._get_config()
        if config and config.django_args:
            return config.get_django_args_str()

        # Check Django settings
        settings_args = self._get_from_settings("django_args")
        if settings_args:
            if isinstance(settings_args, dict):
                # Convert dict to string format
                return self._django_args_dict_to_str(settings_args)
            elif isinstance(settings_args, str):
                return settings_args

        # Fall back to parent implementation
        return super().to_django_args()

    def get_validators(self) -> list[str]:
        """
        Get validators for this node.
        Prioritizes fields already on the node (via super()).
        """
        # 1. Check if it's already on the node (handled by super())
        res = super().get_validators()
        # super().get_validators() returns an empty list if not found on node.
        # If `res` is not empty, it means it came from the node.
        if res:
            return res

        # 2. Check database config
        config = self._get_config()
        if config and config.validators:
            return config.validators

        # Check settings
        settings_validators = self._get_from_settings("validators")
        if settings_validators and isinstance(settings_validators, list):
            return settings_validators

        return []

    def get_extra_imports(self) -> list[str]:
        """
        Get extra imports for this node.
        Prioritizes fields already on the node (via super()).
        """
        # 1. Check if it's already on the node (handled by super())
        res = super().get_extra_imports()
        # super().get_extra_imports() returns an empty list if not found on node.
        # If `res` is not empty, it means it came from the node.
        if res:
            return res

        # 2. Check database config
        config = self._get_config()
        if config and config.extra_imports:
            return config.extra_imports

        # Check settings
        settings_imports = self._get_from_settings("extra_imports")
        if settings_imports and isinstance(settings_imports, list):
            return settings_imports

        return super().get_extra_imports()

    @staticmethod
    def _django_args_dict_to_str(args_dict: dict) -> str:
        """
        Convert django_args dict to string format.

        Args:
            args_dict: Dict of field arguments

        Returns:
            Comma-separated string of arguments
        """
        parts = []
        for key, value in args_dict.items():
            if isinstance(value, bool):
                parts.append(f"{key}={str(value)}")
            elif isinstance(value, (int, float)):
                parts.append(f"{key}={value}")
            elif isinstance(value, str):
                # Handle model references (e.g., "app.Model" or models.CASCADE)
                if value in {"True", "False", "None"}:
                    parts.append(f"{key}={value}")
                elif value.startswith("models.") or ("." in value and not value.startswith('"')):
                    parts.append(f"{key}={value}")
                else:
                    parts.append(f'{key}="{value}"')
            else:
                parts.append(f"{key}={value}")

        return ", ".join(parts)
