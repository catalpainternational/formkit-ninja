"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from django.db import models


class ParentItems(models.Model):
    # This class is a Repeater: Parent and ordinality fields have been added"
    parent = models.ForeignKey("Parent", on_delete=models.CASCADE, related_name="items")
    ordinality = models.IntegerField()
    item_name = models.TextField(null=True, blank=True)
    item_count = models.IntegerField(null=True, blank=True)


class ParentChild(models.Model):
    child_field = models.TextField(null=True, blank=True)


class Parent(models.Model):
    child = models.OneToOneField(ParentChild, on_delete=models.CASCADE)


class ParentChild(models.Model):
    child_field = models.TextField(null=True, blank=True)


class ParentItems(models.Model):
    # This class is a Repeater: Parent and ordinality fields have been added"
    parent = models.ForeignKey("Parent", on_delete=models.CASCADE, related_name="items")
    ordinality = models.IntegerField()
    item_name = models.TextField(null=True, blank=True)
    item_count = models.IntegerField(null=True, blank=True)
