"""Turn one submission into the events that describe it.

This is the decomposition that ``SeparatedSubmission.objects.from_submission``
has always performed, expressed as a value instead of as a set of database
writes. The same walk, the same identities, the same order — but the result is a
list of frozen dataclasses, so it can be appended to a log, folded into a
projection, compared against another run, or replayed years later.

What it decides: which rows a document contains, what each row's identity and
parent are, which stream each belongs on, the order they must be applied in, and
each row's position among its siblings.

What it deliberately does not decide: anything domain-specific. There is no form
type named in this module. It does not know what a project is, what a status
means, whether an import succeeded, or what should happen next. Those are the
consumer's decisions and they stay there.

**No transport.** This module imports no stream library and performs no I/O. A
consumer takes the emissions, wraps each in whatever envelope it uses, and
appends them. Keeping the dependency out means this library, the log
implementation and the consumer can each be released without waiting on the
other two.

**Stream names are a default.** ``stream_path`` and ``reorder_stream_path`` say
where this library would put each row's events, but the application that writes
to the log owns the names of its streams. A consumer that already writes to a
log may name them differently (Partisipa uses ``submissions/<form>``, not
``submission/<form>``). The one rule that is shared is ``slug``: how a form's
name is spelt inside a path.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from formkit_ninja.form_submission.reserved import RANK_KEY, UUID_KEY
from formkit_ninja.form_submission.utils import flatten

#: Stream path prefix for a document's content.
SUBMISSION_PREFIX = "submission"

#: Stream path prefix for a row changing position within its sibling group.
REORDER_PREFIX = "repeater_reorder"


@dataclass(frozen=True)
class Emission:
    """One row of one document, ready to become an event.

    ``row_id`` is the identity the derived row will be keyed by: the submission's
    own key for the root, and the row's ``uuid`` for a repeater row. It comes out
    of the canonical document rather than being minted here, which is what lets a
    replay reproduce the same primary keys — and therefore lets everything that
    points at a derived row keep pointing at it.

    ``fields`` carries the user's answers only; identity and position travel as
    ``row_id`` and ``rank`` rather than inside the payload, so re-ordering a row
    does not read as a content change.

    It is typed as a ``Mapping`` because an emission owns its answers and nothing
    should write through them. The dict is already the emission's own — ``flatten``
    deep-copies, so popping the bookkeeping keys during construction never reaches
    the caller's document — but ``dict`` invited a consumer to mutate a value that
    reads as frozen, and ``frozen=True`` does not stop that.
    """

    stream_path: str
    form_type: str
    row_id: str
    parent_id: str | None
    repeater_key: str | None
    fields: Mapping[str, Any]
    rank: str | None

    @property
    def is_root(self) -> bool:
        return self.repeater_key is None


def slug(name: str) -> str:
    """A form type as it appears in a stream path: ``TF_13_2_1`` -> ``tf1321``.

    Vocabulary, not policy — which is why it lives here rather than in a
    consumer. Consumers that already spell it themselves should re-export this
    one rather than keep a second copy, since two copies of a naming rule
    disagree exactly once and then silently write to two different streams.
    """
    return name.lower().replace("_", "")


def stream_path(form_type: str, repeater_path: Sequence[str] = ()) -> str:
    """Where a row's events live.

    ::

        stream_path("TF_6_1_1")                              -> submission/tf611
        stream_path("TF_13_2_1", ["repeaterProjectProgress"]) -> submission/tf1321/repeaterprojectprogress

    Nested repeaters extend the path rather than flattening into it, so a
    repeater's stream sits under the root it belongs to and depth costs nothing
    to represent.

    This is an advisory default, not a rule. A consumer that already writes to a
    log may name its streams differently, and should still build the form part
    of the path with ``slug`` so the spelling cannot drift.
    """
    return "/".join([SUBMISSION_PREFIX, slug(form_type), *(slug(part) for part in repeater_path)])


def reorder_stream_path(form_type: str) -> str:
    """Where position changes for a document family live — one stream per root.

    Per root rather than per repeater because a re-order is scoped to a sibling
    group, and the group is already identified by ``parent_id`` plus
    ``repeater_key`` on the payload. One stream per root keeps the inventory a
    rebuild has to walk small.

    Like ``stream_path``, this is an advisory default: a consumer that already
    writes to a log may name its streams differently, and should still use
    ``slug`` for the form part.
    """
    return f"{REORDER_PREFIX}/{slug(form_type)}"


def emit_submission(sub) -> list[Emission]:
    """Every row of ``sub``, root first, then repeaters parent-before-child.

    Pure with respect to the database: it reads ``sub.fields``, ``sub.form_type``
    and ``sub.pk`` and queries nothing. That is the property that makes a replay
    faithful — a producer that consults the rows it is about to write cannot be
    replayed, because on the second run those rows already say something
    different.

    Order matters and is not incidental: a repeater row names its parent, so the
    parent has to be applied first. ``flatten`` yields children first and the root
    last, so this reverses it.
    """
    rows = list(flatten(sub.fields, [sub.form_type], parent_uuid=sub.pk))
    _root_path, _root_parent, root_fields, _root_index = rows[-1]

    emissions = [
        Emission(
            stream_path=stream_path(sub.form_type),
            form_type=sub.form_type,
            row_id=str(sub.pk),
            parent_id=None,
            repeater_key=None,
            fields=root_fields,
            # A root has no siblings, so it has no position among them.
            rank=None,
        )
    ]

    for path, parent_uuid, row_fields, _index in reversed(rows[:-1]):
        row_id = row_fields.pop(UUID_KEY, None)
        rank = row_fields.pop(RANK_KEY, None)
        if not row_id:
            # A row that was never given an identity was never stored, so there
            # is nothing for an event to be about. The wording is the splitter's
            # own, kept verbatim: this warning predates the emitter, it is the
            # only signal a consumer gets for a dropped row, and some of them
            # match on it.
            warnings.warn(f"No Submission key (UUID) present in {row_fields} of {sub}")
            continue
        emissions.append(
            Emission(
                # `path` starts with the form type, so the rest is the repeater
                # nesting — exactly what the stream path needs.
                stream_path=stream_path(path[0], path[1:]),
                form_type="".join(part.capitalize() for part in path),
                row_id=str(row_id),
                parent_id=str(parent_uuid) if parent_uuid else str(sub.pk),
                repeater_key=path[-1],
                fields=row_fields,
                rank=rank,
            )
        )
    return emissions


def emit_reorder(sub, *, prior: dict[str, str]) -> list[Emission]:
    """One emission per row whose position changed, and nothing for the rest.

    ``prior`` is the rank each row held before this save
    (``ranking.harvest_ranks`` over the stored document). A group that did not
    move produces an empty list, which is the point: moving one row of thirty
    should cost one event, not thirty.
    """
    path = reorder_stream_path(sub.form_type)
    return [replace(e, stream_path=path) for e in emit_submission(sub) if e.rank is not None and prior.get(e.row_id) != e.rank]
