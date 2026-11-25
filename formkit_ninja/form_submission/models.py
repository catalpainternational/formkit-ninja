from __future__ import annotations

import json
import logging
import uuid
import warnings
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import fields as dataclass_fields
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, cast

import pghistory
import pgtrigger
from django.apps import apps
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, router, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from formkit_ninja.form_submission.compat import RepeaterOrderDescriptor, warn_on_write
from formkit_ninja.form_submission.emit import Emission, emit_submission
from formkit_ninja.form_submission.ordering import plan_ranks
from formkit_ninja.form_submission.querysets import SeparatedSubmissionQuerySet, SubmissionQuerySet
from formkit_ninja.form_submission.utils import (
    ensure_repeater_uuid,
    pre_validation,
    sibling_groups,
)

if TYPE_CHECKING:
    from formkit_ninja.form_submission.events import SubmissionEvent, SubmissionState

logger = logging.getLogger(__name__)


@contextmanager
def immediate_constraints():
    """
    Context manager for handling atomic transactions in the database
    with constraints set to `immediate`. This prevents an error being
    raised later, potentially very far from the source and hard
    to track down.
    """
    with transaction.atomic():
        conn = transaction.get_connection()
        with conn.cursor() as c:
            # Temporarily set all constraints to 'IMMEDIATE' in order to not have 'Foreign Key'
            # errors which we'll catch in outer scope later
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")
        yield


class SubmissionField(models.JSONField):
    def pre_save(self, model_instance: models.Model, add):  # type: ignore[override]
        value = getattr(model_instance, self.attname)
        validated = pre_validation(value)
        # Ensure that all repeaters have a UUID set on save
        try:
            from formkit_ninja.form_submission.utils import get_repeaters

            for repeater_key in get_repeaters(validated):
                try:
                    validated[repeater_key] = list(ensure_repeater_uuid(validated, repeater_key))
                except TypeError as E:
                    warnings.warn(f"{E} (received {validated[repeater_key]})")
        except LookupError as E:
            warnings.warn(f"{E}")
        # After the uuids exist, so a normalisation inside a repeater can name its row.
        from formkit_ninja.form_submission.normalise import normalise

        result = normalise(getattr(model_instance, "form_type", ""), validated)
        validated = result.fields
        # Handed to the recording save of this submission, if one is running; a write that skips
        # save() (bulk_create, bulk_update) has nothing to record them in.
        pending = _writes_in_progress.get().get(str(model_instance.pk))
        if pending is not None:
            pending.extend(result.normalisations)
        setattr(model_instance, self.attname, validated)
        return validated


def _compared(state: SubmissionState) -> dict[str, Any]:
    """The parts of ``state`` that ``==`` compares (everything but ``schema_version``)."""
    return {f.name: getattr(state, f.name) for f in dataclass_fields(state) if f.compare}


#: The submissions (by key) whose ``save()`` or ``delete()`` is recording right now in this thread or
#: task, each with the normalisations its writes have made and the labels its receivers have given so far.
#: See ``Submission._record_write``.
_writes_in_progress: ContextVar[Mapping[str, list]] = ContextVar("formkit_ninja_submission_writes_in_progress", default={})


# Deletes are tracked explicitly. django-pghistory 3.x defaults to
# ``(InsertEvent(), UpdateEvent())`` when ``track()`` is called with no arguments — 2.x
# included deletes — so a bare decorator silently stopped recording them at the 3.0 upgrade.
# A hard delete is exactly the event an audit trail exists for: without this, a deleted
# submission leaves its content in the event table and nothing at all to say it is gone.
@pghistory.track(pghistory.InsertEvent(), pghistory.UpdateEvent(), pghistory.DeleteEvent())
class Submission(models.Model):
    class Status(models.IntegerChoices):
        NEW = 1, _("New Submission")
        REJECTED = 2, _("Rejected")
        VERIFIED = 3, _("Verified")
        CHANGES_REQUESTED = 4, _("Changes Requested")

    key = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created = models.DateTimeField(default=timezone.now)
    updated = models.DateTimeField(default=timezone.now)
    status = models.IntegerField(
        choices=Status.choices,
        default=Status.NEW,
    )
    fields = SubmissionField(encoder=DjangoJSONEncoder)
    form_type = models.CharField(
        max_length=128,
        help_text="The type of form used in the submission",
    )
    is_active = models.BooleanField(default=True)

    objects = SubmissionQuerySet.as_manager()

    #: The events the ``save()`` or ``delete()`` last called on this instance recorded, in order; an empty
    #: list when it changed nothing. Not set until one of them runs. See ``_record_write``.
    recorded_events: list[SubmissionEvent]

    class Meta:
        triggers = [
            # ``SeparatedSubmission.status`` is a denormalised mirror of this root
            # status. ``from_submission()`` keeps it current whenever the consumer
            # runs a split, but status changes that never trigger one — bulk
            # ``.update(status=…)``, restores, raw SQL — would otherwise leave the
            # mirror stale. This trigger enforces the invariant for every write path,
            # so any consumer reading ``SeparatedSubmission.status`` can trust it.
            # It writes a *different* table, so there is no recursion.
            pgtrigger.Trigger(
                name="sync_separated_submission_status",
                when=pgtrigger.After,
                operation=pgtrigger.Update,
                condition=pgtrigger.Q(old__status__df=pgtrigger.F("new__status")),
                func=pgtrigger.Func(
                    """
                    UPDATE formkit_ninja_separatedsubmission
                    SET status = NEW.status
                    WHERE submission_id = NEW.key
                      AND status IS DISTINCT FROM NEW.status;
                    RETURN NEW;
                    """
                ),
            ),
        ]

    def save(self, *args, **kwargs):
        """
        Persist the submission. **This does not split it.**

        Deriving the flattened ``SeparatedSubmission`` rows is the consumer's
        responsibility — call ``SeparatedSubmission.objects.from_submission(sub)``
        yourself, typically from a ``post_save`` receiver on this model.

        Nothing is derived until something calls it — see "Wiring the split" in
        docs/submission_architecture.md. Removed in 2.5.4 / 3.0.0; CHANGELOG.md
        has the rationale.

        It does record what changed: the stored row is read (and locked) first, and the
        events between it and this save go to the configured sink in the same transaction
        (``form_submission.sinks``). Writes that skip this method record nothing:
        ``QuerySet.update()``, ``bulk_create``, ``bulk_update``, the owner being set to null when
        their user is deleted (the foreign key's ``SET_NULL``), and raw SQL. After one of them the
        events no longer fold to the row, and nothing raises to say so; call
        ``form_submission.sinks.record_reset`` for each submission it touched. This method cannot
        notice the gap itself, because it never reads the history. ``QuerySet.delete()`` is
        recorded, by ``SubmissionQuerySet.delete``.

        The row is read back after the write, rather than taken from this instance, because the
        database decides the stored value: Postgres turns ``1e16`` into an integer and has no
        negative zero. An event built from the instance would replay to a different answer than
        the one stored.
        """
        using = kwargs["using"] = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        if self.pk is None:
            # Django would give it the default inside the write; give it now so the key is known.
            self.pk = type(self)._meta.pk.get_default()
        self._record_write(using, lambda: super(Submission, self).save(*args, **kwargs))

    @classmethod
    def write_state(cls, state: SubmissionState, *, using: str | None = None) -> Submission:
        """Store ``state`` as the submission and record no event; returns the stored submission.

        For an application that appends a submission's events to its own log first and derives the
        submission from them: ``state`` is the ``fold`` of those events. The write goes through
        ``save()``, so empty answers are dropped, repeater rows get their ``uuid``, the normaliser runs
        and ``post_save`` receivers (such as the consumer's split) fire as usual; only the recording
        is skipped, since the events are already in the log. A later ordinary ``save()`` records from
        the stored row as usual, so the application's events followed by the recorded ones, in order,
        still fold to the row.

        The row is read back after the write and compared with ``state`` as JSON, so 1, 1.0 and
        ``True`` are different answers. If they differ (an empty answer was dropped, a row had no
        ``uuid``, the normaliser changed an answer or its type, the key was not in its canonical
        form), the write is rolled back and ``ValueError`` is raised: the stored submission would no
        longer be the fold of the log. Fold events of stored answers, not answers as the form sent
        them. ``ValueError`` is raised too when this submission is already being recorded by a
        ``save()`` or ``delete()`` further up the stack, which would otherwise record this write as
        its own change. ``schema_version`` is not stored, and a deleted submission (a fold of
        ``None``) is not written here.
        """
        from formkit_ninja.form_submission.events import SubmissionState, _same

        using = using or router.db_for_write(cls)
        in_progress = _writes_in_progress.get()
        if state.key in in_progress:
            raise ValueError(f"submission {state.key} is being recorded by a save or delete further up the stack; write its state after that finishes")
        with transaction.atomic(using=using):
            # Marked as already recording, so save() writes without recording.
            token = _writes_in_progress.set({**in_progress, state.key: []})
            try:
                rows = cls.objects.using(using)
                sub = rows.select_for_update().filter(pk=state.key).first() or cls(pk=state.key)
                sub.form_type = state.form_type
                sub.fields = state.fields
                sub.status = state.status
                sub.is_active = state.is_active
                sub.user_id = state.owner
                sub.save(using=using)
            finally:
                _writes_in_progress.reset(token)
            written = rows.get(pk=state.key)
            stored = SubmissionState.of(written)
            if not _same(_compared(stored), _compared(state)):
                raise ValueError(f"submission {state.key}: saving stored {stored!r}, which is not the state it was given ({state!r})")
        return written

    def label_edit(self, path: tuple[str, ...], label: str) -> None:
        """Record that a receiver rewrote the answer at ``path`` during this save, and why (``label``).

        For an application's ``pre_save`` receiver that changes an answer: the create or edit event
        the save records lists ``{path, label}`` under ``labelled``, so the change does not read as
        the person's own. ``path`` is written as for a normalisation (the answer's key, prefixed by
        ``(repeater key, row uuid)`` for each repeater it sits in). Only labels whose value
        differs between the stored row before and after the save are listed, so labelling an answer
        that ends up unchanged lists nothing; ``path`` may also end at a row's uuid, or be just the
        repeater's key, to label a whole row or table (rows removed or reordered). Call it from a
        receiver while the save runs: called before ``save()``, or outside a recorded save (``loaddata``,
        ``write_state``), it is dropped. Label only when your own write changed the value: a label
        matches the answer, not who set it, so labelling an answer the person also set in the same save
        labels theirs. A row the person adds in the same save has no ``uuid`` yet when ``pre_save``
        receivers run, so it cannot be named.
        """
        from formkit_ninja.form_submission.events import LabelledEdit

        if not isinstance(label, str):
            raise TypeError(f"a label_edit label must be text, got {label!r}")
        if not label:
            raise ValueError("a label_edit label must not be empty")
        if isinstance(path, str):
            raise TypeError(f"a label_edit path is a tuple of keys, got the text {path!r}")
        parts = tuple(path)
        if not all(isinstance(part, str) for part in parts):
            raise TypeError(f"a label_edit path must hold only text, got {parts!r}")
        if not parts:
            raise ValueError("a label_edit path must not be empty")
        pending = _writes_in_progress.get().get(str(self.pk))
        if pending is not None:
            pending.append(LabelledEdit(parts, label))

    def roll_back_to(self, events: Iterable[Mapping[str, Any]], event_id: str) -> None:
        """Save this submission with its answers as they were just after ``event_id``, recorded as a new edit if they differ.

        Only the answers go back: the stored row is read (and locked) and only its answers are changed,
        so its status, owner and whether it is active stay as they are stored now, even if this
        instance is out of date or holds unsaved changes; undoing an answer does not undo a
        verification or bring back a removed submission. Afterwards this instance is read again from
        the row.
        ``events`` is this submission's history, oldest first (from the configured sink's store, or
        the application's own). The version after ``event_id`` is worked out with ``fold_versions``
        and its answers saved through ``save()``, under ``context(rolled_back_to=event_id)``, so the
        change back is recorded as an edit like any other and the versions in between stay in the
        history. Because it is a save, the normaliser and the application's receivers run again; if
        the stored answers then differ from that version's (a rule changed since, say), the save is
        rolled back and ``ValueError`` raised (a sink that does not write in the same transaction has
        already been given the events by then). So is one for an event not in ``events``, events of
        another submission, a version whose state is not known (``STATE_UNKNOWN``), a version in
        which the submission was deleted (that is a ``delete()``), a submission whose row has been
        deleted since, and one whose form type has changed since that version, as its old answers
        belong to the other form. Afterwards
        ``recorded_events`` on this instance lists what the rollback recorded (empty if the answers were already those).
        After a refusal this instance is left as it was.
        Called from a receiver during a save of the same submission, the rollback's save records nothing of its own:
        the outer save records the whole change as one plain edit, without ``rolled_back_to``, and ``recorded_events``
        on this instance is left as it was.
        """
        from formkit_ninja.form_submission.events import SubmissionState, _same, _Unknown, context, fold_versions

        events = list(events)
        if any(str(event.get("submission")) != str(self.pk) for event in events):
            raise ValueError(f"cannot roll submission {self.pk} back with events of another submission")
        versions = [state for event, state in fold_versions(events) if event.get("event_id") == event_id]
        if not versions:
            raise ValueError(f"event {event_id} is not in the history of submission {self.pk}")
        target = versions[0]
        if isinstance(target, _Unknown):
            raise ValueError(f"submission {self.pk} after event {event_id} is not known (an earlier write skipped save()), so it cannot be rolled back to")
        if target is None:
            raise ValueError(f"submission {self.pk} was deleted after event {event_id}; delete it rather than roll back to it")
        using = router.db_for_write(type(self), instance=self)
        rows = type(self).objects.using(using)
        with transaction.atomic(using=using):
            # The stored row, not this instance: only the answers go back, whatever this instance holds.
            row = rows.select_for_update().filter(pk=self.pk).first()
            if row is None:
                raise ValueError(f"submission {self.pk} no longer exists (it was deleted), so it is not rolled back")
            if row.form_type != target.form_type:
                raise ValueError(f"submission {self.pk} has the form type {row.form_type!r} now, not {target.form_type!r} as after event {event_id}, so that version's answers are not rolled back to")
            row.fields = deepcopy(target.fields)
            with context(rolled_back_to=event_id):
                row.save(using=using)
            stored = SubmissionState.of(rows.get(pk=self.pk))
            if not _same(stored.fields, target.fields):
                raise ValueError(f"submission {self.pk}: saving stored the answers {stored.fields!r}, which are not the version after event {event_id} ({target.fields!r})")
        self.refresh_from_db(using=using)
        # The save ran on ``row``, so this instance gets its list (empty when nothing changed). Inside a save
        # of this submission there is none: the outer save records everything, and this instance is left as it was.
        if "recorded_events" in row.__dict__:
            self.recorded_events = row.recorded_events

    def delete(self, *args, **kwargs):
        """Delete the submission and record ``submission:delete`` in the same transaction."""
        using = kwargs["using"] = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        return self._record_write(using, lambda: super(Submission, self).delete(*args, **kwargs))

    def _record_write(self, using: str, write: Callable[[], Any]) -> Any:
        """Run ``write`` and record the events between the stored row before it and after it.

        A write of this submission made while another is recording it, typically a ``post_save``
        or ``post_delete`` receiver saving or deleting the same submission, records nothing itself.
        It runs inside the outer write's transaction, so recording it there would put its events
        before the outer write's, which ``fold`` cannot replay. The outermost write reads the row
        back after everything inside it has run and records prior-to-final once, with the
        normalisations and labels of every save in between. A write of a different submission records as usual.

        The events recorded are kept on this instance as ``recorded_events``, so an application can
        tell straight after ``save()`` that nothing changed (an empty list). A write that records
        nothing itself, as above, leaves the attribute as it was; one that raises leaves it unset.
        """
        from formkit_ninja.form_submission.events import LabelledEdit, SubmissionState
        from formkit_ninja.form_submission.sinks import record_events

        key, pk = str(self.pk), self.pk
        in_progress = _writes_in_progress.get()
        if key in in_progress:
            return write()
        notes: list = []  # normalisations and labels, in the order they were made
        # So a write that raises leaves no list from an earlier one.
        self.__dict__.pop("recorded_events", None)
        with transaction.atomic(using=using):
            # Cleared inside the block: Django runs ``on_commit`` callbacks as the block commits, and a
            # save of this submission from one of them must record as a write of its own.
            token = _writes_in_progress.set({**in_progress, key: notes})
            try:
                rows = type(self).objects.using(using)
                stored = rows.select_for_update().filter(pk=pk).first()
                result = write()
                after = rows.filter(pk=pk).first()
                events = record_events(
                    SubmissionState.of(stored) if stored is not None else None,
                    SubmissionState.of(after) if after is not None else None,
                    normalisations=[n for n in notes if not isinstance(n, LabelledEdit)],
                    labels=[n for n in notes if isinstance(n, LabelledEdit)],
                )
            finally:
                _writes_in_progress.reset(token)
        # After the block, so a save of this instance from an ``on_commit`` callback cannot replace it.
        self.recorded_events = events
        return result

    def __str__(self) -> str:
        # Use only local fields to avoid N+1 (e.g. admin list).
        return f"{self.form_type} {self.key} ({self.get_status_display()})"


def _normalize_json(value) -> str:
    """
    Canonical string form of a JSON value for change detection.

    The stored ``SeparatedSubmission.fields`` is JSON round-tripped through
    ``DjangoJSONEncoder`` (Decimals/UUIDs/datetimes become strings, key order is
    arbitrary), while a freshly-computed ``defaults["fields"]`` is a raw Python
    dict that can still hold ``UUID``/``Decimal``/``datetime`` objects (e.g.
    ``ensure_object_has_uuid`` injects ``uuid.uuid4()`` objects). Dumping both
    through the same encoder with sorted keys reproduces the exact stored
    representation, so equal content compares equal and there are no false
    "changed"/"unchanged" verdicts.
    """
    return json.dumps(value, sort_keys=True, cls=DjangoJSONEncoder)


class _SeparatedSubmissionManagerBase(models.Manager):
    """Base manager with custom creation methods for SeparatedSubmission."""

    def _apply_defaults(self, pk: uuid.UUID | str, defaults: dict[str, Any], *, force: bool, rows: dict[str, "SeparatedSubmission"] | None = None) -> tuple["SeparatedSubmission", bool, bool]:
        """
        Change-aware upsert of one ``SeparatedSubmission`` row.

        Like ``update_or_create(pk=pk, defaults=defaults)`` but only calls
        ``.save()`` when the computed ``defaults`` actually differ from the
        stored row (or when ``force`` is set), so an unchanged row fires no
        ``post_save`` and no downstream projection cascade.

        ``rows`` is the one-read-per-save map ``from_submission`` builds: when
        given, it is authoritative and no per-row query runs (the split used to
        read every row back one query at a time — Partisipa measured it at 59%
        of an import's time).

        Returns ``(instance, created, changed)`` where ``changed`` reflects the
        real content diff, independent of ``force``.
        """
        if rows is not None:
            obj = rows.get(str(pk))
        else:
            obj = SeparatedSubmission.objects.filter(pk=pk).first()
        if obj is None:
            return SeparatedSubmission.objects.create(pk=pk, **defaults), True, True

        changed = False
        for name, value in defaults.items():
            field = cast(models.Field, SeparatedSubmission._meta.get_field(name))
            if field.is_relation:
                stored = getattr(obj, field.attname)
                new = value.pk if value is not None else None
                differs = stored != new
            elif name == "fields":
                differs = _normalize_json(getattr(obj, name)) != _normalize_json(value)
            else:
                differs = getattr(obj, name) != value
            if differs:
                setattr(obj, name, value)
                changed = True

        if force and not changed:
            # Forced re-touch: re-apply every default so the write matches the
            # old unconditional-upsert semantics (self-heals stale rows).
            for name, value in defaults.items():
                setattr(obj, name, value)

        if changed or force:
            obj.save()

        return obj, False, changed

    @transaction.atomic()
    def from_submission(self, sub: Submission, *, force: bool = False) -> list[tuple[SeparatedSubmission, bool, bool]]:
        """
        Create SeparatedSubmission(s) from one Submission.

        Change-aware by default: rows whose computed values are byte-identical
        to what is already stored are not re-saved, so no ``post_save`` (and no
        downstream projection cascade) fires for them. Pass ``force=True`` to
        restore the old unconditional re-touch (self-healing for consumers that
        rely on every save repairing stale derived rows).

        Returns a list of ``(instance, created, changed)`` tuples.
        """
        # One decomposition, shared with the event emitter. `emit_submission`
        # returns the root first and then every repeater row parent-before-child,
        # which is the order the writes below need and the order a replay will
        # apply them in — so the rows a log produces and the rows a document
        # produces cannot drift apart.
        emissions = emit_submission(sub)
        root = emissions[0]

        # Every row this document can hold, read back in one query instead of one
        # query per row. Rows written below are added as they are made, so a child
        # resolves its parent from this map without touching the database again.
        rows: dict[str, SeparatedSubmission] = {str(obj.pk): obj for obj in SeparatedSubmission.objects.filter(pk__in=[sub.pk, *(e.row_id for e in emissions[1:])])}

        main, main_created, main_changed = self._apply_defaults(
            sub.pk,
            dict(
                submission=sub,
                user=sub.user,
                created=sub.created,
                status=sub.status,
                fields=root.fields,
                form_type=sub.form_type,
            ),
            force=force,
            rows=rows,
        )
        rows[str(main.pk)] = main

        # Positions for the repeater rows, worked out once for the whole document.
        # Only the rows that actually moved get a new key; everything else is handed
        # back the key it already holds, so `_apply_defaults` sees no difference and
        # does not write. This is what makes a re-order cost one row instead of every
        # row whose array index shifted.
        ranks = self._plan_repeater_ranks(sub, main.pk)

        results: list[tuple[SeparatedSubmission, bool, bool]] = []

        # Track every row we (re)write so we can reconcile away orphans below.
        # A skipped (unchanged) row still returns a result, so it stays in
        # ``written_pks`` and survives the orphan sweep.
        written_pks: set = {main.pk}

        for emission in emissions[1:]:
            res = self.apply_emission(emission, main, rank=ranks.get(emission.row_id), force=force, rows=rows)
            if res:
                results.append(res)
                written_pks.add(res[0].pk)
                rows[str(res[0].pk)] = res[0]

        results.append((main, main_created, main_changed))  # type: ignore[arg-type]

        # Reconcile away orphaned derived rows (#2252).
        #
        # ``from_submission`` upserts one SeparatedSubmission per repeater-row
        # uuid. When a row's uuid changes or disappears from canonical
        # ``Submission.fields`` (web-form round-trip dropping/regenerating uuid,
        # flat<->repeater migrations, string->Decimal retypes, imports bypassing
        # save), the old derived row was historically left behind forever. Those
        # phantom rows are invisible in canonical fields but ARE served by the
        # derived-model endpoints, so they double-count in cumulative aggregates.
        #
        # The valid set is exactly the rows we just wrote (root + every repeater
        # row at every nesting depth, since ``flatten`` recurses). Deleting the
        # rest is stateless and self-healing — a no-op once consistent — and
        # cascades to child rows and their dependent Import/Flag rows.
        self.filter(submission=sub).exclude(pk__in=written_pks).delete()

        return results

    def _plan_repeater_ranks(self, sub: Submission, root_pk: uuid.UUID) -> dict[str, str | None]:
        """The ``repeater_rank`` every child row should hold after this save.

        Returns a key for *every* child, not just the moved ones: the keys that did not
        move map to the value already stored, so ``_apply_defaults`` compares equal and
        skips the write. Handing back only the changes would set the rest to ``None``
        and wipe the column on every save.

        Ranks are planned per sibling group — one repeater on one parent — because a
        rank is only meaningful against its siblings. A parent carrying two repeaters
        has two independent orderings.
        """
        stored: dict[str, str | None] = {str(pk): rank for pk, rank in SeparatedSubmission.objects.filter(submission=sub).values_list("pk", "repeater_rank")}

        planned: dict[str, str | None] = {}
        for now in sibling_groups(sub.fields, root_pk, sub.form_type).values():
            planned.update({child_uuid: stored.get(child_uuid) for child_uuid in now})
            planned.update(plan_ranks(now, stored))
        return planned

    def apply_emission(
        self, emission: Emission, main: SeparatedSubmission, *, rank: str | None = None, force: bool = False, rows: dict[str, "SeparatedSubmission"] | None = None
    ) -> tuple["SeparatedSubmission", bool, bool] | None:
        """Upsert the derived row one :class:`~formkit_ninja.form_submission.emit.Emission` describes.

        The projection half of the decomposition: ``emit_submission`` says what
        rows a document contains, and this writes one of them. Splitting the two
        is what lets the same rows be produced from a document today and from a
        log later — the writing half does not care which.

        Returns ``None`` for the root emission, which ``from_submission`` has
        already written as the anchor every child hangs from.

        ``rank`` is passed in rather than read off the emission because the
        canonical document does not carry one yet; once it does, this argument
        goes away and ``emission.rank`` is used directly.
        """
        if emission.is_root:
            return None

        # Resolve parent. A child naming a parent that is not there is a damaged
        # document, not a reason to lose the row: it is re-parented to the root
        # and the fact is reported, which is what the splitter has always done.
        parent_obj = main
        if emission.parent_id and emission.parent_id != str(main.pk):
            # Emissions come parent-before-child, so a live parent is already in
            # ``rows``; the query is only for a parent outside this document.
            found = rows.get(str(emission.parent_id)) if rows is not None else None
            if found is None:
                found = SeparatedSubmission.objects.filter(pk=emission.parent_id).first()
            if found is not None:
                parent_obj = found
            else:
                warnings.warn(f"Parent {emission.parent_id} not found for {emission.repeater_key}")

        return self._apply_defaults(
            emission.row_id,
            dict(
                status=main.status,
                submission=main.submission,
                form_type=emission.form_type,
                user=main.user,
                fields=emission.fields,
                repeater_parent=parent_obj,
                repeater_key=emission.repeater_key,
                repeater_rank=rank,
            ),
            force=force,
            rows=rows,
        )


# Combine custom manager methods with queryset annotation methods
SeparatedSubmissionManager = _SeparatedSubmissionManagerBase.from_queryset(SeparatedSubmissionQuerySet)


# Deletes tracked for the same reason as ``Submission`` above, and it matters more here:
# these rows are removed on paths a user never sees — the orphan reconcile inside
# ``from_submission``, and the cascade from deleting a canonical submission.
@pghistory.track(pghistory.InsertEvent(), pghistory.UpdateEvent(), pghistory.DeleteEvent())
class SeparatedSubmission(models.Model):
    """
    This represents a Submission broken down into the main
    submission instance and separate repeaters
    """

    def __init__(self, *args, **kwargs):
        # `repeater_order=` used to be a real field. Django would raise TypeError for it
        # now — an unhelpful death for a value that had nowhere to go even before the
        # drop, since the splitter recomputed it on every save.
        if "repeater_order" in kwargs:
            warn_on_write(kwargs.pop("repeater_order"))
        super().__init__(*args, **kwargs)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created = models.DateTimeField(default=timezone.now)
    status = models.IntegerField(choices=Submission.Status.choices, default=Submission.Status.NEW)
    fields = models.JSONField(encoder=DjangoJSONEncoder)
    form_type = models.CharField(
        max_length=256,
        help_text="The type of form used in the submission",
    )

    # These fields are relevant for 'Repeaters' to reference the parent object
    repeater_key = models.CharField(
        max_length=256,
        help_text="The field name in the original JSON document",
        null=True,
        blank=True,
    )
    repeater_parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="repeater_set")
    #: Removed as a column in #74 — it was the rank's position within the sibling group,
    #: counted, and a dense index is what made moving one row cost a write per row it
    #: passed. Still readable on an instance, and still annotatable onto a queryset by
    #: `with_repeater_order()`; both warn. See `form_submission/compat.py`.
    repeater_order = RepeaterOrderDescriptor()
    #: A base-62 fractional index (``formkit_ninja.fracrank``) giving this row a position
    #: that can be changed without touching the rows either side of it. ``db_collation="C"``
    #: is load-bearing: the keys are compared as **bytes** in Python, and Postgres' default
    #: en_US.UTF-8 collation is not byte order, so without it SQL and Python disagree about
    #: order — silently. ``tests/test_fracrank_storage.py`` is the guard.
    #:
    #: Nullable, and null on every row until the backfill runs, so
    #: ``in_document_order()`` falls back to ``repeater_order``. Never serialise it to a
    #: JavaScript client: ``Number("a0V")`` is ``NaN``, which sorts the list arbitrarily
    #: with no error.
    repeater_rank = models.TextField(
        null=True,
        blank=True,
        db_collation="C",
        help_text="Fractional index position of this repeater row within its sibling group",
    )
    submission = models.ForeignKey(
        Submission,
        help_text="The original submission.",
        on_delete=models.CASCADE,
    )

    objects = SeparatedSubmissionManager()

    @property
    def model_type(self) -> type[models.Model] | None:
        """
        Return the corresponding Django model.
        """
        # Strategy: Search all installed apps for a model with matching name (case insensitive?)
        # Or exact match.
        # The 'form_type' in SeparatedSubmission is capitalized in the Manager logic.

        target_name = self.form_type

        # Prioritize 'formkit_ninja' or apps defined in setting?
        # For now, search all.
        for app_config in apps.get_app_configs():
            try:
                model = app_config.get_model(target_name)
                if model:
                    return model
            except LookupError:
                continue

        # Fallback: maybe the capitalization differs?
        # TODO: Implement fuzzy matching?
        return None

    # to_model removed in favor of generated signals

    def __str__(self) -> str:
        # Use only local fields to avoid N+1 (submission_id would also be local).
        return f"{self.form_type} {self.id} ({self.get_status_display()})"


class SubmissionFile(models.Model):
    submission = models.UUIDField()
    file = models.FileField(upload_to="submission_files")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    comment = models.TextField()
    date_uploaded = models.DateTimeField(default=timezone.now)
    deleted = models.BooleanField(default=False)

    class Meta:
        triggers = [pgtrigger.SoftDelete(name="soft_delete", field="deleted", value=True)]

    def __str__(self) -> str:
        return f"File for submission {self.submission}" if self.pk else "SubmissionFile (unsaved)"


class SubmissionEventRecord(models.Model):
    """One submission event, stored by the default sink (``form_submission.sinks.TableSink``).

    Append-only: a database trigger refuses updates and deletes. ``submission`` is a plain UUID,
    not a foreign key, so a deleted submission's history stays.
    """

    event_id = models.UUIDField(unique=True)
    type = models.CharField(max_length=32)
    submission = models.UUIDField(db_index=True)
    form_type = models.CharField(max_length=128)
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    #: The whole event, exactly as ``form_submission.events`` built it.
    event = models.JSONField(encoder=DjangoJSONEncoder)

    class Meta:
        ordering = ["id"]
        triggers = [pgtrigger.Protect(name="append_only", operation=pgtrigger.Update | pgtrigger.Delete)]

    @classmethod
    def from_event(cls, event) -> "SubmissionEventRecord":
        return cls(
            event_id=event["event_id"],
            type=event["type"],
            submission=event["submission"],
            form_type=event["form_type"],
            occurred_at=event["occurred_at"],
            event=event,
        )

    def __str__(self) -> str:
        return f"{self.type} {self.submission}"


class SeparatedSubmissionImport(models.Model):
    """
    Record a success / fail message for a submission import
    """

    submission = models.ForeignKey(SeparatedSubmission, on_delete=models.CASCADE)
    created = models.DateTimeField(default=timezone.now)
    success = models.BooleanField()
    message = models.TextField()

    class Meta:
        indexes = [
            # Both readers of this table ask one question — the most recent attempt for a
            # row — and until now the only index was the implicit one on the foreign key,
            # so answering it meant sorting every attempt that row has ever had. The
            # columns are in the order the query wants them, tiebreak included; see
            # `querysets._latest_import_success`, which is the only place that ordering is
            # written.
            models.Index(
                fields=["submission", "-created", "-id"],
                name="sepsubimport_latest_idx",
            ),
        ]

    def __str__(self) -> str:
        status = "ok" if self.success else "fail"
        msg = self.message or ""
        return f"{status} @ {self.created}: {msg[:50]}..." if len(msg) > 50 else f"{status} @ {self.created}: {msg or '-'}"


class Flag(models.Model):
    """
    Quality-assurance flag on a separated submission, visible to users and
    administrators. Used to surface data-quality issues (e.g. mismatched worker
    data between forms). One separated submission can have multiple flags
    (different rule types).

    A flag can also point at a request the consumer recorded but did not store
    (issue #109): a refused new report has no submission to sit on, so it
    carries only ``request_key``. A request held back from an existing
    submission sets both. ``request_key`` is the consumer's own id for the
    request and is never interpreted here.

    A flag with a separated submission is deleted with it, including by the
    split's cleanup of repeater rows a later edit dropped, and including a
    flag that also names a request. A consumer that needs a request to outlive
    its row keeps its own record of the request, or puts the flag on a row that
    outlives the change.

    ``params`` holds the values a flag's message refers to (e.g. the id of a
    colliding submission), so ``message`` can stay fixed, translatable text.
    Its keys belong to whichever rule wrote the flag.
    """

    SEVERITY_CHOICES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
    ]

    separated_submission = models.ForeignKey(
        SeparatedSubmission,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="quality_flags",
    )
    request_key = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="The consumer's id for the request this flag is about, when there is one",
    )
    flag_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Code identifying the rule that created this flag (e.g. workers_project_mismatch)",
    )
    message = models.TextField(help_text="User-facing message for this flag")
    params = models.JSONField(
        default=dict,
        blank=True,
        help_text="Values the message refers to, keyed by the rule that wrote the flag",
    )
    severity = models.CharField(
        max_length=16,
        choices=SEVERITY_CHOICES,
        default="warning",
    )
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_flags",
        help_text="User responsible for triaging/resolving this flag",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]
        constraints = [
            # ``assigned_at`` is how long a flag has sat with someone, so an
            # assignment without it silently under-reports the triage queue's
            # age. The admin keeps the pair in step; this makes every other
            # writer (data migrations, rule engines, bulk ``.update()``) do the
            # same instead of failing quietly.
            #
            # One-directional on purpose. The biconditional ("both set or both
            # NULL") is unenforceable alongside ``assigned_to``'s SET_NULL:
            # deleting a user issues a bare ``UPDATE ... SET assigned_to_id =
            # NULL``, leaving ``assigned_at`` behind, so it would make every
            # user who has ever held a flag undeletable — and fail deep inside
            # the delete cascade. A stranded ``assigned_at`` is harmless
            # residue; an assignment with no age is the state worth rejecting.
            models.CheckConstraint(
                condition=models.Q(assigned_to__isnull=True) | models.Q(assigned_at__isnull=False),
                name="flag_assigned_to_has_assigned_at",
            ),
            # A flag has to be about something: a stored submission, a
            # request, or both. An empty key does not count as naming a
            # request. Both halves of the key test are needed: a CHECK passes
            # when it evaluates to NULL, and ``NULL > ''`` is NULL.
            models.CheckConstraint(
                condition=models.Q(separated_submission__isnull=False) | models.Q(request_key__isnull=False, request_key__gt=""),
                name="flag_has_submission_or_request",
                violation_error_message="A flag needs a separated submission, a request key, or both.",
            ),
        ]
        indexes = [
            # Every submission changelist page now runs the
            # ``with_has_unresolved_flags`` correlated EXISTS. A partial index
            # keeps that flat as the flag table grows: it covers only the
            # unresolved rows, which is the only half the subquery looks at.
            models.Index(
                fields=["separated_submission"],
                condition=models.Q(resolved_at__isnull=True, separated_submission__isnull=False),
                name="flag_unresolved_by_sepsub_idx",
            ),
            # Exact lookups by the consumer's request id. A plain index, not
            # ``db_index=True``, which would add a LIKE-pattern index nothing uses.
            models.Index(fields=["request_key"], name="flag_request_key_idx"),
        ]

    def __str__(self) -> str:
        if self.separated_submission_id is None:
            return f"{self.flag_type} on request {self.request_key}"
        return f"{self.flag_type} on separated submission {self.separated_submission_id}"

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None
