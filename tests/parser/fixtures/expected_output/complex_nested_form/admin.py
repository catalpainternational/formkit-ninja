"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from django.contrib import admin

from . import models


class ReadOnlyInline(admin.TabularInline):
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ParentItemsInline(ReadOnlyInline):
    model = models.ParentItems


@admin.register(models.ParentItems)
class ParentItemsAdmin(admin.ModelAdmin):
    list_display = [
        "item_name",
        "item_count",
    ]
    readonly_fields = [
        "item_name",
        "item_count",
    ]


@admin.register(models.ParentChild)
class ParentChildAdmin(admin.ModelAdmin):
    list_display = [
        "child_field",
    ]
    readonly_fields = [
        "child_field",
    ]


@admin.register(models.Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = [
        "child",
    ]
    inlines = [
        ParentItemsInline,
    ]
    readonly_fields = [
        "child",
    ]


@admin.register(models.ParentChild)
class ParentChildAdmin(admin.ModelAdmin):
    list_display = [
        "child_field",
    ]
    readonly_fields = [
        "child_field",
    ]


class ParentItemsInline(ReadOnlyInline):
    model = models.ParentItems


@admin.register(models.ParentItems)
class ParentItemsAdmin(admin.ModelAdmin):
    list_display = [
        "item_name",
        "item_count",
    ]
    readonly_fields = [
        "item_name",
        "item_count",
    ]
