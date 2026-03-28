import re

from emtranscriber.shared.i18n import TRANSLATIONS, UiTranslator, resolve_ui_language


def test_resolve_ui_language_honors_supported_value() -> None:
    assert resolve_ui_language("de") == "de"


def test_resolve_ui_language_fallbacks_on_unsupported_value() -> None:
    assert resolve_ui_language("pt") in {"en", "es", "de", "fr", "it"}


def test_translator_returns_spanish_translation_when_available() -> None:
    tr = UiTranslator("es")
    assert tr.t("main.new_job") == "Nuevo Job"


def test_credits_translation_label_is_available() -> None:
    tr = UiTranslator("it")
    assert tr.t("main.credits") == "Crediti"


def test_credits_content_is_localized_for_german() -> None:
    tr = UiTranslator("de")
    assert tr.t("credits.about_title") == "Ueber EMtranscriber"


def test_all_translation_entries_cover_supported_languages() -> None:
    required_languages = {"en", "it", "es", "de", "fr"}
    for key, bucket in TRANSLATIONS.items():
        assert required_languages.issubset(bucket.keys()), key


def test_translation_placeholders_are_consistent_across_languages() -> None:
    placeholder_re = re.compile(r"\{[^}]+\}")
    for key, bucket in TRANSLATIONS.items():
        reference = set(placeholder_re.findall(bucket["en"]))
        for lang in ("it", "es", "de", "fr"):
            assert set(placeholder_re.findall(bucket[lang])) == reference, (key, lang)
