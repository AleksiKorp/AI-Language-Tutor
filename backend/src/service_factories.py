import os

from conversation_config import (
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE,
)
from src.dynamic_azure_services import (
    AzureContinuousLanguageSTTService,
    DynamicAzureTTSService,
)
from loguru import logger

from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.azure.llm import AzureLLMService
from pipecat.utils.text.markdown_text_filter import MarkdownTextFilter

from src.state import conv_state

# ============= Service Factories =============

def create_llm_service():
    """Create LLM service based on LLM_PROVIDER env var."""
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "azure":
        return AzureLLMService(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            model=os.getenv("AZURE_OPENAI_MODEL", "gpt-4o-mini"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview"),
        )

    elif provider == "openai":
        return OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )


    elif provider == "google":
        from pipecat.services.google.llm import GoogleLLMService
        return GoogleLLMService(
            api_key=os.getenv("GOOGLE_API_KEY"),
            model=os.getenv("GOOGLE_MODEL", "gemini-2.0-flash"),
        )
    
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def create_stt_service():
    """Create STT service based on STT_PROVIDER env var."""
    provider = os.getenv("STT_PROVIDER", "azure").lower()

    if provider == "azure":
        # Azure will listen for all 4 languages.
        azure_locales = [
            cfg["locale"] for cfg in SUPPORTED_LANGUAGES.values()
        ]

        return AzureContinuousLanguageSTTService(
            api_key=os.getenv("AZURE_SPEECH_API_KEY"),
            region=os.getenv("AZURE_SPEECH_REGION"),
            languages=azure_locales,
            sample_rate=16000,
        )

    elif provider == "deepgram":
        from pipecat.services.deepgram.stt import DeepgramSTTService
        return DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
        )

    elif provider == "openai":
        from pipecat.services.openai.stt import OpenAISTTService
        return OpenAISTTService(
            api_key=os.getenv("OPENAI_API_KEY"),
        )

    else:
        raise ValueError(
            f"Unsupported STT provider: {provider}. "
            "Supported: azure, deepgram, openai"
        )

def get_current_language():
    return conv_state.current_language


def create_tts_service():
    """Create TTS service based on TTS_PROVIDER env var."""
    provider = os.getenv("TTS_PROVIDER", "azure").lower()

    if provider == "azure":
        return DynamicAzureTTSService(
            api_key=os.getenv("AZURE_SPEECH_API_KEY"),
            region=os.getenv("AZURE_SPEECH_REGION"),
            language_getter=get_current_language,
            language_config=SUPPORTED_LANGUAGES,
            default_language=DEFAULT_LANGUAGE,
            text_filters=[MarkdownTextFilter()],
            sample_rate=16000,
        )

    elif provider == "deepgram":
        from pipecat.services.deepgram.tts import DeepgramTTSService
        return DeepgramTTSService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            voice=os.getenv("DEEPGRAM_TTS_VOICE", "aura-asteria-en"),
        )

    elif provider == "openai":
        from pipecat.services.openai.tts import OpenAITTSService
        return OpenAITTSService(
            api_key=os.getenv("OPENAI_API_KEY"),
            voice=os.getenv("OPENAI_TTS_VOICE", "alloy"),
        )

    elif provider == "elevenlabs":
        from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
        return ElevenLabsTTSService(
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
        )

    else:
        raise ValueError(
            f"Unsupported TTS provider: {provider}. "
            "Supported: azure, deepgram, openai, elevenlabs"
        )
    
