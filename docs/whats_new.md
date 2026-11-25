# What's new in 7.3

7.3 is about a submission's history: every change is recorded with more about why it happened,
the history reads as each answer's old and new value, and answers can be put back to an earlier
version. Everything new is optional. Nothing stored changes and no migration is needed. The full
list is in the [changelog](https://github.com/catalpainternational/formkit-ninja/blob/main/CHANGELOG.md#730---2026-11-25).

## A history you can read and roll back

`answer_history(events)` turns a submission's stored events into each answer's old and new value,
version by version. It works on every stored history, from any release.
`submission.roll_back_to(events, event_id)` puts the answers back as they were just after that
event. Going back is saved as a new edit, so the versions in between stay in the history, and the
status, owner and whether the submission is active are left as they are. See
[Recording what changed](submission_architecture.md#recording-what-changed).

## Knowing what a save did

- **Did anything change?** After `save()` or `delete()`, `submission.recorded_events` lists the
  events that write recorded. The list is empty when nothing changed, so an application can note an
  unchanged sending.
- **Changes made by the application's own code.** A receiver that rewrites an answer during a save
  calls `instance.label_edit(path, label)`, and the edit records that label. The person's own edits
  in the same save stay unlabelled.
- **Which cleaning rules were in force.** Set `rules_version` on the normaliser function and every
  create and edit records it.
- **The answers as they were sent.** `sent_event(...)` builds a `submission:sent` event holding the
  answers exactly as received. The application keeps it in its own store; the library stores
  nothing raw. See [Keeping the answers as sent](submission_architecture.md#keeping-the-answers-as-sent).

## Fixed

A repeater row with no answers, or only blank answers, is now dropped on save. Before 7.3 such a row
got a new id on every save and was recorded as an edit each time. A submission that already holds
one records a single edit at its next save and is stable after that.

## Upgrading from 7.2

Each kind of change now has its own type (`CreateEvent`, `EditEvent` and so on, with `Changes` for an
edit's changes), so a type checker knows which keys each one carries. Typed code may need a small
change:

- Check `event["type"] == SUBMISSION_EDIT` before reading `event["changes"]` or any other key that
  only some events have. An `==` test narrows the type; `in (...)` does not.
- Annotate what `diff_fields` returns as `Changes` or `Mapping[str, Any]`, not `dict[str, Any]`.
- `SubmissionEvent` is now a union, so it can't be called or subclassed.

The events themselves are unchanged at runtime. The new names are provisional; see
[What is public](public-api.md#tier-2-provisional).
