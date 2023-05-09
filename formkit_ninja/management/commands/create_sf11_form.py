from enum import Enum

from django.core.management.base import BaseCommand

from formkit_ninja import models
from formkit_ninja.formkit_schema import FormKitNode


class TrainingOrMeeting(Enum):
    Formasaun = 1
    Enkontru = 2


class MeetingTypes(Enum):
    SucoSocialisation = 1
    AldeaSocialisation = 2
    CMTelectionatsuco = 4
    AnnualGrantAgreementSigned = 11
    ProjectImplementationagreementsigned = 16
    Accountabilitymeeting1 = 17
    Districtsocialization = 20
    Subdistrictsocialization = 21
    CMTnominationataldeia = 22
    Prioritysettingataldeia = 23
    Prioritysettingatsuco = 24
    Accountabilitymeeting2 = 28
    PrioritysettingataldeiaWomen = 40


def partisipants_schema():
    """
    Create the "Partisipants" section
    """
    partisipants, created = models.FormKitSchema.objects.get_or_create(key="SF 1.1 Partisipants")
    yield partisipants, created
    # This is a dump from python code
    partisipants_group = {
        "children": [
            {
                "key": "attendance_male",
                "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 40 && $get(activity_subtype).value != 11",
                "id": "attendance_male",
                "name": "attendance_male",
                "label": "Total participants male",
                "validation": "greaterThanOrEqualSum:kpa_male+community_member_male",
                "validation-messages": {
                    "greaterThanOrEqualSum": "The total participants male should be greater than or equal to the sum of Participants Suku Management Team (SMT) - male and Number of community members - male"
                },
                "node_type": "formkit",
                "formkit": "number",
                "$formkit": "number",
                "min": 0,
            },
            {
                "key": "attendance_female",
                "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 11",
                "id": "attendance_female",
                "name": "attendance_female",
                "label": "Total participants female",
                "validation": "greaterThanOrEqualSum:kpa_female+community_member_female",
                "validation-messages": {
                    "greaterThanOrEqualSum": "The total participants female should be greater than or equal to the sum of Participants Suku Management Team (SMT) - female and Number of community members - female"
                },
                "node_type": "formkit",
                "formkit": "number",
                "$formkit": "number",
                "min": 0,
            },
            {
                "key": "kpa_male",
                "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 20 && $get(activity_subtype).value != 21 && $get(activity_subtype).value != 40 && $get(activity_subtype).value != 11",
                "id": "kpa_male",
                "name": "kpa_male",
                "label": "Participants Suku Management Team (SMT) - male",
                "node_type": "formkit",
                "formkit": "number",
                "$formkit": "number",
                "min": 0,
            },
            {
                "key": "kpa_female",
                "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 11 && $get(activity_subtype).value != 20 && $get(activity_subtype).value != 21",
                "id": "kpa_female",
                "name": "kpa_female",
                "label": "Participants Suku Management Team (SMT) - female",
                "node_type": "formkit",
                "formkit": "number",
                "$formkit": "number",
                "min": 0,
            },
            {
                "key": "disable_male",
                "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 40 && $get(activity_subtype).value != 11",
                "id": "disable_male",
                "name": "disable_male",
                "label": "Number of People with Disability - male",
                "node_type": "formkit",
                "formkit": "number",
                "$formkit": "number",
                "min": 0,
            },
            {
                "key": "disable_female",
                "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 11",
                "id": "disable_female",
                "name": "disable_female",
                "label": "Number of People with Disability - female",
                "node_type": "formkit",
                "formkit": "number",
                "$formkit": "number",
                "min": 0,
            },
            {
                "key": "community_member_male",
                "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 20 && $get(activity_subtype).value != 21 && $get(activity_subtype).value != 40 && $get(activity_subtype).value != 11",
                "id": "community_member_male",
                "name": "community_member_male",
                "label": "Number of community members - male",
                "node_type": "formkit",
                "formkit": "number",
                "$formkit": "number",
                "min": 0,
            },
            {
                "key": "community_member_female",
                "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 11 && $get(activity_subtype).value != 20 && $get(activity_subtype).value != 21",
                "id": "community_member_female",
                "name": "community_member_female",
                "label": "Number of community members - female",
                "node_type": "formkit",
                "formkit": "number",
                "$formkit": "number",
                "min": 0,
            },
        ],
        "name": "partisipants",
        "node_type": "formkit",
        "formkit": "group",
        "$formkit": "group",
    }

    for node in partisipants_group["children"]:
        node_from_fk = FormKitNode.parse_obj(node).__root__
        schema_node, schema_node_created = models.FormKitSchemaNode.objects.update_or_create(
            label=f"SF 1.1 partisipants ({node_from_fk.name})",
            node_type="$formkit",
            translation_context="partisipants",
            defaults=dict(node=node_from_fk.dict()),
        )
        yield schema_node, schema_node_created
        component, component_created = models.FormComponents.objects.update_or_create(
            defaults=dict(
                schema=partisipants,
                node=schema_node,
            ),
            label=f"SF 1.1 partisipants ({node_from_fk.name})",
        )
        yield component, component_created


def meeting_information_schema():
    """
    Create or recreate the SF 1.1 Meeting Information schema
    """

    meeting_information, mi_created = models.FormKitSchema.objects.get_or_create(key="SF 1.1 Meeting Information")
    yield meeting_information, mi_created
    activity_type, activity_type_created = models.FormKitSchemaNode.objects.update_or_create(
        label="SF 1.1 Activity Type",
        node_type="$formkit",
        defaults=dict(
            node={
                "key": "activity_type",
                "html_id": "activity_type",
                "name": "activity_type",
                "label": "Meeting or Training",
                "node_type": "formkit",
                "formkit": "select",
            }
        ),
    )
    yield activity_type, activity_type_created

    yield models.Option.objects.update_or_create(
        field=activity_type, value=str(TrainingOrMeeting.Formasaun.value), label="Training"
    )
    yield models.Option.objects.update_or_create(
        field=activity_type, value=str(TrainingOrMeeting.Enkontru.value), label="Meeting"
    )

    yield models.FormComponents.objects.update_or_create(
        defaults=dict(
            schema=meeting_information,
            node=activity_type,
        ),
        label="SF 1.1 Meeting Information (activity type)",
    )

    # The JSON code for the Subtype nodes

    activity_subtype = FormKitNode.parse_obj(
        {
            "key": "activity_subtype",
            "if_condition": f"$get(activity_type).value == '{TrainingOrMeeting.Formasaun.value}'",
            "html_id": "activity_subtype",
            "name": "activity_subtype",
            "label": "Training Type",
            "node_type": "formkit",
            "formkit": "select",
            "dollar_formkit": "select",
        }
    ).__root__

    options_activity_subtype_training = [
        {"value": "----", "label": ""},
        {"value": "41", "label": "Module UKL - UKL Verification Guideline"},
        {"value": "39", "label": "Module L -Monitoring O & M"},
        {"value": "32", "label": "Module E -Proposal Writing"},
        {"value": "31", "label": "Module C -Sf Orientation"},
        {"value": "38", "label": "Module K -Financial Management 3"},
        {"value": "37", "label": "Module J -Operations and Maintainance"},
        {"value": "36", "label": "Module I -Monitoring & Accountability"},
        {"value": "35", "label": "Module H -Financial Management 2"},
        {"value": "3", "label": "Module D -Financial Management 1"},
        {"value": "30", "label": "Module B -Womens Empowerment 1"},
        {"value": "29", "label": "Module A -Introduction & Planning"},
        {"value": "34", "label": "Module G -Managing Construction 1"},
        {"value": "33", "label": "Module F -Womens Empowerment 2"},
    ]

    activity_subtype_meetings = FormKitNode.parse_obj(
        {
            "key": "activity_subtype",
            "if_condition": f"$get(activity_type).value == '{TrainingOrMeeting.Enkontru.value}'",
            "html_id": "activity_subtype",
            "name": "activity_subtype",
            "label": "Meeting Type",
            "node_type": "formkit",
            "formkit": "select",
            "dollar_formkit": "select",
        }
    ).__root__
    options_activity_subtype_meeting = [
        {"value": "----", "label": ""},
        {"value": "22", "label": "CMT nomination at aldeia"},
        {"value": "2", "label": "Aldea Socialisation"},
        {"value": "4", "label": "CMT election at suco"},
        {"value": "11", "label": "Annual Grant Agreement Signed"},
        {"value": "16", "label": "Project Implementation agreement signed"},
        {"value": "17", "label": "Accountability meeting 1"},
        {"value": "20", "label": "District socialization"},
        {"value": "21", "label": "Sub-district socialization"},
        {"value": "1", "label": "Suco Socialisation"},
        {"value": "23", "label": "Priority setting at aldeia"},
        {"value": "24", "label": "Priority setting at suco"},
        {"value": "28", "label": "Accountability meeting 2"},
        {"value": "40", "label": "Priority setting at aldeia-Women"},
    ]

    activity_subtype_node, c = models.FormKitSchemaNode.objects.update_or_create(
        label="SF 1.1 Activity Sub-Type (Training)",
        node_type="$formkit",
        defaults=dict(translation_context="activitytype", node=activity_subtype.dict(exclude_none=True)),
    )
    yield activity_subtype_node, c

    for option in options_activity_subtype_training:
        yield models.Option.objects.get_or_create(field=activity_subtype_node, **option)

    activity_subtype_node_meetings, c = models.FormKitSchemaNode.objects.update_or_create(
        label="SF 1.1 Activity Sub-Type (Meeting)",
        node_type="$formkit",
        defaults=dict(translation_context="activitytype", node=activity_subtype_meetings.dict(exclude_none=True)),
    )
    yield activity_subtype_node_meetings, c

    for option in options_activity_subtype_meeting:
        yield models.Option.objects.get_or_create(field=activity_subtype_node_meetings, **option)


def create_sf11_locations():
    """
    This is a special "SF11 Locations" schema with additional conditions
    For these 'SF11' type forms, we add some conditions as described in our spreadsheet
    """
    locations_sf11, c = models.FormKitSchema.objects.get_or_create(key="SF 1.1 Locations")
    yield locations_sf11, c
    district, c = models.FormKitSchemaNode.objects.update_or_create(
        label="municipality",
        defaults=dict(
            node_type="$formkit",
            translation_context="municipality",
            node=dict(
                label="Municipality",
                html_id="municipality",
                name="municipality",
                key="municipality",
                formkit="select",
                options="$getLocations()",
            ),
        ),
    )
    yield district, c

    sf11_admin_post, c = models.FormKitSchemaNode.objects.get_or_create(
        label="Administrative Post select (SF 1.1 options)",
        defaults=dict(
            node_type="$formkit",
            translation_context="admin_post",
            node=dict(
                label="Administrative Post",
                html_id="admin_post",
                name="admin_post",
                key="admin_post",
                formkit="select",
                if_condition=" && ".join(
                    (
                        '$getLocations($get("municipality").value)',
                        f"get(activity_subtype).value !== '{MeetingTypes.Districtsocialization.value}'",
                    )
                ),
                options='$getLocations($get("municipality").value)',
            ),
        ),
    )
    yield sf11_admin_post, c

    sf11_suco, c = models.FormKitSchemaNode.objects.get_or_create(
        label="Suco select (SF 1.1 options)",
        defaults=dict(
            node_type="$formkit",
            translation_context="suco",
            node=dict(
                label="Suco",
                html_id="suco",
                name="suco",
                key="suco",
                formkit="select",
                if_condition=" && ".join(
                    (
                        '$getLocations($get("admin_post").value)',
                        f"get(activity_subtype).value !== '{MeetingTypes.Districtsocialization.value}'",
                        f"get(activity_subtype).value !== '{MeetingTypes.Subdistrictsocialization.value}'",
                    )
                ),
                options='$getLocations($get("municipality").value, $get("admin_post").value)',
            ),
        ),
    )
    yield sf11_suco, c

    sf11_aldeia, c = models.FormKitSchemaNode.objects.get_or_create(
        label="Aldeia select (SF 1.1 options)",
        defaults=dict(
            node_type="$formkit",
            translation_context="aldeia",
            node=dict(
                label="Aldeia",
                html_id="aldeia",
                name="aldeia",
                key="aldeia",
                formkit="select",
                if_condition=" && ".join(
                    [
                        '$getLocations($get("suco").value)',  # Has a suco value,
                        *[
                            f"get(activity_subtype).value !== '{item.value}'"
                            for item in [
                                MeetingTypes.Districtsocialization,
                                MeetingTypes.Subdistrictsocialization,
                                MeetingTypes.SucoSocialisation,
                                MeetingTypes.Prioritysettingatsuco,
                                MeetingTypes.CMTelectionatsuco,
                                MeetingTypes.AnnualGrantAgreementSigned,
                                MeetingTypes.ProjectImplementationagreementsigned,
                                MeetingTypes.Accountabilitymeeting1,
                                MeetingTypes.Accountabilitymeeting2,
                            ]
                        ],
                    ]
                ),
                options='$getLocations($get("municipality").value, $get("admin_post").value, $get("suco").value)',
            ),
        ),
    )
    yield sf11_aldeia, c

    yield models.FormComponents.objects.update_or_create(
        defaults=dict(
            schema=locations_sf11,
            node=district,
        ),
        label="Municipalities for the SF 1.1 Location Select schema",
    )

    yield models.FormComponents.objects.update_or_create(
        label="Administrative Posts for the SF 1.1 Location Select schema",
        defaults=dict(
            schema=locations_sf11,
            node=sf11_admin_post,
        ),
    )

    yield models.FormComponents.objects.update_or_create(
        defaults=dict(
            schema=locations_sf11,
            node=sf11_suco,
        ),
        label="Suco for the SF 1.1 Location Select schema",
    )

    yield models.FormComponents.objects.update_or_create(
        label="Aldeias for the for SF 1.1 Location Select schema",
        defaults=dict(
            schema=locations_sf11,
            node=sf11_aldeia,
        ),
    )


class Command(BaseCommand):
    help = """
        Create the Partisipa 'SF11' form
        as a set of Django models / FormKit integration
    """

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Writing Partisipants schema"))
        for instance, created in partisipants_schema():
            if options["verbosity"] > 1:
                self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} {instance}"))

        self.stdout.write(self.style.SUCCESS("Writing Meeting Information schema"))
        for instance, created in meeting_information_schema():
            if options["verbosity"] > 1:
                self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} {instance}"))

        self.stdout.write(self.style.SUCCESS("Writing Locations schema for SF 11"))
        for instance, created in create_sf11_locations():
            if options["verbosity"] > 1:
                self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} {instance}"))

        # Update / Create translated content hooks for "labels" and "options"
        for instance, created in models.FormKitSchemaNode.translatable_content():
            if options["verbosity"] > 1:
                self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} {instance}"))
