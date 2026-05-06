"""Dynamic Azure STT/TTS services for multilingual language tutor.

Language detection strategy:
- Azure F0 free tier does NOT support continuous language identification.
- Instead we use 'lingua' to detect language from the transcribed text locally.
- This runs free, offline, and works on short utterances.
"""

import asyncio
from loguru import logger
from pipecat.services.azure.stt import AzureSTTService
from pipecat.services.azure.tts import AzureTTSService


# Maps lingua/langdetect language codes to our internal keys
LINGUA_TO_LANGUAGE = {
    "EN": "english",
    "SV": "swedish",
    "ZH": "chinese",
    "AR": "arabic_morocco",
}

# Minimum number of characters before attempting detection
# Short utterances like "yes" / "ok" are unreliable
MIN_DETECTION_LENGTH = 8

# How many consecutive utterances in the new language before switching
# Prevents single-word false positives from triggering a language change
CONFIRMATION_COUNT = 2


def _build_lingua_detector():
    """Build lingua detector for our 4 supported languages."""
    try:
        from lingua import Language, LanguageDetectorBuilder
        languages = [
            Language.ENGLISH,
            Language.SWEDISH,
            Language.CHINESE,
            Language.ARABIC,
        ]
        detector = (
            LanguageDetectorBuilder
            .from_languages(*languages)
            .with_minimum_relative_distance(0.15)  # confidence threshold
            .build()
        )
        logger.info("Lingua language detector initialized")
        return detector
    except ImportError:
        logger.warning(
            "lingua-language-detector not installed. "
            "Run: pip install lingua-language-detector\n"
            "Language auto-detection from speech disabled."
        )
        return None


# Module-level detector — built once, reused across all requests
_lingua_detector = _build_lingua_detector()


def detect_language_from_text(text: str) -> str | None:
    """Detect language from transcribed text.

    Returns internal language key e.g. 'swedish', or None if
    detection is unreliable (text too short, low confidence, etc.)
    """
    if not _lingua_detector:
        return None

    if not text or len(text.strip()) < MIN_DETECTION_LENGTH:
        return None

    try:
        result = _lingua_detector.detect_language_of(text.strip())
        if result is None:
            return None

        # lingua returns Language enum e.g. Language.SWEDISH
        # .iso_code_639_1.name gives us "SV"
        iso_code = result.iso_code_639_1.name.upper()
        language_key = LINGUA_TO_LANGUAGE.get(iso_code)

        logger.debug(f"Lingua detected: '{text[:40]}' -> {iso_code} -> {language_key}")
        return language_key

    except Exception as e:
        logger.error(f"Lingua detection error: {e}")
        return None


class AzureMultilingualSTTService(AzureSTTService):
    """Azure STT with local text-based language detection.

    Works on F0 free tier — does NOT use Azure's paid LID feature.
    Instead detects language from the transcribed text using lingua.

    On detection of a language change (confirmed over N utterances),
    calls on_language_detected(language_key).
    """

    def __init__(
        self,
        *,
        api_key: str,
        region: str,
        on_language_detected=None,
        sample_rate: int | None = None,
        **kwargs,
    ):
        # Pass a neutral language to Azure — we handle detection ourselves
        super().__init__(
            api_key=api_key,
            region=region,
            language="en-US",   # Azure still needs a base language for acoustic model
            sample_rate=sample_rate,
            **kwargs,
        )
        self._on_language_detected = on_language_detected
        self._event_loop = None

        # Confirmation tracking — avoid flipping on single utterance
        self._pending_language = None       # candidate being confirmed
        self._pending_count = 0             # how many consecutive detections
        self._confirmed_language = "english"  # last confirmed language

    async def start(self, frame):
        """Capture event loop before Azure SDK threads start."""
        self._event_loop = asyncio.get_running_loop()
        await super().start(frame)

    def _on_handle_recognized(self, evt):
        """Override to intercept transcribed text for language detection."""
        # Let parent handle the transcription → pushes text into pipeline
        super()._on_handle_recognized(evt)

        if not self._on_language_detected or not self._event_loop:
            return

        text = getattr(evt.result, "text", "") or ""
        if not text.strip():
            return

        detected = detect_language_from_text(text)

        if detected is None:
            # Text too short or ambiguous — don't reset confirmation
            return

        if detected == self._confirmed_language:
            # Still in same language, reset any pending switch
            self._pending_language = None
            self._pending_count = 0
            return

        # New candidate language detected
        if detected == self._pending_language:
            self._pending_count += 1
        else:
            # Different candidate — restart confirmation count
            self._pending_language = detected
            self._pending_count = 1

        logger.debug(
            f"Language candidate: {detected} "
            f"({self._pending_count}/{CONFIRMATION_COUNT} confirmations)"
        )

        if self._pending_count >= CONFIRMATION_COUNT:
            # Confirmed — fire the switch
            self._confirmed_language = detected
            self._pending_language = None
            self._pending_count = 0

            logger.info(f"Language confirmed: switching to {detected}")

            future = asyncio.run_coroutine_threadsafe(
                self._on_language_detected(detected),
                self._event_loop,
            )
            future.add_done_callback(_log_future_error)


class DynamicAzureTTSService(AzureTTSService):
    """Azure TTS that switches voice and locale dynamically per response."""

    def __init__(
        self,
        *,
        language_getter,
        language_config: dict,
        api_key: str,
        region: str,
        default_language: str = "english",
        sample_rate: int = 16000,
        text_filters=None,
        **kwargs,
    ):
        self._language_getter = language_getter
        self._language_config = language_config
        self._default_language = default_language

        default_cfg = language_config[default_language]

        super().__init__(
            api_key=api_key,
            region=region,
            voice=default_cfg["tts_voice"],
            sample_rate=sample_rate,
            text_filters=text_filters,
            **kwargs,
        )

    def _construct_ssml(self, text: str) -> str:
        """Swap voice and locale to match current language before synthesis."""
        current_language = self._language_getter() or self._default_language
        cfg = self._language_config.get(
            current_language,
            self._language_config[self._default_language],
        )
        self._voice_id = cfg["tts_voice"]
        self._settings["language"] = cfg["locale"]
        return super()._construct_ssml(text)


def _log_future_error(future):
    """Surface errors from fire-and-forget async callbacks."""
    try:
        exc = future.exception()
        if exc:
            logger.error(f"Language detection callback raised: {exc}")
    except Exception:
        pass