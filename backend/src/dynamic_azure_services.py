"""Dynamic Azure STT/TTS services for multilingual language tutor.

Language detection strategy:
- Azure F0 free tier does NOT support continuous language identification.
- Instead we use 'lingua' to detect language from the transcribed text locally.
- This runs free, offline, and works on short utterances.
"""

from loguru import logger
from pipecat.services.azure.stt import AzureSTTService
from pipecat.services.azure.tts import AzureTTSService


class AzureContinuousLanguageSTTService(AzureSTTService):
    """Azure STT with continuous language identification.

    This lets Azure detect English, Moroccan Arabic, Chinese, or Swedish
    without recreating the STT service for each language.
    """

    def __init__(
        self,
        *,
        api_key: str,
        region: str,
        languages: list[str],
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

        # Azure continuous LID requires the speech v2 endpoint.
        # Format: wss://{region}.stt.speech.microsoft.com/speech/universal/v2
        self._speech_v2_endpoint = (
            f"wss://{region}.stt.speech.microsoft.com/speech/universal/v2"
        )

    async def _connect(self):
        """Override Pipecat Azure STT connection to enable language auto-detect."""
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
            from azure.cognitiveservices.speech.dialog import AudioConfig
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
            self._speech_recognizer.recognized.connect(
                self._on_handle_recognized
            )
            self._speech_recognizer.canceled.connect(
                self._on_handle_canceled
            )

            self._speech_recognizer.start_continuous_recognition_async()

            logger.info(
                f"Azure STT continuous language ID enabled for: {self._languages}"
            )

        except Exception as e:
            await self.push_error(
                error_msg=f"Azure multilingual STT initialization failed: {e}",
                exception=e,
            )


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
