"""Dynamic Azure STT/TTS services for multilingual language tutor."""

from loguru import logger
from pipecat.services.azure.stt import AzureSTTService
from pipecat.services.azure.tts import AzureTTSService


# Maps Azure locale strings back to our internal language keys
LOCALE_TO_LANGUAGE = {
    "en-US": "english",
    "ar-SA": "arabic_morocco",
    "zh-CN": "chinese",
    "sv-SE": "swedish",
}


class AzureContinuousLanguageSTTService(AzureSTTService):
    """Azure STT with continuous language identification.

    Detects which of the 4 supported languages the user is speaking
    and calls on_language_detected(language_key) when it changes.
    """

    def __init__(
        self,
        *,
        api_key: str,
        region: str,
        languages: list[str],
        on_language_detected=None,   # callback: async fn(language_key: str)
        sample_rate: int | None = None,
        **kwargs,
    ):
        super().__init__(
            api_key=api_key,
            region=region,
            sample_rate=sample_rate,
            **kwargs,
        )

        self._api_key = api_key
        self._region = region
        self._languages = languages
        self._on_language_detected = on_language_detected
        self._last_detected_locale = None   # track changes, avoid duplicate triggers

        self._speech_v2_endpoint = (
            f"wss://{region}.stt.speech.microsoft.com/speech/universal/v2"
        )

    async def _connect(self):
        """Override to enable continuous language identification."""
        if self._audio_stream:
            return

        try:
            from azure.cognitiveservices.speech import (
                SpeechConfig,
                SpeechRecognizer,
                PropertyId,
            )
            from azure.cognitiveservices.speech.audio import (
                AudioStreamFormat,
                PushAudioInputStream,
            )
            from azure.cognitiveservices.speech.audio import AudioConfig
            from azure.cognitiveservices.speech.languageconfig import (
                AutoDetectSourceLanguageConfig,
            )

            stream_format = AudioStreamFormat(
                samples_per_second=self.sample_rate,
                channels=1,
            )
            self._audio_stream = PushAudioInputStream(stream_format)
            audio_config = AudioConfig(stream=self._audio_stream)

            speech_config = SpeechConfig(
                endpoint=self._speech_v2_endpoint,
                subscription=self._api_key,
            )

            # Continuous = re-detect language on every utterance, not just once
            speech_config.set_property(
                property_id=PropertyId.SpeechServiceConnection_LanguageIdMode,
                value="Continuous",
            )

            auto_detect_config = AutoDetectSourceLanguageConfig(
                languages=self._languages
            )

            self._speech_recognizer = SpeechRecognizer(
                speech_config=speech_config,
                auto_detect_source_language_config=auto_detect_config,
                audio_config=audio_config,
            )

            self._speech_recognizer.recognizing.connect(
                self._on_handle_recognizing
            )
            # Use our override instead of the parent's _on_handle_recognized
            self._speech_recognizer.recognized.connect(
                self._on_handle_recognized_with_lang
            )
            self._speech_recognizer.canceled.connect(
                self._on_handle_canceled
            )

            self._speech_recognizer.start_continuous_recognition_async()

            logger.info(
                f"Azure STT continuous language ID active for: {self._languages}"
            )

        except Exception as e:
            await self.push_error(
                error_msg=f"Azure multilingual STT init failed: {e}",
                exception=e,
            )

    def _on_handle_recognized_with_lang(self, evt):
        """Handle a recognized utterance and extract the detected language.

        Azure puts the detected locale in evt.result.properties under
        SpeechServiceConnection_AutoDetectSourceLanguageResult.
        We extract it, map it to our internal key, and fire the callback
        if the language has changed since last utterance.
        """
        # Always let the parent handle the transcription text normally
        self._on_handle_recognized(evt)

        if not self._on_language_detected:
            return

        try:
            from azure.cognitiveservices.speech import PropertyId

            detected_locale = evt.result.properties.get(
                PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult
            )

            if not detected_locale:
                return

            # Azure returns e.g. "en-US", "sv-SE", "zh-CN", "ar-SA"
            language_key = LOCALE_TO_LANGUAGE.get(detected_locale)

            if not language_key:
                logger.warning(
                    f"STT detected unrecognized locale '{detected_locale}', ignoring"
                )
                return

            # Only fire callback if language actually changed
            if detected_locale == self._last_detected_locale:
                return

            self._last_detected_locale = detected_locale
            logger.info(
                f"STT detected language change: {detected_locale} -> {language_key}"
            )

            # Schedule the async callback from this sync Azure SDK event
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(
                        self._on_language_detected(language_key)
                    )
            except RuntimeError:
                logger.warning("STT: could not schedule language detection callback")

        except Exception as e:
            logger.error(f"STT language detection extraction failed: {e}")


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