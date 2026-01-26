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


@admin.register(models.Tf_6_1_1Meetinginformation)
class Tf_6_1_1MeetinginformationAdmin(admin.ModelAdmin):
    list_display = [
        "district",
        "administrative_post",
        "suco",
        "aldeia",
    ]
    readonly_fields = [
        "district",
        "administrative_post",
        "suco",
        "aldeia",
    ]


@admin.register(models.Tf_6_1_1Projecttimeframe)
class Tf_6_1_1ProjecttimeframeAdmin(admin.ModelAdmin):
    list_display = [
        "date_start_estimated",
        "date_finish_estimated",
    ]
    readonly_fields = [
        "date_start_estimated",
        "date_finish_estimated",
    ]


@admin.register(models.Tf_6_1_1Projectdetails)
class Tf_6_1_1ProjectdetailsAdmin(admin.ModelAdmin):
    list_display = [
        "project_status",
        "project_sector",
        "project_subsector",
        "project_name",
        "objective",
        "gps_latitude",
        "gps_longitude",
        "is_women_priority",
    ]
    readonly_fields = [
        "project_status",
        "project_sector",
        "project_subsector",
        "project_name",
        "objective",
        "gps_latitude",
        "gps_longitude",
        "is_women_priority",
    ]


@admin.register(models.Tf_6_1_1Projectbeneficiaries)
class Tf_6_1_1ProjectbeneficiariesAdmin(admin.ModelAdmin):
    list_display = [
        "number_of_households",
        "no_of_women",
        "no_of_men",
        "disability_male",
        "disability_female",
    ]
    readonly_fields = [
        "number_of_households",
        "no_of_women",
        "no_of_men",
        "disability_male",
        "disability_female",
    ]


class Tf_6_1_1ProjectoutputRepeaterprojectoutputInline(ReadOnlyInline):
    model = models.Tf_6_1_1ProjectoutputRepeaterprojectoutput


@admin.register(models.Tf_6_1_1ProjectoutputRepeaterprojectoutput)
class Tf_6_1_1ProjectoutputRepeaterprojectoutputAdmin(admin.ModelAdmin):
    list_display = [
        "uuid",
    ]
    readonly_fields = [
        "uuid",
    ]


@admin.register(models.Tf_6_1_1Projectoutput)
class Tf_6_1_1ProjectoutputAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Tf_6_1_1)
class Tf_6_1_1Admin(admin.ModelAdmin):
    list_display = [
        "meetinginformation",
        "projecttimeframe",
        "projectdetails",
        "projectbeneficiaries",
        "projectoutput",
    ]
    readonly_fields = [
        "meetinginformation",
        "projecttimeframe",
        "projectdetails",
        "projectbeneficiaries",
        "projectoutput",
    ]


@admin.register(models.Tf_6_1_1Meetinginformation)
class Tf_6_1_1MeetinginformationAdmin(admin.ModelAdmin):
    list_display = [
        "district",
        "administrative_post",
        "suco",
        "aldeia",
    ]
    readonly_fields = [
        "district",
        "administrative_post",
        "suco",
        "aldeia",
    ]


@admin.register(models.Tf_6_1_1Projecttimeframe)
class Tf_6_1_1ProjecttimeframeAdmin(admin.ModelAdmin):
    list_display = [
        "date_start_estimated",
        "date_finish_estimated",
    ]
    readonly_fields = [
        "date_start_estimated",
        "date_finish_estimated",
    ]


@admin.register(models.Tf_6_1_1Projectdetails)
class Tf_6_1_1ProjectdetailsAdmin(admin.ModelAdmin):
    list_display = [
        "project_status",
        "project_sector",
        "project_subsector",
        "project_name",
        "objective",
        "gps_latitude",
        "gps_longitude",
        "is_women_priority",
    ]
    readonly_fields = [
        "project_status",
        "project_sector",
        "project_subsector",
        "project_name",
        "objective",
        "gps_latitude",
        "gps_longitude",
        "is_women_priority",
    ]


@admin.register(models.Tf_6_1_1Projectbeneficiaries)
class Tf_6_1_1ProjectbeneficiariesAdmin(admin.ModelAdmin):
    list_display = [
        "number_of_households",
        "no_of_women",
        "no_of_men",
        "disability_male",
        "disability_female",
    ]
    readonly_fields = [
        "number_of_households",
        "no_of_women",
        "no_of_men",
        "disability_male",
        "disability_female",
    ]


class Tf_6_1_1ProjectoutputRepeaterprojectoutputInline(ReadOnlyInline):
    model = models.Tf_6_1_1ProjectoutputRepeaterprojectoutput


@admin.register(models.Tf_6_1_1ProjectoutputRepeaterprojectoutput)
class Tf_6_1_1ProjectoutputRepeaterprojectoutputAdmin(admin.ModelAdmin):
    list_display = [
        "uuid",
    ]
    readonly_fields = [
        "uuid",
    ]


@admin.register(models.Tf_6_1_1Projectoutput)
class Tf_6_1_1ProjectoutputAdmin(admin.ModelAdmin):
    pass


class Tf_6_1_1ProjectoutputRepeaterprojectoutputInline(ReadOnlyInline):
    model = models.Tf_6_1_1ProjectoutputRepeaterprojectoutput


@admin.register(models.Tf_6_1_1ProjectoutputRepeaterprojectoutput)
class Tf_6_1_1ProjectoutputRepeaterprojectoutputAdmin(admin.ModelAdmin):
    list_display = [
        "uuid",
    ]
    readonly_fields = [
        "uuid",
    ]
