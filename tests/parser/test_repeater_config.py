"""
Test generating the Tf_6_1_1Repeaterprojectoutput model purely from Django configuration.
"""

from pathlib import Path

import pytest

from formkit_ninja.code_generation_config import CodeGenerationConfig
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


@pytest.mark.django_db
class TestRepeaterConfig:
    def test_generate_repeater_from_config(self, tmp_path: Path):
        # 1. Define the Schema
        # We explicitly include 'uuid' and 'submission' so we can configure them
        schema = [
            {
                "$formkit": "group",
                "name": "Tf_6_1_1",
                "label": "Root Form",
                "children": [
                    {
                        "$formkit": "repeater",
                        "name": "repeaterProjectOutput",
                        "children": [
                            # Standard Fields
                            {"$formkit": "number", "name": "quantity", "label": "Quantity"},
                            {"$formkit": "select", "name": "output", "options": "$ida(output)"},
                            {"$formkit": "select", "name": "activity", "options": "$ida(activity)"},
                            {"$formkit": "select", "name": "unit", "options": "$ida(unit)"},
                            {"$formkit": "select", "name": "woman_priority", "options": "$ida(yesno)"},
                            # "Hidden" fields we want to map to model fields
                            {"$formkit": "hidden", "name": "uuid"},
                            {"$formkit": "hidden", "name": "submission"},
                        ],
                    }
                ],
            }
        ]

        # 2. Configure Foreign Keys via Django Admin

        # Output -> FK to ida_options.Output
        CodeGenerationConfig.objects.create(
            node_name="output",
            django_type="ForeignKey",
            django_args={"to": "ida_options.Output", "on_delete": "models.DO_NOTHING", "null": True, "blank": True},
            is_active=True,
            priority=100,
        )

        # Activity -> FK to ida_options.Activity
        CodeGenerationConfig.objects.create(
            node_name="activity",
            django_type="ForeignKey",
            django_args={"to": "ida_options.Activity", "on_delete": "models.DO_NOTHING", "null": True, "blank": True},
            is_active=True,
            priority=100,
        )

        # Unit -> FK to ida_options.Unit
        CodeGenerationConfig.objects.create(
            node_name="unit",
            django_type="ForeignKey",
            django_args={"to": "ida_options.Unit", "on_delete": "models.DO_NOTHING", "null": True, "blank": True},
            is_active=True,
            priority=100,
        )

        # Woman Priority -> FK with related_name="+"
        CodeGenerationConfig.objects.create(
            node_name="woman_priority",
            django_type="ForeignKey",
            django_args={
                "to": "ida_options.YesNo",
                "on_delete": "models.DO_NOTHING",
                "related_name": "+",
                "null": True,
                "blank": True,
            },
            is_active=True,
            priority=100,
        )

        # UUID -> UUIDField
        CodeGenerationConfig.objects.create(
            node_name="uuid",
            django_type="UUIDField",
            django_args={"editable": False, "unique": True, "null": True, "blank": True},
            is_active=True,
            priority=100,
        )

        # Submission -> OneToOneField
        CodeGenerationConfig.objects.create(
            node_name="submission",
            django_type="OneToOneField",
            django_args={"to": "form_submission.SeparatedSubmission", "on_delete": "models.CASCADE", "null": True},
            is_active=True,
            priority=100,
        )

        # 3. Generate
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
            merge_top_level_groups=False,  # Simple generation for this test
        )

        generator = CodeGenerator(config=config, template_loader=DefaultTemplateLoader(), formatter=CodeFormatter())
        generator.generate(schema)

        # 4. Read Result
        models_file = tmp_path / "models" / "tf611.py"
        content = models_file.read_text()
        print(content)

        # Verify Fields
        assert "output = models.ForeignKey(" in content
        assert "ida_options.Output" in content

        assert "related_name='+'" in content or 'related_name="+"' in content

        assert "uuid = models.UUIDField(" in content
        assert "unique=True" in content

        assert "submission = models.OneToOneField(" in content
        assert "form_submission.SeparatedSubmission" in content

        # Check Parent (Auto-generated)
        assert "parent = models.ForeignKey(" in content
