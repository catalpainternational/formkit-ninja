"""Signals an application sends to record what its importer did.

These are a rendezvous point, not a notification this library emits. Only the
application knows whether populating its own typed model from a
``SeparatedSubmission`` succeeded, so the application sends these and
:mod:`formkit_ninja.form_submission.import_monitoring` receives them and writes
the ``SeparatedSubmissionImport`` row that the import-status queryset methods and
the admin columns read.

Sending them is optional; the split works either way.
"""

from django.dispatch import Signal

#: Sent by the application when its importer populated a model from a
#: ``SeparatedSubmission``. Provides: ``instance``, ``model_instance``, ``was_created``.
import_success = Signal()

#: Sent by the application when its importer raised while doing so.
#: Provides: ``instance``, ``error``.
import_error = Signal()
