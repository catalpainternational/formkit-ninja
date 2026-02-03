"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from django.contrib import admin
from .. import models


class ReadOnlyInline(admin.TabularInline):
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class MainFormLineItemsInline(ReadOnlyInline):
    model = models.MainFormLineItems


@admin.register(models.MainForm)
class MainFormAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "description",
    ]
    inlines = [
        MainFormLineItemsInline,
    ]
    readonly_fields = [
        "title",
        "description",
    ]


@admin.register(models.MainFormLineItems)
class MainFormLineItemsAdmin(admin.ModelAdmin):
    list_display = [
        "item_name",
        "quantity",
        "price",
    ]
    readonly_fields = [
        "item_name",
        "quantity",
        "price",
    ]
