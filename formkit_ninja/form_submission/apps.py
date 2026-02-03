"""
Django AppConfig for form_submission module.
"""

from django.apps import AppConfig


class FormSubmissionConfig(AppConfig):
    name = "formkit_ninja.form_submission"
    label = "formkit_ninja_form_submission"
    verbose_name = "FormKit Ninja Form Submission"
    default_auto_field = "django.db.models.BigAutoField"
