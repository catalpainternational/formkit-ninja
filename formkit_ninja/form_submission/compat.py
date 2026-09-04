"""Keeping ``repeater_order`` readable after the column is gone (#74).

The column is dropped. What it held is still available — it was the rank's position
within its sibling group, counted — so this is a change of representation, not a loss,
and the point of this module is that a consumer does not have to finish migrating
before they can upgrade.

Three shapes of use, three answers:

* ``row.repeater_order`` — still works. :class:`RepeaterOrderDescriptor` computes it on
  access and warns. One query per access, which is the honest price of asking a row
  about its siblings; a loop over rows should annotate instead.
* ``.order_by("repeater_order")`` / ``.filter(repeater_order=0)`` /
  ``.values_list("repeater_order")`` — add ``.with_repeater_order()`` to the queryset
  and they work unchanged, because the annotation is named ``repeater_order``.
* ``SeparatedSubmission(repeater_order=3)`` — accepted and discarded, with a warning,
  rather than raising ``TypeError``. The value had nowhere to go even before the drop:
  the splitter recomputed it on every save.

Deliberately *not* annotating every queryset by default. It was the obvious design and
it is wrong: a window function on ``get_queryset()`` reaches ``.update()``,
``.delete()`` and ``bulk_update()``, which Django will not run against a windowed
queryset. Silence where it is safe, a loud ``FieldError`` where it is not, and one
method call to fix it.
"""

from __future__ import annotations

import warnings


class RepeaterOrderDeprecationWarning(DeprecationWarning):
    """Raised on every read or write of the retired ``repeater_order``.

    Its own class so a consumer can find the call sites — ``-W error::...`` in a test
    run turns the whole migration into a list of stack traces — and so that turning it
    into an error does not also break every other deprecation in their stack.
    """


#: The one place the replacement is named, so the message cannot drift from the API.
GUIDANCE = "use .with_repeater_order() on the queryset, or .in_document_order() if you only want the rows in order"


class RepeaterOrderDescriptor:
    """``repeater_order`` as a computed attribute.

    Holds an annotated value when one is set — ``with_repeater_order()`` produces an
    annotation of this same name, and Django assigns annotations with ``setattr``, which
    a bare ``property`` would either reject or silently swallow. Stored in the instance
    dict under a private key so a later read returns the annotated value rather than
    running a second query for an answer it already has.
    """

    _CACHE = "_repeater_order_annotated"

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        if self._CACHE in instance.__dict__:
            return instance.__dict__[self._CACHE]

        warnings.warn(
            f"SeparatedSubmission.repeater_order has been removed as a column and is computed from repeater_rank, which costs a query per row: {GUIDANCE}",
            RepeaterOrderDeprecationWarning,
            stacklevel=2,
        )
        return self._compute(instance)

    def __set__(self, instance, value):
        # Both an annotation landing (no warning wanted — the caller asked for it) and a
        # consumer still passing the old kwarg. Telling them apart is not worth a flag:
        # the annotation is the value we want to keep either way, and the constructor
        # path warns on its own where it can name the argument.
        instance.__dict__[self._CACHE] = value

    @staticmethod
    def _compute(instance) -> int | None:
        """This row's position among its siblings, or ``None`` for a root row.

        Counts rather than reads: the siblings in document order, and where this row
        falls among them. Same answer the window function gives, one row at a time.
        """
        if instance.repeater_parent_id is None:
            return None

        siblings = list(
            type(instance)
            ._default_manager.filter(
                repeater_parent_id=instance.repeater_parent_id,
                repeater_key=instance.repeater_key,
            )
            .in_document_order()
            .values_list("pk", flat=True)
        )
        try:
            return siblings.index(instance.pk)
        except ValueError:
            # Unsaved, or deleted since it was loaded. The column would have held
            # whatever was last written; there is no honest answer, and inventing 0
            # would put an unsaved row at the front of a list it is not in.
            return None


def warn_on_write(value) -> None:
    """Called where the retired keyword is still being passed in."""
    warnings.warn(
        f"SeparatedSubmission.repeater_order is no longer stored, so repeater_order={value!r} is ignored. Order is set by the document; to read a position back, {GUIDANCE}",
        RepeaterOrderDeprecationWarning,
        stacklevel=3,
    )
