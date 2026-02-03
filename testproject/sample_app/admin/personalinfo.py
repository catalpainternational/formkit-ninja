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


@admin.register(models.PersonalInfo)
class PersonalInfoAdmin(admin.ModelAdmin):
    list_display = [
        "full_name",
        "email_address",
    ]
    readonly_fields = [
        "full_name",
        "email_address",
    ]
