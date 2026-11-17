# Submission changes — preliminary specification

**Status: draft for discussion, nothing here is built.** It describes the format the library
already writes for an edit (event format 1, since 7.2.0) and proposes how a form app could send
an edit in that same format instead of sending the whole submission again.

Two documents travel with this one:

- [`schemas/submission-changes-1.json`](schemas/submission-changes-1.json): a JSON Schema
  (draft 2020-12) for the format.
- [`schemas/submission-changes-1.examples.json`](schemas/submission-changes-1.examples.json):
  reference examples, each a `before` document, an `after` document and the `changes` between
  them. They were produced by the library's own `diff_fields`, and each one was checked to pass
  the schema and to turn `before` into `after` through `apply_changes`. Once this format is
  declared stable, these examples are never edited or removed, only added to.

## 1. The format

A change describes what happened to one submission's answers in one save. It has up to three
parts, and each is present only when it has something in it:

| Part | Holds | Example |
|---|---|---|
| `set` | answers that are new or different, each with its whole new value | `{"set": {"project_status": 3}}` |
| `unset` | keys of answers that were removed | `{"unset": ["comments"]}` |
| `rows` | row-by-row changes to a repeater, keyed by the repeater's key | see below |

A save that changes no answers is the empty change, `{}`.

### Repeaters

A repeater is changed row by row only when every row has a `uuid`, both before and after, and
no two rows share one. Its entry in `rows` has up to three parts:

| Part | Holds |
|---|---|
| `order` | every row's uuid in the new order. Present whenever a row was added, removed or moved. A row that is left out is removed. |
| `added` | each new row, whole, keyed by its uuid |
| `changed` | for each existing row that changed, a change of the same shape as the whole, keyed by its uuid. A repeater inside a row is therefore changed row by row too. |

```json
{"rows": {"outputs": {"changed": {"5d2f8a44-…": {"set": {"quantity": 3}}}}}}
```

When any row of a repeater has no uuid, or two rows share one, the whole repeater is sent in
`set` as one answer.

### Values

A value in `set`, or an answer inside an added row, is any JSON value: text, a number, true or
false, a list or an object. A cleared answer is removed with `unset`; it is never set to `""` or
`null`. Saved submissions never store either, so a change that sets one would be recorded as a
change the stored submission does not show.

### Rules the schema cannot express

The JSON Schema checks the shape. These rules need a check of their own, which the server runs
before applying a change from outside the library (proposed below as `check_changes`). The
library's own `apply_changes` does not refuse any of them today (measured: applying each case
to a two-row document in a scratch script):

1. A key appears in at most one of `set`, `unset` and `rows`. Today a key in both `set` and
   `unset` ends up set.
2. A repeater entry with `added` also has `order`, and `order` lists every added uuid. Today an
   added row with no `order` is silently dropped.
3. An added row's `uuid` equals the key it is filed under, and is not already a row of that
   repeater. Today the first is stored as given, and the second overwrites the existing row.
4. Every row named in `changed` is still in `order`. Today a changed row that is also removed
   is dropped without complaint.
5. `set` holds no `""` or `null`.

`apply_changes` already refuses a `rows` entry for an answer that is not a repeater with uuids,
and a `changed` row that does not exist.

### Equality

The library treats `1`, `1.0` and `true` as different values when it works out a change. A
JavaScript app cannot tell `1` from `1.0`. This does not need settling for the app, because of
how a change is judged (next section): an app's change is correct when applying it to the
submission it started from gives the answers the officer sees. It does not have to be the
smallest possible change, or the one the library would have worked out.

## 2. Sending an edit from a form app

Today the app sends the whole submission on every save, and the server works out what changed
by comparing it with the stored copy. The comparison cannot tell what the officer did from
what the app happened to send: an answer missing from the document reads as cleared, whether
the officer cleared it, the app never loaded it, or someone else added it since the app opened
the submission. And the comparison is made after the normaliser has run, so it records what
was stored rather than what was entered.

The proposal: for an edit, the app sends the change instead.

```json
{
  "submission": "6f1c…",
  "form_type": "TF_6_1_1",
  "base": "0193a7c2-…",
  "changes": {"set": {"project_status": 3}, "unset": ["comments"]}
}
```

`base` names the version of the submission the app started from. Which value is the consumer's
choice: the last event the app has seen, or a position in the consumer's own stream. A new
submission is still sent whole.

The server then:

1. checks the change against the schema and the rules above, and refuses it if either fails;
2. applies it to its stored copy of the submission;
3. runs the normaliser and its own checks on the result, exactly as it does for a whole-document
   save today, so nothing downstream sees a difference;
4. saves, which records the normalised edit as now: the library works out the change between
   the stored copy and the saved result;
5. records the change exactly as the app sent it, with `base`, as the **original** event, sharing
   its `correlation` with the normalised events.

Old apps that send the whole submission keep working unchanged, and simply have no original
event. Both kinds of app can run side by side for as long as needed.

### When two people edit the same submission

The first version does not check `base`. A change is applied to whatever is stored, so two
people editing different answers both keep their edits (today the second save undoes the
first), and two people editing the same answer get the later one. A change that cannot be
applied, because a row it changes has since been removed, is refused.

This rests on one premise: that two people editing one submission at the same time is rare
(Josh's expectation, not measured). Because `base` is recorded on every original event, the
premise can be measured later from the history, by counting changes whose `base` was no longer
the latest version when they arrived. If that count turns out not to be small, the server can
start refusing a stale `base` without changing the format.

### What the library would add

- `check_changes(changes)`: the schema and the five rules, raising one error that names every
  problem.
- The schema and the examples, shipped with the package, with a test that checks every example
  against `diff_fields`, `apply_changes` and the schema.
- A place on the event for the change as sent. Whether that is a separate event type in the
  same history, or an event in a separate stream the consumer owns, follows the decision on the
  original stream.
- `docs/public-api.md`: the format moves from provisional to stable, with the promise that
  event format 1 is read forever and only ever added to under a new format number.

The app's side (working out the change, giving new rows a uuid, the endpoint) belongs to the
consumer.

## 3. Typed submissions

A form's Pydantic model (generated, or kept by hand) can carry the format as two methods, so
code that works with a submission never handles the plain format directly:

```python
class Tf611(Submission):          # Submission: a small base class from this library
    project_status: IdaOption = None
    comments: str | None = None
    outputs: list[Output] = []

current = old.with_changes(d1).with_changes(d2)
change = current.changes_since(old)
assert old.with_changes(change) == current
```

- `with_changes(changes)` turns the model into its stored answers, applies the change with
  `apply_changes`, and validates the result back into the model.
- `changes_since(old)` runs `diff_fields` on the two models' stored answers.
- `+` and `-` are shorthand for the two methods, for tests and documentation:
  `old + d1 + d2 == current`, `current - old == change`. The methods are the documented
  interface, because they read plainly in a stack trace. `+` takes a model on the left only.

Because `with_changes` validates, it also tidies: the model is the normaliser. That gives the
two streams directly. The changes the app sent are the original stream. The changes between
each validated state and the one before it are the normalised stream. A change that names an
answer the model does not have, or gives a value it cannot accept, is refused before anything
is stored.

A prototype of the base class (a scratch script against 7.2.0, not committed) showed:

| Check | Result |
|---|---|
| `old + d1 + d2 == current`, with `d1` setting an option as text `"3"` and `d2` adding a row with `"unit": "7"` | holds; `current` stores `3` and `7` |
| `current - old` | `{"set": {"project_status": 3}, "unset": ["comments"], "rows": {"outputs": {"order": […], "added": {…}}}}`, the tidied values |
| `old + (current - old) == current` | holds |
| applying `d1` twice | the same as applying it once |
| a change setting an answer the model does not have (model set to forbid extra answers) | refused by validation |

Rules the base class must follow, two of which the prototype broke:

1. **The model's stored answers must equal what saving stores, exactly**, or every save shows
   changes nobody made. The prototype wrote an empty repeater as `[]`, which saving drops, and a
   decimal as text (`"120"`) where the stored answer may be the number `120`. Turning a model
   into stored answers needs one function, sharing its rules with saving and tested against it.
2. **Tidying must give the same result when run twice.** `old + d1 + d2` tidies after each
   change. Two changes merged first and applied once are tidied only at the end. The two agree
   only if tidying is repeatable, which matters once edits are saved offline (open question 3).
3. **Merging two changes (`d1 + d2`, without the submission) is not part of the first
   version.** It can be defined (a later removal overrides an earlier set, a change to a row the
   first change added folds into that added row, the later order wins), and is worth adding
   only when offline edits need it.

The plain format stays what the app sends and what the history stores. The typed methods are
how Python code on the server reads and makes changes.

## 4. Open questions

1. **Row position.** Rows carry `$rank`, their position. Should the app send it for an added or
   moved row, or leave the server to assign it as it does for a whole-document save? (Inferred
   that the server assigns it on save; not checked.)
2. **Row uuids from the app.** The app must give each new row a uuid before it sends the change.
   Whether the form library already does is not checked.
3. **Edits saved offline.** The consumer's app does not queue edits offline today. If it starts
   to, two changes queued for one submission must be combined before sending, or sent in order
   with the second's `base` naming the first.
4. **The original's shape.** The consumer's own event catalogue plans an edit that carries
   `changed_answers` and `previous_answers`. Using this format there instead, or alongside,
   needs agreeing with that design.
