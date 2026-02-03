"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from django.db import models


class PersonalInfo(models.Model):
    """
    Generated from FormKit Group node: personal_info (label: "Personal Information")
    """

    submission = models.OneToOneField("formkit_ninja.SeparatedSubmission", on_delete=models.CASCADE, primary_key=True, related_name="+")  # Added via extra_attribs hook
    full_name = models.TextField(null="True", blank="True")  # From: personal_info > full_name
    email_address = models.TextField(null="True", blank="True")  # From: personal_info > email_address
