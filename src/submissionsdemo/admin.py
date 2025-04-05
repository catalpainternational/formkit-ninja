from django.contrib import admin
from django.utils.safestring import mark_safe
import json
from .models import Submission

class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'updated_at', 'form')
    readonly_fields = ('id', 'created_at', 'updated_at', 'form', 'formatted_data', 'deleted_at')
    search_fields = ('id',)
    ordering = ('-created_at',)
    exclude = ('data',)  # Hide the raw data field since we show formatted version

    def formatted_data(self, obj):
        """Display the data JSON in a formatted way"""
        if obj and obj.data:
            formatted_json = json.dumps(obj.data, indent=2)
            return mark_safe(f'<pre style="background-color: #f5f5f5; padding: 10px; border-radius: 4px;">{formatted_json}</pre>')
        return ""
    formatted_data.short_description = "Form Data"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True  # Allow viewing but all fields are readonly

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(Submission, SubmissionAdmin)

# Register your models here.
