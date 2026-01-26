"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from django.db import models


class Tf_6_1_1Meetinginformation(models.Model):
    district = models.TextField(null=True, blank=True)
    administrative_post = models.TextField(null=True, blank=True)
    suco = models.TextField(null=True, blank=True)
    aldeia = models.TextField(null=True, blank=True)


class Tf_6_1_1Projecttimeframe(models.Model):
    date_start_estimated = models.DateTimeField(null=True, blank=True)
    date_finish_estimated = models.DateTimeField(null=True, blank=True)


class Tf_6_1_1Projectdetails(models.Model):
    project_status = models.TextField(null=True, blank=True)
    project_sector = models.TextField(null=True, blank=True)
    project_subsector = models.TextField(null=True, blank=True)
    project_name = models.TextField(null=True, blank=True)
    objective = models.TextField(null=True, blank=True)
    gps_latitude = models.IntegerField(null=True, blank=True)
    gps_longitude = models.IntegerField(null=True, blank=True)
    is_women_priority = models.TextField(null=True, blank=True)


class Tf_6_1_1Projectbeneficiaries(models.Model):
    number_of_households = models.IntegerField(null=True, blank=True)
    no_of_women = models.IntegerField(null=True, blank=True)
    no_of_men = models.IntegerField(null=True, blank=True)
    disability_male = models.IntegerField(null=True, blank=True)
    disability_female = models.IntegerField(null=True, blank=True)


class Tf_6_1_1ProjectoutputRepeaterprojectoutput(models.Model):
    # This class is a Repeater: Parent and ordinality fields have been added"
    parent = models.ForeignKey("Tf_6_1_1Projectoutput", on_delete=models.CASCADE, related_name="repeaterProjectOutput")
    ordinality = models.IntegerField()
    uuid = models.UUIDField(editable=False, null=True, blank=True)


class Tf_6_1_1Projectoutput(models.Model):
    pass


class Tf_6_1_1(models.Model):
    meetinginformation = models.OneToOneField(Tf_6_1_1Meetinginformation, on_delete=models.CASCADE)
    projecttimeframe = models.OneToOneField(Tf_6_1_1Projecttimeframe, on_delete=models.CASCADE)
    projectdetails = models.OneToOneField(Tf_6_1_1Projectdetails, on_delete=models.CASCADE)
    projectbeneficiaries = models.OneToOneField(Tf_6_1_1Projectbeneficiaries, on_delete=models.CASCADE)
    projectoutput = models.OneToOneField(Tf_6_1_1Projectoutput, on_delete=models.CASCADE)


class Tf_6_1_1Meetinginformation(models.Model):
    district = models.TextField(null=True, blank=True)
    administrative_post = models.TextField(null=True, blank=True)
    suco = models.TextField(null=True, blank=True)
    aldeia = models.TextField(null=True, blank=True)


class Tf_6_1_1Projecttimeframe(models.Model):
    date_start_estimated = models.DateTimeField(null=True, blank=True)
    date_finish_estimated = models.DateTimeField(null=True, blank=True)


class Tf_6_1_1Projectdetails(models.Model):
    project_status = models.TextField(null=True, blank=True)
    project_sector = models.TextField(null=True, blank=True)
    project_subsector = models.TextField(null=True, blank=True)
    project_name = models.TextField(null=True, blank=True)
    objective = models.TextField(null=True, blank=True)
    gps_latitude = models.IntegerField(null=True, blank=True)
    gps_longitude = models.IntegerField(null=True, blank=True)
    is_women_priority = models.TextField(null=True, blank=True)


class Tf_6_1_1Projectbeneficiaries(models.Model):
    number_of_households = models.IntegerField(null=True, blank=True)
    no_of_women = models.IntegerField(null=True, blank=True)
    no_of_men = models.IntegerField(null=True, blank=True)
    disability_male = models.IntegerField(null=True, blank=True)
    disability_female = models.IntegerField(null=True, blank=True)


class Tf_6_1_1ProjectoutputRepeaterprojectoutput(models.Model):
    # This class is a Repeater: Parent and ordinality fields have been added"
    parent = models.ForeignKey("Tf_6_1_1Projectoutput", on_delete=models.CASCADE, related_name="repeaterProjectOutput")
    ordinality = models.IntegerField()
    uuid = models.UUIDField(editable=False, null=True, blank=True)


class Tf_6_1_1Projectoutput(models.Model):
    pass


class Tf_6_1_1ProjectoutputRepeaterprojectoutput(models.Model):
    # This class is a Repeater: Parent and ordinality fields have been added"
    parent = models.ForeignKey("Tf_6_1_1Projectoutput", on_delete=models.CASCADE, related_name="repeaterProjectOutput")
    ordinality = models.IntegerField()
    uuid = models.UUIDField(editable=False, null=True, blank=True)
