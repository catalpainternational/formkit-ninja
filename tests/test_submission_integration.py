import importlib.util
import sys
from unittest.mock import MagicMock

import pytest

from formkit_ninja.code_generation_config import CodeGenerationConfig
from formkit_ninja.models import SeparatedSubmission, Submission
from formkit_ninja.parser.database_node_path import DatabaseNodePath
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator, GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader


# Helper for loading module
def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.django_db
class TestSubmissionIntegration:
    def test_full_lifecycle(self, tmp_path):
        # 1. Setup Configuration

        # Submission Link Config (Generic for any node named 'submission')
        CodeGenerationConfig.objects.create(
            node_name="submission",
            django_type="OneToOneField",
            django_args={
                "to": "formkit_ninja.models.SeparatedSubmission",
                "on_delete": "models.CASCADE",
                "related_name": "+",
                "null": True,
                "blank": True,
            },
            is_active=True,
            priority=100,
        )

        # Repeater "myrepeater"
        CodeGenerationConfig.objects.create(
            node_name="myrepeater", django_type="OneToOneField", is_active=True, priority=100
        )

        # 2. Schema
        schema_data = [
            {
                "$formkit": "group",
                "name": "myform",
                "children": [
                    {"$formkit": "text", "name": "field1"},
                    # Explicit Submission Link for Root
                    {"$formkit": "text", "name": "submission"},
                    {
                        "$formkit": "repeater",
                        "name": "myrepeater",
                        "children": [
                            {"$formkit": "text", "name": "subfield"},
                            # Explicit Submission Link for Repeater
                            {"$formkit": "text", "name": "submission"},
                        ],
                    },
                ],
            }
        ]

        # 3. Generate Code
        output_dir = tmp_path / "models"
        output_dir.mkdir()

        config = GeneratorConfig(
            app_name="formkit_ninja",
            output_dir=output_dir,
            node_path_class=DatabaseNodePath,
            custom_imports=["import formkit_ninja.models"],
        )

        generator = CodeGenerator(
            config=config,
            template_loader=DefaultTemplateLoader(),
            formatter=CodeFormatter(),
        )
        generator.generate(schema_data)

        # 4. Load Generated Models
        models_file = output_dir / "models" / "myform.py"
        assert models_file.exists()

        generated_models = load_module("formkit_ninja.models.myform", models_file)

        Myform = getattr(generated_models, "Myform", None)
        assert Myform is not None

        MyformMyrepeater = getattr(generated_models, "MyformMyrepeater", None)
        assert MyformMyrepeater is not None

        # Verify 'submission' field existence
        assert hasattr(Myform, "submission"), "Myform should have 'submission' field"

        # 5. Create Submission
        submission_data = {"field1": "hello", "myrepeater": [{"subfield": "row1"}, {"subfield": "row2"}]}

        sub = Submission.objects.create(form_type="myform", fields=submission_data)

        # 6. Setup for Separation
        # We don't call from_submission yet, because we want to catch the signals
        # after mocks are in place.

        # 7. Mock Objects Manager and Connect Signal Handler
        # We replace .objects on the classes
        Myform.objects = MagicMock()
        Myform.objects.update_or_create.return_value = (MagicMock(), True)

        MyformMyrepeater.objects = MagicMock()
        MyformMyrepeater.objects.update_or_create.return_value = (MagicMock(), True)

        # In this decoupled world, we simulate the user app connecting the handler
        from formkit_ninja.form_submission.handlers import auto_populate_model
        from formkit_ninja.form_submission.signals import separated_submission_created

        # Disconnect the auto handler if it was automatically connected by the import
        separated_submission_created.disconnect(auto_populate_model)

        # We wrap this in a patch to ensure to_model uses our generated_models module
        # since the default auto_populate_model would try to look up models globally
        # (which doesn't work for dynamically loaded ones in a test)
        def manual_populate(sender, instance, **kwargs):
            instance.to_model(models_module=generated_models)

        separated_submission_created.connect(manual_populate)

        try:
            # 8. Separate Submission (This will now trigger the signals!)
            SeparatedSubmission.objects.from_submission(sub)
        finally:
            # Cleanup
            separated_submission_created.disconnect(manual_populate)

        # 9. Verify update_or_create calls
        # Verify update_or_create calls
        # Root Item (Myform)
        root_item = SeparatedSubmission.objects.get(repeater_key__isnull=True)
        Myform.objects.update_or_create.assert_called()
        call_args = Myform.objects.update_or_create.call_args[1]

        # Check that submission was passed
        assert call_args["submission_id"] == root_item.pk
        # Check fields
        assert call_args["defaults"]["field1"] == "hello"

        # Repeater Items
        repeater_items = SeparatedSubmission.objects.filter(repeater_key="myrepeater")
        assert MyformMyrepeater.objects.update_or_create.call_count == 2

        for rep_item in repeater_items:
            found = False
            for call in MyformMyrepeater.objects.update_or_create.call_args_list:
                kwargs = call[1]
                if kwargs.get("submission_id") == rep_item.pk:
                    found = True
                    # Check defaults has subfield
                    assert kwargs["defaults"]["subfield"] in ["row1", "row2"]
                    break
            assert found, f"No call found for repeater item {rep_item}"
