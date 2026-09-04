"""The ordering primitive (#74): base-62 fractional index keys.

The point of taking a dependency rather than hand-rolling the arithmetic is
byte-for-byte compatibility with the JavaScript and Go implementations, so a
client that mints a key locally and a server that mints one agree. That claim
is only worth anything if it is asserted, so the canonical vectors published by
``rocicorp/fractional-indexing`` are pinned here rather than trusted.
"""

import pytest

from formkit_ninja.fracrank import DIGITS, key_between, keys_between, validate_key

# --------------------------------------------------------------------------- #
# Cross-language conformance
# --------------------------------------------------------------------------- #

#: ``(a, b, expected)`` from the canonical ``rocicorp/fractional-indexing`` table.
#: A failure here means the key format moved and every key already stored under
#: the old format is now ordered against keys minted under the new one.
CANONICAL = [
    (None, None, "a0"),
    (None, "a0", "Zz"),
    ("a0", None, "a1"),
    ("a0", "a1", "a0V"),
    ("a0V", "a1", "a0l"),
    (None, "Zz", "Zy"),
    ("Zz", None, "a0"),
    ("a0", "a2", "a1"),
    ("a1", None, "a2"),
    ("az", None, "b00"),
    ("b127", None, "b13"),
    ("a0", "a0V", "a0G"),
    ("a0", "a0G", "a08"),
    ("a0P", "a0V", "a0S"),
    # Boundary: the largest single-magnitude key appends rather than overflowing.
    ("zzzzzzzzzzzzzzzzzzzzzzzzzzy", None, "zzzzzzzzzzzzzzzzzzzzzzzzzzz"),
    ("zzzzzzzzzzzzzzzzzzzzzzzzzzz", None, "zzzzzzzzzzzzzzzzzzzzzzzzzzzV"),
]


@pytest.mark.parametrize("a,b,expected", CANONICAL)
def test_matches_the_canonical_javascript_vectors(a, b, expected):
    assert key_between(a, b) == expected


def test_the_alphabet_is_ascii_ordered():
    """Byte comparison must equal index comparison, or Postgres and Python part ways."""
    assert list(DIGITS) == sorted(DIGITS)
    assert len(set(DIGITS)) == len(DIGITS) == 62


# --------------------------------------------------------------------------- #
# key_between
# --------------------------------------------------------------------------- #


def test_a_key_sorts_strictly_between_its_neighbours():
    a, b = "a0", "a1"
    mid = key_between(a, b)
    assert a < mid < b


def test_repeated_subdivision_always_finds_room():
    """The property the whole design rests on: there is always a key in the gap."""
    lo, hi = "a0", "a1"
    for _ in range(50):
        mid = key_between(lo, hi)
        assert lo < mid < hi
        hi = mid


@pytest.mark.parametrize("a,b", [("a1", "a0"), ("a0", "a0")])
def test_neighbours_in_the_wrong_order_are_a_caller_bug(a, b):
    """``a >= b`` is not rounded away — there is no key to return and pretending
    otherwise would write a rank that breaks the ordering it was meant to fix."""
    with pytest.raises(ValueError):
        key_between(a, b)


def test_a_malformed_neighbour_raises_valueerror_not_fierror():
    """Callers here are written against ``ValueError``; the library's ``FIError``
    must not leak through the seam."""
    with pytest.raises(ValueError):
        key_between("not a key", None)


# --------------------------------------------------------------------------- #
# keys_between
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("count", [1, 2, 3, 5, 17, 100])
def test_n_keys_are_strictly_ascending(count):
    keys = keys_between(None, None, count)
    assert len(keys) == count
    assert keys == sorted(keys)
    assert len(set(keys)) == count


@pytest.mark.parametrize("count", [1, 2, 3, 5, 17, 100])
def test_n_keys_stay_inside_their_bounds(count):
    lo, hi = "a0", "a1"
    keys = keys_between(lo, hi, count)
    assert all(lo < k < hi for k in keys)
    assert keys == sorted(keys)


def test_zero_keys_is_the_empty_list_not_an_error():
    """An unchanged repeater re-ranks nothing, and that is the common case."""
    assert keys_between(None, None, 0) == []
    assert keys_between("a0", "a1", 0) == []


def test_a_negative_count_is_rejected():
    with pytest.raises(ValueError):
        keys_between(None, None, -1)


# --------------------------------------------------------------------------- #
# validate_key
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", ["a0", "a1", "Zz", "a0V", "b00", "zzzzzzzzzzzzzzzzzzzzzzzzzzzV"])
def test_well_formed_keys_pass(key):
    validate_key(key)  # does not raise


@pytest.mark.parametrize(
    "key",
    [
        None,
        "",
        # `validate_order_key` accepts these; we do not. A space (0x20) sorts below
        # "0" (0x30) under COLLATE "C" while the algorithm reads it as the zero digit,
        # so Python and SQL would silently disagree about the order.
        "a0 ",
        "a0!",
        "a0-",
        # Genuinely malformed, caught by the library.
        "1",
        "not a key",
    ],
)
def test_malformed_keys_are_rejected(key):
    with pytest.raises(ValueError):
        validate_key(key)


def test_the_rejection_names_the_stray_characters():
    """A bad key found in a database column is useless as a bare 'invalid'; the
    error has to say what is wrong with it."""
    with pytest.raises(ValueError, match=r"outside the alphabet.*' '"):
        validate_key("a0 ")
