"""The emitter must describe exactly what the splitter writes.

``emit_submission`` is the decomposition ``from_submission`` performs, expressed
as a value. That equivalence is the whole basis for later feeding the splitter
from a log instead of from a document, so it is asserted directly here rather
than inferred from both sides passing their own tests.
"""

from __future__ import annotations

import uuid

import pytest

from formkit_ninja.form_submission.emit import (
    emit_reorder,
    emit_submission,
    reorder_stream_path,
    slug,
    stream_path,
)
from formkit_ninja.form_submission.models import SeparatedSubmission, Submission
from formkit_ninja.form_submission.ranking import apply_ranks, harvest_ranks
from formkit_ninja.form_submission.utils import pre_validation


class TestStreamPaths:
    def test_a_root_form_gets_one_path_segment(self):
        assert stream_path("TF_6_1_1") == "submission/tf611"

    def test_a_repeater_nests_under_its_root(self):
        assert stream_path("TF_13_2_1", ["repeaterProjectProgress"]) == "submission/tf1321/repeaterprojectprogress"

    def test_nesting_extends_rather_than_flattens(self):
        assert stream_path("SF_1_2", ["outer", "inner"]) == "submission/sf12/outer/inner"

    def test_reorder_is_one_stream_per_root_family(self):
        assert reorder_stream_path("TF_13_2_1") == "repeater_reorder/tf1321"

    def test_slug_drops_the_underscores_a_form_code_carries(self):
        assert (slug("TF_6_1_1"), slug("SF_2_3")) == ("tf611", "sf23")


@pytest.mark.django_db
class TestEmissionMatchesTheSplit:
    """The equivalence gate. A mutation to either side must show up here."""

    def _submission(self, user, fields, form_type="Tf611"):
        return Submission.objects.create(user=user, fields=fields, form_type=form_type)

    def test_a_flat_document_emits_only_a_root(self, admin_user):
        sub = self._submission(admin_user, {"question": "answer"})
        emissions = emit_submission(sub)
        assert [e.row_id for e in emissions] == [str(sub.pk)]
        assert emissions[0].is_root and emissions[0].parent_id is None

    def test_every_derived_row_has_exactly_one_emission_with_the_same_pk(self, admin_user):
        sub = self._submission(
            admin_user,
            {"title": "t", "repeaterA": [{"v": 1}, {"v": 2}], "repeaterB": [{"w": 9}]},
        )
        emitted = {e.row_id for e in emit_submission(sub)}
        stored = {str(pk) for pk in SeparatedSubmission.objects.filter(submission=sub).values_list("pk", flat=True)}
        assert emitted == stored

    def test_parents_and_repeater_keys_match_the_stored_rows(self, admin_user):
        sub = self._submission(admin_user, {"title": "t", "repeaterA": [{"v": 1}, {"v": 2}]})
        by_id = {str(row.pk): (str(row.repeater_parent_id) if row.repeater_parent_id else None, row.repeater_key) for row in SeparatedSubmission.objects.filter(submission=sub)}
        for e in emit_submission(sub):
            assert by_id[e.row_id] == (e.parent_id, e.repeater_key)

    def test_form_type_matches_the_stored_row(self, admin_user):
        sub = self._submission(admin_user, {"repeaterA": [{"v": 1}]})
        by_id = {str(r.pk): r.form_type for r in SeparatedSubmission.objects.filter(submission=sub)}
        for e in emit_submission(sub):
            assert by_id[e.row_id] == e.form_type

    def test_a_parent_is_always_emitted_before_its_children(self, admin_user):
        sub = self._submission(
            admin_user,
            {"repeaterA": [{"v": 1, "inner": [{"z": 1}]}, {"v": 2, "inner": [{"z": 2}]}]},
        )
        seen: set[str] = set()
        for e in emit_submission(sub):
            if e.parent_id is not None:
                assert e.parent_id in seen, f"{e.row_id} emitted before its parent {e.parent_id}"
            seen.add(e.row_id)

    def test_nested_repeaters_land_on_a_nested_stream(self, admin_user):
        sub = self._submission(admin_user, {"repeaterA": [{"inner": [{"z": 1}]}]}, form_type="Tf611")
        paths = {e.stream_path for e in emit_submission(sub)}
        assert "submission/tf611" in paths
        assert "submission/tf611/repeatera" in paths
        assert "submission/tf611/repeatera/inner" in paths

    def test_identity_and_position_do_not_travel_inside_fields(self, admin_user):
        """A re-order must not read as a content change, so `fields` carries answers only.

        The rank has to be *present* on the row for this to test anything — a
        document that never carried one gives the same green whether the emitter
        strips it or not. Mutation watched: `pop(RANK_KEY)` -> `get(RANK_KEY)`.
        """
        sub = self._submission(admin_user, {"repeaterA": [{"v": 1}]})
        sub.fields = apply_ranks(sub.fields, prior={})
        assert sub.fields["repeaterA"][0]["$rank"], "fixture must carry a rank or this proves nothing"

        child = next(e for e in emit_submission(sub) if not e.is_root)
        assert child.fields == {"v": 1}
        assert child.rank == sub.fields["repeaterA"][0]["$rank"]

    def test_emitting_queries_nothing(self, admin_user, django_assert_num_queries):
        """A producer that reads the rows it is about to write cannot be replayed."""
        sub = self._submission(admin_user, {"repeaterA": [{"v": 1}, {"v": 2}]})
        with django_assert_num_queries(0):
            emit_submission(sub)

    def test_a_row_without_an_identity_is_skipped_with_a_warning(self, admin_user):
        """Matches the splitter: never stored, so there is nothing to be about."""
        sub = self._submission(admin_user, {"repeaterA": [{"v": 1}]})
        sub.fields["repeaterA"][0].pop("uuid")
        with pytest.warns(UserWarning, match="No Submission key"):
            assert [e.row_id for e in emit_submission(sub)] == [str(sub.pk)]


class TestReorderEmissions:
    """Pure — no database needed, which is itself the point."""

    class _Doc:
        form_type = "Tf611"

        def __init__(self, fields):
            self.pk = uuid.uuid4()
            self.fields = fields

    def _ranked(self, n):
        doc = self._Doc({"rep": [{"uuid": str(uuid.uuid4()), "v": i} for i in range(n)]})
        doc.fields = apply_ranks(doc.fields, prior={})
        return doc

    def test_an_unmoved_document_emits_no_reorder_at_all(self):
        doc = self._ranked(4)
        assert emit_reorder(doc, prior=harvest_ranks(doc.fields)) == []

    def test_moving_one_row_of_four_emits_one_event(self):
        doc = self._ranked(4)
        prior = harvest_ranks(doc.fields)
        rows = doc.fields["rep"]
        doc.fields["rep"] = [rows[3], rows[0], rows[1], rows[2]]
        doc.fields = apply_ranks(doc.fields, prior=prior)

        events = emit_reorder(doc, prior=prior)
        assert len(events) == 1
        assert events[0].row_id == rows[3]["uuid"]

    def test_a_reorder_goes_to_the_reorder_stream(self):
        doc = self._ranked(2)
        prior = harvest_ranks(doc.fields)
        doc.fields["rep"].reverse()
        doc.fields = apply_ranks(doc.fields, prior=prior)
        assert {e.stream_path for e in emit_reorder(doc, prior=prior)} == {"repeater_reorder/tf611"}

    def test_a_first_rank_is_a_reorder_too(self):
        """Nothing held a position before, so every row's position is news."""
        doc = self._ranked(3)
        assert len(emit_reorder(doc, prior={})) == 3


class TestEmptyRowsStayEmpty:
    """`$rank` must not make a blank repeater row look like data.

    This is the break that is both silent and second-save-only: `pre_validation`
    runs before the identity is minted, so a create looks fine and it is the edit
    that starts materialising phantom rows.
    """

    def test_a_ranked_empty_row_is_treated_exactly_as_an_unranked_one(self):
        """Asserted as an equivalence, not against a literal: the guarantee is
        that adding a reserved key changed nothing, and a hardcoded expectation
        would still pass if both sides regressed together."""
        row_id = str(uuid.uuid4())
        assert pre_validation({"rep": [{"uuid": row_id, "$rank": "a0"}]}) == pre_validation({"rep": [{"uuid": row_id}]})

    def test_a_row_with_one_real_answer_survives(self):
        row = {"uuid": str(uuid.uuid4()), "$rank": "a0", "v": 1}
        assert pre_validation({"rep": [row]})["rep"] == [row]

    def test_the_guard_is_a_subset_test_not_an_equality_test(self):
        """The mutation this was watched against: reverting `_skip_value` to
        `== {"uuid"}`. That leaves the row in the document, so it materialises."""
        assert pre_validation({"rep": [{"uuid": str(uuid.uuid4()), "$rank": "a0"}]}) == {}
