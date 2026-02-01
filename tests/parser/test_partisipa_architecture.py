"""
Test demonstrating how to Implement 'SeparatedSubmission' linking using a custom NodePath.

Architecture:
Raw JSON -> Submission -> SeparatedSubmission -> Generated Model

This test shows how to ensure every generated Top-Level Model and Repeater Model
automatically gets a link to 'SeparatedSubmission'.
"""

from pathlib import Path

import pytest

from formkit_ninja.parser.database_node_path import DatabaseNodePath
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


# 1. Define the Custom NodePath
class PartisipaNodePath(DatabaseNodePath):
    """
    Custom NodePath that implements the Partisipa Architecture:
    All content models must link back to a SeparatedSubmission.
    """

    @property
    def extra_attribs(self) -> list[str]:
        attribs = super().extra_attribs

        # Check if we should add a submission link
        # We add it to Root Groups (depth=1) and Repeaters

        if self.is_group and self.depth == 1:
            # Root Group -> Primary Key OneToOne
            attribs.append(
                "submission = models.OneToOneField("
                '"form_submission.SeparatedSubmission", '
                "on_delete=models.CASCADE, primary_key=True)"
            )

        elif self.is_repeater:
            # Repeater -> Foreign Key (or OneToOne per row, depending on your design)
            # User requested: OneToOneField to SeparatedSubmission for repeaters too
            attribs.append(
                "submission = models.OneToOneField("
                '"form_submission.SeparatedSubmission", '
                "on_delete=models.CASCADE, null=True)"
            )

        return attribs


@pytest.mark.django_db
class TestSeparatedSubmissionLinking:
    def test_generated_models_have_submission_links(self, tmp_path: Path):
        # 1. Setup Schema (Standard FormKit, no hidden 'submission' field needed!)
        schema = [
            {
                "$formkit": "group",
                "name": "MyForm",
                "children": [
                    {"$formkit": "text", "name": "field1"},
                    {
                        "$formkit": "repeater",
                        "name": "myRepeater",
                        "children": [{"$formkit": "text", "name": "subfield"}],
                    },
                ],
            }
        ]

        # 2. Configure Generator to use OUR Custom NodePath
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=tmp_path,
            node_path_class=PartisipaNodePath,  # <--- The Magic
            merge_top_level_groups=False,
        )

        generator = CodeGenerator(config=config, template_loader=DefaultTemplateLoader(), formatter=CodeFormatter())

        # 3. Generate
        generator.generate(schema)

        # 4. Verify Output
        models_file = tmp_path / "models" / "myform.py"
        content = models_file.read_text()

        print(content)

        # Root model should have PK to SeparatedSubmission
        assert "class Myform(models.Model):" in content
        assert '"form_submission.SeparatedSubmission"' in content
        assert "primary_key=True" in content

        # Repeater model should have link to SeparatedSubmission
        assert "class MyformMyrepeater(models.Model):" in content
        # We can check for the link again (it appears twice)
        assert content.count('"form_submission.SeparatedSubmission"') == 2
