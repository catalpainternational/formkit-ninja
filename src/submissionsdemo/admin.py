from django.contrib import admin
from .models import Submission

class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')
    search_fields = ('id',)
    ordering = ('-created_at',)

admin.site.register(Submission, SubmissionAdmin)

# Register your models here.
