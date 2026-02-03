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


class Tf611RepeaterprojectoutputInline(ReadOnlyInline):
    model = models.Tf611Repeaterprojectoutput
    extra = 0
    fields = ["ordinality", "output", "activity", "quantity", "unit", "woman_priority"]


@admin.register(models.Tf611)
class Tf611Admin(admin.ModelAdmin):
    list_display = [
        "submission",
        "district",
        "date_start",
        "date_finish",
        "project_status",
        "number_of_households",
    ]
    readonly_fields = [
        "submission",
        "district",
        "administrative_post",
        "suco",
        "aldeia",
        "date_start",
        "date_finish",
        "project_status",
        "project_sector",
        "project_sub_sector",
        "project_name",
        "objective",
        "latitude",
        "longitude",
        "women_priority",
        "number_of_households",
        "no_of_women",
        "no_of_men",
        "no_of_pwd_male",
        "no_of_pwd_female",
    ]
    inlines = [Tf611RepeaterprojectoutputInline]


@admin.register(models.Tf611Repeaterprojectoutput)
class Tf611RepeaterprojectoutputAdmin(admin.ModelAdmin):
    list_display = [
        "submission",
        "parent",
        "ordinality",
        "output",
        "activity",
        "quantity",
    ]
    readonly_fields = [
        "submission",
        "parent",
        "ordinality",
        "uuid",
        "output",
        "activity",
        "quantity",
        "unit",
        "woman_priority",
    ]
