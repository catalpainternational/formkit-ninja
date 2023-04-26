from django.core.management.base import BaseCommand

from formkit_ninja.management.commands.common_nodes import create_location_nodes


def create():

    # The SF 13 form has the following schemas
    # meetingInformation
    # participants
    # projectteam
    # planning
    # sukus

    # The SF 13 form has the following components
    # For 'meeting information':
    # municipality
    # adminpost
    # sucos
    # date

    # For 'partisipants':
    # suku_comittee_member_female
    # suku_committee_member_male
    # community_member_female
    # community_member_male
    # participants_with_disability_female
    # participants_with_disability_male

    # For 'projectteam':
    # A 'repeater' (ooh, fancy!)
    # with lots of nested children, aargh
    ...


class Command(BaseCommand):
    help = """
        Create the Partisipa 'SF13' form
        as a set of Django models / FormKit integration
    """

    def handle(self, *args, **options):
        for instance, created in create_location_nodes():
            if options["verbosity"] > 1:
                self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} {instance}"))
        for instance, created in create():
            if options["verbosity"] > 1:
                self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} {instance}"))
