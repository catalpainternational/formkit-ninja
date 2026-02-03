"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from django.db import models


class MainForm(models.Model):
    """
    Generated from FormKit Group node: main_form (label: "Main Form")
    """

    submission = models.OneToOneField("formkit_ninja.SeparatedSubmission", on_delete=models.CASCADE, primary_key=True, related_name="+")  # Added via extra_attribs hook
    title = models.TextField(null="True", blank="True")  # From: main_form > title
    description = models.TextField(null="True", blank="True")  # From: main_form > description


class MainFormLineItems(models.Model):
    """
    Generated from FormKit Repeater node: main_form > line_items (label: "Line Items")
    """

    # This class is a Repeater: Parent and ordinality fields have been added"
    parent = models.ForeignKey("MainForm", on_delete=models.CASCADE, related_name="line_items")  # From: main_form > line_items
    ordinality = models.IntegerField()  # Auto-generated for repeater ordering
    submission = models.OneToOneField("formkit_ninja.SeparatedSubmission", on_delete=models.CASCADE, primary_key=True, related_name="+")  # Added via extra_attribs hook
    item_name = models.TextField(null="True", blank="True")  # From: main_form > line_items > item_name
    quantity = models.IntegerField(null="True", blank="True")  # From: main_form > line_items > quantity
    price = models.IntegerField(null="True", blank="True")  # From: main_form > line_items > price
