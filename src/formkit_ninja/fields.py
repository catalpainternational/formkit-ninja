from __future__ import annotations

import warnings

# from collections import UserDict
from typing import Sequence

from django.conf import settings
from django.db.models import JSONField
from django.utils import translation


class WhitelistedKeysDict(dict):
    """
    Allow only certain keys.
    >>> t = WhitelistedKeysDict("ahi!", default_key="tet")
    >>> t["tet"]
    'ahi!'
    >>> t = WhitelistedKeysDict("fire!", default_key="en")
    >>> t["en"]
    'fire!'
    >>> t = WhitelistedKeysDict({"en": "fire!", "tet": "ahi!"}, permitted_keys={"tet", "en"})
    >>> t["tet"]
    'ahi!'
    >>> t["en"]
    'fire!'
    >>> set(t.keys()) == {'tet', 'en'}
    True
    >>> t = WhitelistedKeysDict({"en": "fire!", "tet": "ahi!", "noexist": "should-warn"}, permitted_keys={"tet", "en"})
    >>> "noexist" in t
    False
    >>> set(t.keys()) == {"tet", "en"}
    True
    """

    default_key: str | None
    permitted_keys: set[str]

    def __init__(
        self,
        dict_=None,
        /,
        permitted_keys: set[str] = set(),
        default_key: str | None = None,
        **kwargs,
    ):
        self.default_key = default_key
        self.permitted_keys = permitted_keys
        if default_key:
            self.permitted_keys.add(default_key)
        self.data = {}
        if isinstance(dict_, str):
            if self.default_key:
                return self.__init__({self.default_key: dict_})
            warnings.warn("No default key was set. You must have a default_key to initialize with a string.")
            return super().__init__()
        return super().__init__(dict_ or {})

    def __setitem__(self, key: str, item: str) -> None:
        if key in self.permitted_keys:
            return super().__setitem__(key, item)
        warnings.warn(f"ignored key not in whitelist: {key}")


class TranslatedValues(WhitelistedKeysDict):
    """
    dict rejects keys not in Django's LANGUAGES
    >>> t = TranslatedValues("ahi!")
    >>> t["tet"]
    'ahi!'
    >>> t = TranslatedValues({"en": "fire!", "tet": "ahi!"})
    >>> t["tet"]
    'ahi!'
    >>> t["en"]
    'fire!'
    >>> set(t.keys()) == {'tet', 'en'}
    True
    >>> t = TranslatedValues({"en": "fire!", "tet": "ahi!", "noexist": "should-warn"})
    >>> "noexist" in t
    False
    >>> set(t.keys()) == {"tet", "en"}
    True
    >>> t.value  # Note: only when in Django, if Django language is set to 'tet'
    'ahi!'
    """

    def __init__(self, dict_, /, **kwargs):
        return super().__init__(
            dict_,
            permitted_keys=set((lang[0] for lang in getattr(settings, "LANGUAGES", ()))),
            default_key=translation.get_language(),
            **kwargs,
        )

    @property
    def value(self):
        """
        Return the value at the current language, or fallback
        """
        return TranslatedValues.get_str(self)

    @staticmethod
    def get_str(
        dict_: TranslatedValues,
        lang: str = translation.get_language(),
        fallback: Sequence[str] = ("en",),
    ):
        """
        Return the value at the current language, or fallback (static method)
        """
        # A newly created value might error out here if the `__str__` ref's the value
        # hint the user that they may wish to `refresh_from_db`
        if dict_ is None:
            return ""

        if isinstance(dict_, str):
            warnings.warn(
                "TranslatedValues received a str, you may have a new model which hasn't called `refresh_from_db` yet"
            )
            return dict_
        if len(list(dict_)) == 0:
            return "empty"
        for lc in (lang, *fallback, list(dict_)[0]):
            if lc in dict_:
                return dict_[lc]


class TranslatedField(JSONField):
    """
    When a string is passed to this field
    it will be saved as a value corresponding
    to the "LANGUAGE_CODE" key
    """

    description = "A translated char field storing content as JSON"

    def from_db_value(self, value, expression, connection):
        value_: dict | None = super().from_db_value(value, expression, connection)
        return TranslatedValues(value_)

    def to_python(self, value):
        value_ = super().to_python(value)
        return TranslatedValues(value_)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
