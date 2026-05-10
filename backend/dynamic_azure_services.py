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