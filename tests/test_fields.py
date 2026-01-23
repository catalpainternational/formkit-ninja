"""
Tests for formkit_ninja.fields module.

This module tests:
- WhitelistedKeysDict: Dictionary with key filtering
- TranslatedValues: Language-aware dictionary with fallbacks
- TranslatedField: Django field for translated content
"""

import pytest
from django.test import override_settings
from django.utils import translation

from formkit_ninja.fields import TranslatedField, TranslatedValues, WhitelistedKeysDict


class TestWhitelistedKeysDict:
    """Tests for WhitelistedKeysDict class"""

    def test_init_with_string_and_default_key(self):
        """Test initialization with string and default_key"""
        d = WhitelistedKeysDict("hello", default_key="en")
        assert d["en"] == "hello"
        assert len(d) == 1

    def test_init_with_string_no_default_key(self):
        """Test initialization with string but no default_key warns"""
        with pytest.warns(UserWarning, match="No default key was set"):
            d = WhitelistedKeysDict("hello")
            assert len(d) == 0

    def test_init_with_dict_and_permitted_keys(self):
        """Test initialization with dict and permitted_keys"""
        # Note: WhitelistedKeysDict doesn't filter on init, only on __setitem__
        # So invalid keys are present initially but filtered when setting new values
        d = WhitelistedKeysDict(
            {"en": "hello", "tet": "ola", "invalid": "should-be-filtered"},
            permitted_keys={"en", "tet"},
        )
        assert d["en"] == "hello"
        assert d["tet"] == "ola"
        # Invalid key is present in init (not filtered), but can't be set via __setitem__
        assert "invalid" in d  # Present from init
        # But setting it would be filtered
        with pytest.warns(UserWarning, match="ignored key not in whitelist"):
            d["invalid2"] = "value"
        assert "invalid2" not in d

    def test_init_with_dict_no_permitted_keys(self):
        """Test initialization with dict but no permitted_keys allows all"""
        d = WhitelistedKeysDict({"en": "hello", "tet": "ola"})
        assert d["en"] == "hello"
        assert d["tet"] == "ola"
        assert len(d) == 2

    def test_setitem_with_permitted_key(self):
        """Test setting item with permitted key"""
        d = WhitelistedKeysDict(permitted_keys={"en", "tet"}, default_key="en")
        d["en"] = "hello"
        assert d["en"] == "hello"

    def test_setitem_with_non_permitted_key(self):
        """Test setting item with non-permitted key warns and ignores"""
        d = WhitelistedKeysDict(permitted_keys={"en", "tet"}, default_key="en")
        with pytest.warns(UserWarning, match="ignored key not in whitelist"):
            d["invalid"] = "value"
        assert "invalid" not in d

    def test_default_key_added_to_permitted_keys(self):
        """Test that default_key is automatically added to permitted_keys"""
        d = WhitelistedKeysDict(default_key="en", permitted_keys={"tet"})
        assert "en" in d.permitted_keys
        assert "tet" in d.permitted_keys

    def test_empty_dict_initialization(self):
        """Test initialization with empty dict"""
        d = WhitelistedKeysDict({}, permitted_keys={"en", "tet"})
        assert len(d) == 0

    def test_keys_filtering(self):
        """Test that setting new keys filters to permitted keys only"""
        d = WhitelistedKeysDict(permitted_keys={"en", "tet"})
        d["en"] = "hello"
        d["tet"] = "ola"
        # Try to set invalid key - should be filtered
        with pytest.warns(UserWarning, match="ignored key not in whitelist"):
            d["invalid"] = "bad"
        keys = set(d.keys())
        assert keys == {"en", "tet"}
        assert "invalid" not in keys


class TestTranslatedValues:
    """Tests for TranslatedValues class"""

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_init_with_string(self):
        """Test initialization with string uses current language as key"""
        with translation.override("en"):
            d = TranslatedValues("hello")
            assert d["en"] == "hello"
            assert len(d) == 1

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_init_with_dict(self):
        """Test initialization with dict - invalid keys present but filtered on set"""
        # Note: WhitelistedKeysDict doesn't filter on init, only on __setitem__
        d = TranslatedValues({"en": "hello", "tet": "ola", "invalid": "bad"})
        assert d["en"] == "hello"
        assert d["tet"] == "ola"
        # Invalid key is present from init, but setting new invalid keys would be filtered
        assert "invalid" in d  # Present from init
        # But new invalid keys are filtered
        with pytest.warns(UserWarning, match="ignored key not in whitelist"):
            d["invalid2"] = "value"
        assert "invalid2" not in d

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_value_property_current_language(self):
        """Test value property returns current language"""
        with translation.override("en"):
            d = TranslatedValues({"en": "hello", "tet": "ola"})
            assert d.value == "hello"

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_value_property_fallback(self):
        """Test value property falls back when current language missing"""
        with translation.override("pt"):  # Not in LANGUAGES
            d = TranslatedValues({"en": "hello", "tet": "ola"})
            # Should fallback to first available or 'en'
            assert d.value in ("hello", "ola")

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_get_str_static_method_current_language(self):
        """Test get_str returns current language value"""
        with translation.override("en"):
            d = TranslatedValues({"en": "hello", "tet": "ola"})
            result = TranslatedValues.get_str(d, lang="en")
            assert result == "hello"

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_get_str_static_method_fallback(self):
        """Test get_str falls back through language chain"""
        d = TranslatedValues({"tet": "ola"})  # No 'en'
        # Should fallback to 'tet' or first available
        result = TranslatedValues.get_str(d, lang="en", fallback=("en",))
        assert result == "ola"  # Falls back to first available

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_get_str_static_method_custom_fallback(self):
        """Test get_str uses custom fallback chain"""
        d = TranslatedValues({"tet": "ola"})
        result = TranslatedValues.get_str(d, lang="en", fallback=("pt", "tet"))
        assert result == "ola"  # Uses 'tet' from fallback

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_get_str_static_method_none_input(self):
        """Test get_str handles None input"""
        result = TranslatedValues.get_str(None)
        assert result == ""

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_get_str_static_method_string_input(self):
        """Test get_str handles string input (should warn)"""
        with pytest.warns(UserWarning, match="TranslatedValues received a str"):
            result = TranslatedValues.get_str("hello")
            assert result == "hello"

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_get_str_static_method_empty_dict(self):
        """Test get_str handles empty dict"""
        d = TranslatedValues({})
        result = TranslatedValues.get_str(d)
        assert result == "empty"

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_get_str_static_method_first_available_fallback(self):
        """Test get_str falls back to first available key if all else fails"""
        d = TranslatedValues({"tet": "ola"})
        result = TranslatedValues.get_str(d, lang="pt", fallback=("pt",))
        assert result == "ola"  # Uses first available key

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum"), ("pt", "Portuguese")])
    def test_multiple_languages(self):
        """Test with multiple languages"""
        d = TranslatedValues({"en": "hello", "tet": "ola", "pt": "olá"})
        assert d["en"] == "hello"
        assert d["tet"] == "ola"
        assert d["pt"] == "olá"
        assert len(d) == 3

    @override_settings(LANGUAGES=[("en", "English"), ("tet", "Tetum")])
    def test_permitted_keys_from_settings(self):
        """Test that permitted_keys come from LANGUAGES setting"""
        d = TranslatedValues({})
        assert "en" in d.permitted_keys
        assert "tet" in d.permitted_keys
        assert "pt" not in d.permitted_keys


class TestTranslatedField:
    """Tests for TranslatedField Django field"""

    @pytest.mark.django_db
    def test_from_db_value(self):
        """Test from_db_value converts JSON string to TranslatedValues"""
        import json

        field = TranslatedField()
        value = json.dumps({"en": "hello", "tet": "ola"})  # JSON string from DB
        result = field.from_db_value(value, None, None)
        assert isinstance(result, TranslatedValues)
        assert result["en"] == "hello"
        assert result["tet"] == "ola"

    @pytest.mark.django_db
    def test_from_db_value_none(self):
        """Test from_db_value handles None"""
        field = TranslatedField()
        result = field.from_db_value(None, None, None)
        assert isinstance(result, TranslatedValues)
        assert len(result) == 0

    @pytest.mark.django_db
    def test_to_python_dict(self):
        """Test to_python converts dict to TranslatedValues"""
        field = TranslatedField()
        value = {"en": "hello", "tet": "ola"}
        result = field.to_python(value)
        assert isinstance(result, TranslatedValues)
        assert result["en"] == "hello"
        assert result["tet"] == "ola"

    @pytest.mark.django_db
    def test_to_python_string(self):
        """Test to_python converts string to TranslatedValues"""
        field = TranslatedField()
        with translation.override("en"):
            result = field.to_python("hello")
            assert isinstance(result, TranslatedValues)
            assert result["en"] == "hello"

    @pytest.mark.django_db
    def test_to_python_none(self):
        """Test to_python handles None"""
        field = TranslatedField()
        result = field.to_python(None)
        assert isinstance(result, TranslatedValues)
        assert len(result) == 0

    @pytest.mark.django_db
    def test_to_python_already_translated_values(self):
        """Test to_python handles already TranslatedValues instance"""
        field = TranslatedField()
        value = TranslatedValues({"en": "hello"})
        result = field.to_python(value)
        assert isinstance(result, TranslatedValues)
        assert result["en"] == "hello"
