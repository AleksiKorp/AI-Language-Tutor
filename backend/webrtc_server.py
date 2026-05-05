#!/usr/bin/env python3
"""Language Tutor Course Assistant - Pipecat Flows + WebRTC."""

import os
from typing import Any, Dict

from dotenv import load_dotenv
from conversation_config import (
    CONVERSATION_CONFIG,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE,
)
from dynamic_azure_services import (
    AzureContinuousLanguageSTTService,
    DynamicAzureTTSService,
)
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    Frame,
    FunctionCallResultFrame,
    LLMFullResponseEndFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.filters.stt_mute_filter import (
    STTMuteConfig,
    STTMuteFilter,
    STTMuteStrategy,
)
from pipecat.processors.frameworks.rtvi import (
    RTVIProcessor,
    RTVIConfig,
    RTVIObserver,
    RTVIServerMessageFrame,
)
from pipecat.runner.types import SmallWebRTCRunnerArguments
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.azure.llm import AzureLLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.utils.text.markdown_text_filter import MarkdownTextFilter

from pipecat_flows import (
    FlowArgs,
    FlowManager,
    FlowsFunctionSchema,
    NodeConfig,
)

load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    override=True,
)

pcs_map: Dict[str, Any] = {}

conv_state = {
    "all_topics": CONVERSATION_CONFIG["topics"],
    "current_node": "initial",
    "discussed_topics": [],
    "responses": [],
    "current_topics": [],
    "current_language": os.getenv("DEFAULT_TUTOR_LANGUAGE", DEFAULT_LANGUAGE),
}


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
    return conv_state.get("current_language", DEFAULT_LANGUAGE)

# ADD THIS — was referenced but never defined
async def push_state_frame(flow_manager: FlowManager, current_node: str):
    """Push a conversation state update to the frontend via RTVI."""
    if hasattr(flow_manager, "_task") and flow_manager._task:
        await flow_manager._task.queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "conversation_state_update",
                    "all_topics": conv_state["all_topics"],
                    "current_node": current_node,
                    "current_language": conv_state.get("current_language", DEFAULT_LANGUAGE),
                    "current_language_display": SUPPORTED_LANGUAGES.get(
                        conv_state.get("current_language", DEFAULT_LANGUAGE), {}
                    ).get("display_name", "English"),
                }
            )
        )


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
    
def create_set_language_function() -> FlowsFunctionSchema:

    async def handle_set_language(
        args: FlowArgs,
        flow_manager: FlowManager,
    ) -> tuple[str | None, NodeConfig]:
        language = args.get("language", "").lower().strip()

        # Guard: if language not recognized, default and log
        if language not in SUPPORTED_LANGUAGES:
            logger.warning(
                f"set_language called with unknown language '{language}', "
                f"defaulting to {DEFAULT_LANGUAGE}"
            )
            language = DEFAULT_LANGUAGE

        # Guard: if already in this language, don't rebuild node
        if conv_state.get("current_language") == language:
            logger.info(f"set_language: already in {language}, skipping rebuild")
            return (
                f"Already tutoring in {SUPPORTED_LANGUAGES[language]['display_name']}.",
                None,   # None = stay on current node, don't rebuild
            )

        conv_state["current_language"] = language
        cfg = SUPPORTED_LANGUAGES[language]
        display_name = cfg["display_name"]
        logger.info(f"Switched tutor language to {display_name}")

        await push_state_frame(flow_manager, conv_state.get("current_node", "initial"))

        # Rebuild the CURRENT node (with the new language injected into prompts)
        current_node = conv_state.get("current_node", "initial")

        node_map = {
            "grammar": create_grammar_node,
            "vocab": create_vocab_node,
            "free_conversation": create_free_conv_node,
            "initial": create_initial_node,
        }
        node_builder = node_map.get(current_node, create_initial_node)

        return (
            f"Language switched to {display_name}. Continue tutoring in {display_name}.",
            node_builder(),
        )

    return FlowsFunctionSchema(
        name="set_language",
        description="""Switch the tutor's target language.

        Use this when the user asks to change language, for example:
        - "switch to English"
        - "let's practice Swedish"
        - "I want Chinese"
        - "change to Moroccan Arabic"
        - "خلينا بالدارجة"
        - "说中文"
        - "vi kan prata svenska"

        The bot should then continue speaking in the selected language.
        """,
        properties={
            "language": {
                "type": "string",
                "enum": list(SUPPORTED_LANGUAGES.keys()),
                "description": "The target language to switch to.",
            }
        },
        required=["language"],
        handler=handle_set_language,
    )


# ============= Custom Frame Processors =============


class ConversationStateProcessor(FrameProcessor):
    """Sends conversation state updates to the frontend via RTVI messages."""

    def __init__(self, conv_state: dict):
        super().__init__()
        self.conv_state = conv_state
        self.last_sent_state: Dict[str, Any] = {}

    async def send_state_update(self):
        #current_state = build_state_frame(self.conv_state["current_node"])

        current_state = {
            "type": "conversation_state_update",
            "all_topics": self.conv_state["all_topics"],
            "discussed_topics": self.conv_state["discussed_topics"],
            "current_topics": self.conv_state.get("current_topics", []),
            "responses": self.conv_state["responses"],
            "current_node": self.conv_state.get("current_node", "initial"),
            "progress": f"{len(self.conv_state['discussed_topics'])}/{len(self.conv_state['all_topics'])}",
        }

        state_changed = current_state != self.last_sent_state or current_state.get(
            "current_node"
        ) != self.last_sent_state.get("current_node")

        if state_changed:
            await self.push_frame(RTVIServerMessageFrame(data=current_state))
            self.last_sent_state = current_state.copy()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, (LLMFullResponseEndFrame, FunctionCallResultFrame)):
            await self.send_state_update()

        await self.push_frame(frame, direction)



# ============= Shared Transition Functions =============
# These are created fresh each time a node is built,
# so the handler always returns the correct destination node.


def create_go_to_grammar_function() -> FlowsFunctionSchema:

    async def handle(args: FlowArgs, flow_manager: FlowManager):
        logger.info("Switching to grammar node")
        conv_state["current_node"] = "grammar"
        await push_state_frame(flow_manager, "grammar")  # was "vocab" — wrong!
        return None, create_grammar_node()

    return FlowsFunctionSchema(
        name="go_to_grammar",
        description="""Switch to grammar practice mode.

        Triggers: user asks about grammar, sentence structure,
        tenses, conjugation, or says "let's do grammar" """,
        properties={},
        required=[],
        handler=handle,
    )


def create_go_to_vocab_function() -> FlowsFunctionSchema:
    """Transition to vocabulary practice node."""

    async def handle(args: FlowArgs, flow_manager: FlowManager):
        logger.info("Switching to vocab node")
        conv_state["current_node"] = "vocab"
        await push_state_frame(flow_manager, "vocab")
        return None, create_vocab_node()

    return FlowsFunctionSchema(
        name="go_to_vocab",
        description="""Switch to vocabulary practice mode.

        Triggers: user asks about words, vocabulary, 
        meaning of words, or says "let's do vocabulary" """,
        properties={},
        required=[],
        handler=handle,
    )


def create_go_to_free_conv_function() -> FlowsFunctionSchema:
    """Transition to free conversation node."""

    async def handle(args: FlowArgs, flow_manager: FlowManager):
        logger.info("Switching to free conversation node")
        conv_state["current_node"] = "free_conversation"
        await push_state_frame(flow_manager, "free_conversation")
        return None, create_free_conv_node()

    return FlowsFunctionSchema(
        name="go_to_free_conversation",
        description="""Switch to free conversation practice mode.

        Triggers: user wants to chat freely, practice speaking,
        have a conversation, or says "let's just talk" """,
        properties={},
        required=[],
        handler=handle,
    )


def create_exit_function() -> FlowsFunctionSchema:
    """Create a function that allows users to exit the conversation."""

    async def handle_exit_conversation(
        args: FlowArgs, flow_manager: FlowManager
    ) -> tuple[str | None, NodeConfig]:
        count_discussed = len(conv_state.get("discussed_topics", []))
        logger.info(f"User exiting after discussing {count_discussed} topics")

        return None, {
            "name": "exit",
            "task_messages": [
                {
                    "role": "system",
                    "content": CONVERSATION_CONFIG["functions"]["exit_prompt"],
                }
            ],
            "post_actions": [{"type": "end_conversation"}],
        }

    return FlowsFunctionSchema(
        name="exit_conversation",
        description="""End the tutoring session.

        ONLY exit for CLEAR exit signals:
        - "I want to quit/exit/stop"
        - "Goodbye" / "I'm done"
        - "That's all I need"

        When uncertain, ASK: "Do you want to end the conversation, or just move to another topic?" """,
        handler=handle_exit_conversation,
        properties={},
        required=[],
    )


def create_initial_node() -> NodeConfig:
    """Welcome node — choose a practice mode."""
    config = CONVERSATION_CONFIG["initial_node"]

    return {
        "name": "initial",
        "role_messages": [
            {"role": "system", "content": config["role_prompt"]}
        ],
        "task_messages": [
            {"role": "system", "content": config["task_prompt"]}
        ],
        # All three modes available from initial
        "functions": [
            create_set_language_function(),
            create_go_to_grammar_function(),
            create_go_to_vocab_function(),
            create_go_to_free_conv_function(),
        ],
        "respond_immediately": True,
    }


def language_instruction() -> str:
    """Get current language instruction to inject into every node prompt."""
    lang = conv_state.get("current_language", DEFAULT_LANGUAGE)
    cfg = SUPPORTED_LANGUAGES.get(lang, SUPPORTED_LANGUAGES[DEFAULT_LANGUAGE])
    return (
        f"\nCURRENT TARGET LANGUAGE: {cfg['prompt_name']}. "
        f"Reply in {cfg['prompt_name']} unless the user explicitly asks otherwise."
    )


def create_grammar_node() -> NodeConfig:
    config = CONVERSATION_CONFIG["grammar_node"]
    return {
        "name": "grammar",
        "role_messages": [
            {
                "role": "system",
                # Append language instruction to role prompt
                "content": config["role_prompt"] + language_instruction(),
            }
        ],
        "task_messages": [
            {"role": "system", "content": config["task_prompt"]}
        ],
        "functions": [
            create_set_language_function(),
            create_go_to_vocab_function(),
            create_go_to_free_conv_function(),
            create_exit_function(),
        ],
        "respond_immediately": False,
    }


def create_vocab_node() -> NodeConfig:
    config = CONVERSATION_CONFIG["vocab_node"]
    return {
        "name": "vocab",
        "role_messages": [
            {
                "role": "system",
                "content": config["role_prompt"] + language_instruction(),
            }
        ],
        "task_messages": [
            {"role": "system", "content": config["task_prompt"]}
        ],
        "functions": [
            create_set_language_function(),
            create_go_to_grammar_function(),
            create_go_to_free_conv_function(),
            create_exit_function(),
        ],
        "respond_immediately": False,
    }


def create_free_conv_node() -> NodeConfig:
    config = CONVERSATION_CONFIG["free_conv_node"]
    return {
        "name": "free_conversation",
        "role_messages": [
            {
                "role": "system",
                "content": config["role_prompt"] + language_instruction(),
            }
        ],
        "task_messages": [
            {"role": "system", "content": config["task_prompt"]}
        ],
        "functions": [
            create_set_language_function(),
            create_go_to_grammar_function(),
            create_go_to_vocab_function(),
            create_exit_function(),
        ],
        "respond_immediately": False,
    }

# ============= Bot Pipeline =============


async def run_bot(runner_args: SmallWebRTCRunnerArguments):
    """Set up and run the Pipecat pipeline with WebRTC transport.
    
    Flow: audio in -> VAD -> STT -> text -> LLM -> text -> TTS -> audio out
    """
    webrtc_connection = runner_args.webrtc_connection

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    stt = create_stt_service()
    tts = create_tts_service()
    llm = create_llm_service()

    context = LLMContext()
    context_aggregator = LLMContextAggregatorPair(context)

    # Mute STT while bot is speaking to prevent feedback loop
    stt_mute_filter = STTMuteFilter(
        config=STTMuteConfig(
        strategies={STTMuteStrategy.FIRST_SPEECH, STTMuteStrategy.FUNCTION_CALL}
    )
)

    rtvi = RTVIProcessor(config=RTVIConfig(config=[]), transport=transport)
    course_state_processor = ConversationStateProcessor(conv_state)

    pipeline = Pipeline(
        [
            transport.input(),       # raw audio in
            stt,                     # audio -> text
            stt_mute_filter,         # silence STT while bot speaks
            context_aggregator.user(),
            rtvi,
            llm,                     # text -> text
            course_state_processor,  # sync state to frontend
            tts,                     # text -> audio
            transport.output(),      # audio out
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
        observers=[RTVIObserver(rtvi)],
    )

    flow_manager = FlowManager(
        task=task,
        llm=llm,
        context_aggregator=context_aggregator,
        transport=transport,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, _client):
        logger.info("Client connected - starting tutor flow")
        conv_state["discussed_topics"] = []
        conv_state["responses"] = {}
        conv_state["current_topics"] = []
        conv_state["current_node"] = "initial"
        conv_state["current_language"] = os.getenv(
            "DEFAULT_TUTOR_LANGUAGE",
            DEFAULT_LANGUAGE,
        )       
        await flow_manager.initialize(create_initial_node())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, _client):
        logger.info("Client disconnected")

    @rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        logger.info("RTVI client ready")
        await rtvi.set_bot_ready()
        await course_state_processor.send_state_update()

    runner = PipelineRunner()
    await runner.run(task)


# ============= FastAPI App =============

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "healthy", "service": "Language Tutor Assistant"}


@app.post("/api/start")
async def start(request: dict, background_tasks: BackgroundTasks):
    return {"webrtcUrl": "/api/offer"}


@app.post("/api/offer")
async def offer(request: dict, background_tasks: BackgroundTasks):
    pc_id = request.get("pc_id")

    if pc_id and pc_id in pcs_map:
        pipecat_connection = pcs_map[pc_id]
        await pipecat_connection.renegotiate(
            sdp=request["sdp"],
            type=request["type"],
            restart_pc=request.get("restart_pc", False),
        )
    else:
        pipecat_connection = SmallWebRTCConnection()
        await pipecat_connection.initialize(sdp=request["sdp"], type=request["type"])

        @pipecat_connection.event_handler("closed")
        async def handle_disconnected(webrtc_connection: SmallWebRTCConnection):
            logger.info(f"Peer connection closed: {webrtc_connection.pc_id}")
            pcs_map.pop(webrtc_connection.pc_id, None)

        runner_args = SmallWebRTCRunnerArguments(webrtc_connection=pipecat_connection)
        background_tasks.add_task(run_bot, runner_args)

    answer = pipecat_connection.get_answer()
    pcs_map[answer["pc_id"]] = pipecat_connection
    return answer


if os.path.exists("/app/static/index.html"):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting server on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)