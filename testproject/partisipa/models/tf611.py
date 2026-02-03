"""
TF611 Django models.

Don't make changes to this code directly.
Instead, make changes to the template and re-generate this file.

Generated from FormKit schema: TF 6 1 1 (TF_6_1_1)
Structure:
- Tf611 (main model with all abstract bases merged)
- Tf611Repeaterprojectoutput (repeater child model)
"""

from django.db import models


class Tf611MeetinginformationAbstract(models.Model):
    """
    Generated from FormKit Group node: tf_6_1_1 > meetinginformation (label: "Location")
    """

    class Meta:
        abstract = True

    district = models.TextField(null=True, blank=True)  # From: tf_6_1_1 > meetinginformation > district
    administrative_post = models.TextField(
        null=True, blank=True
    )  # From: tf_6_1_1 > meetinginformation > administrative_post
    suco = models.TextField(null=True, blank=True)  # From: tf_6_1_1 > meetinginformation > suco
    aldeia = models.TextField(null=True, blank=True)  # From: tf_6_1_1 > meetinginformation > aldeia


class Tf611ProjecttimeframeAbstract(models.Model):
    """
    Generated from FormKit Group node: tf_6_1_1 > projecttimeframe (label: "Project time frame")
    """

    class Meta:
        abstract = True

    date_start = models.DateField(null=True, blank=True)  # From: tf_6_1_1 > projecttimeframe > date_start
    date_finish = models.DateField(null=True, blank=True)  # From: tf_6_1_1 > projecttimeframe > date_finish


class Tf611ProjectdetailsAbstract(models.Model):
    """
    Generated from FormKit Group node: tf_6_1_1 > projectdetails (label: "Project details")
    """

    class Meta:
        abstract = True

    project_status = models.TextField(null=True, blank=True)  # From: tf_6_1_1 > projectdetails > project_status
    project_sector = models.TextField(null=True, blank=True)  # From: tf_6_1_1 > projectdetails > project_sector
    project_sub_sector = models.TextField(null=True, blank=True)  # From: tf_6_1_1 > projectdetails > project_sub_sector
    project_name = models.TextField(null=True, blank=True)  # From: tf_6_1_1 > projectdetails > project_name
    objective = models.TextField(null=True, blank=True)  # From: tf_6_1_1 > projectdetails > objective
    latitude = models.DecimalField(
        null=True, blank=True, max_digits=10, decimal_places=7
    )  # From: tf_6_1_1 > projectdetails > latitude
    longitude = models.DecimalField(
        null=True, blank=True, max_digits=10, decimal_places=7
    )  # From: tf_6_1_1 > projectdetails > longitude
    women_priority = models.TextField(null=True, blank=True)  # From: tf_6_1_1 > projectdetails > women_priority


class Tf611ProjectbeneficiariesAbstract(models.Model):
    """
    Generated from FormKit Group node: tf_6_1_1 > projectbeneficiaries (label: "Project beneficiaries")
    """

    class Meta:
        abstract = True

    number_of_households = models.IntegerField(null=True, blank=True)  # From: tf_6_1_1 > projectbeneficiaries > number_of_households
    no_of_women = models.IntegerField(null=True, blank=True)  # From: tf_6_1_1 > projectbeneficiaries > no_of_women
    no_of_men = models.IntegerField(null=True, blank=True)  # From: tf_6_1_1 > projectbeneficiaries > no_of_men
    no_of_pwd_male = models.IntegerField(null=True, blank=True)  # From: tf_6_1_1 > projectbeneficiaries > no_of_pwd_male
    no_of_pwd_female = models.IntegerField(null=True, blank=True)  # From: tf_6_1_1 > projectbeneficiaries > no_of_pwd_female


class Tf611(
    Tf611MeetinginformationAbstract,
    Tf611ProjecttimeframeAbstract,
    Tf611ProjectdetailsAbstract,
    Tf611ProjectbeneficiariesAbstract,
    models.Model,
):
    """
    TF 6 1 1 form main model.

    Inherits from all abstract bases that represent nested groups.
    Links to SeparatedSubmission via OneToOneField.
    """

    class Meta:
        verbose_name = "TF 6 1 1 Submission"
        verbose_name_plural = "TF 6 1 1 Submissions"

    submission = models.OneToOneField(
        "formkit_ninja.SeparatedSubmission",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="+",
    )

    def __str__(self):
        return f"TF611 - {self.submission_id}"


class Tf611Repeaterprojectoutput(models.Model):
    """
    Generated from FormKit Repeater node: tf_6_1_1 > projectoutput > repeaterProjectOutput

    This model stores individual repeater items.
    """

    class Meta:
        verbose_name = "TF 6 1 1 Project Output"
        verbose_name_plural = "TF 6 1 1 Project Outputs"
        ordering = ["parent", "ordinality"]

    parent = models.ForeignKey(
        Tf611,
        on_delete=models.CASCADE,
        related_name="project_outputs",
    )  # From: tf_6_1_1 > projectoutput > repeaterprojectoutput
    ordinality = models.IntegerField()  # Auto-generated for repeater ordering
    submission = models.OneToOneField(
        "formkit_ninja.SeparatedSubmission",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="+",
    )  # Added via extra_attribs hook
    uuid = models.UUIDField(
        editable=False, null=True, blank=True
    )  # From: tf_6_1_1 > projectoutput > repeaterprojectoutput > uuid
    output = models.TextField(
        null=True, blank=True
    )  # From: tf_6_1_1 > projectoutput > repeaterprojectoutput > output
    activity = models.TextField(
        null=True, blank=True
    )  # From: tf_6_1_1 > projectoutput > repeaterprojectoutput > activity
    quantity = models.IntegerField(
        null=True, blank=True
    )  # From: tf_6_1_1 > projectoutput > repeaterprojectoutput > quantity
    unit = models.TextField(
        null=True, blank=True
    )  # From: tf_6_1_1 > projectoutput > repeaterprojectoutput > unit
    woman_priority = models.TextField(
        null=True, blank=True
    )  # From: tf_6_1_1 > projectoutput > repeaterprojectoutput > woman_priority

    def __str__(self):
        return f"TF611 Output #{self.ordinality} - {self.submission_id}"
