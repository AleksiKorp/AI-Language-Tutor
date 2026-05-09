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
    AzureMultilingualSTTService, 
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

_active_flow_manager = None

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
    
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def create_stt_service():
    """Create STT service with local text-based language detection."""
    provider = os.getenv("STT_PROVIDER", "azure").lower()

    if provider == "azure":
        return AzureMultilingualSTTService(
            api_key=os.getenv("AZURE_SPEECH_API_KEY"),
            region=os.getenv("AZURE_SPEECH_REGION"),
            sample_rate=16000,
            on_language_detected=handle_stt_language_detection,
        )
    else:
        raise ValueError(f"Unsupported STT provider: {provider}")

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

async def handle_stt_language_detection(detected_language_key: str):
    """Called by STT when it detects the user is speaking a different language.

    This automatically switches conv_state and rebuilds the current node
    so the TTS voice, LLM prompt language, and tool registration all update
    to match what the user is actually speaking.
    """
    current = conv_state.get("current_language", DEFAULT_LANGUAGE)

    if current == detected_language_key:
        return

    cfg = SUPPORTED_LANGUAGES.get(detected_language_key)
    if not cfg:
        return

    conv_state["current_language"] = detected_language_key
    display_name = cfg["display_name"]

    logger.info(
        f"Auto language switch: {current} -> {detected_language_key} ({display_name})"
    )

    # We don't have direct access to flow_manager here since this is a module-level
    # callback — so we use the shared pipeline task reference instead.
    # _active_flow_manager is set in run_bot() below.
    flow_manager = _active_flow_manager
    if not flow_manager:
        return

    await push_state_frame(flow_manager, conv_state.get("current_node", "initial"))

    # Rebuild the current node with the new language injected into prompts
    # This also re-registers all tools including set_language
    current_node = conv_state.get("current_node", "initial")
    node_map = {
        "grammar": create_grammar_node,
        "vocab": create_vocab_node,
        "free_conversation": create_free_conv_node,
        "initial": create_initial_node,
    }
    node_builder = node_map.get(current_node, create_initial_node)

    try:
        await flow_manager.set_node(f"{current_node}_lang_switch", node_builder())
        logger.info(f"Node rebuilt for language: {display_name}")
    except Exception as e:
        logger.error(f"Failed to rebuild node after language detection: {e}")

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

    else:
        raise ValueError(
            f"Unsupported TTS provider: {provider}. "
            "Supported: azure"
        )
    
def create_set_language_function() -> FlowsFunctionSchema:
    async def handle_set_language(
        args: FlowArgs,
        flow_manager: FlowManager,
    ) -> tuple[str | None, NodeConfig]:
        language = args.get("language", "").lower().strip()

        if language not in SUPPORTED_LANGUAGES:
            language = DEFAULT_LANGUAGE

        conv_state["current_language"] = language
        cfg = SUPPORTED_LANGUAGES[language]
        display_name = cfg["display_name"]
        logger.info(f"Switched language to {display_name}")

        await push_state_frame(flow_manager, conv_state.get("current_node", "initial"))

        current_node = conv_state.get("current_node", "initial")
        node_map = {
            "grammar": create_grammar_node,
            "vocab": create_vocab_node,
            "free_conversation": create_free_conv_node,
            "initial": create_initial_node,
        }
        node_builder = node_map.get(current_node, create_initial_node)

        next_node = node_builder()

        # Inject a spoken confirmation without using LLM tokens
        existing_pre_actions = next_node.get("pre_actions", [])
        next_node["pre_actions"] = [
            {
                "type": "tts_say",
                "text": get_language_announcement(language),
            },
            *existing_pre_actions,
        ]

        return None, next_node

    return FlowsFunctionSchema(
        name="set_language",
        description="Switch the tutor's target language.",
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
        await push_state_frame(flow_manager, "grammar")
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
                "content": config["role_prompt"] + language_instruction(),
            }
        ],
        "task_messages": [
            {"role": "system", "content": config["task_prompt"]}
        ],
        "pre_actions": [
            {
                "type": "tts_say",
                "text": get_mode_announcement("grammar"),
            }
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
        "pre_actions": [
            {
                "type": "tts_say",
                "text": get_mode_announcement("vocab"),
            }
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
        "pre_actions": [
            {
                "type": "tts_say",
                "text": get_mode_announcement("free_conversation"),
            }
        ],
        "functions": [
            create_set_language_function(),
            create_go_to_grammar_function(),
            create_go_to_vocab_function(),
            create_exit_function(),
        ],
        "respond_immediately": False,
    }

def get_mode_announcement(node_name: str) -> str:
    """Short fixed phrase spoken when entering a mode."""
    lang = conv_state.get("current_language", DEFAULT_LANGUAGE)

    announcements = {
        "english": {
            "grammar": "Okay, grammar mode.",
            "vocab": "Okay, vocabulary mode.",
            "free_conversation": "Okay, free conversation mode.",
        },
        "swedish": {
            "grammar": "Okej, grammatikläge.",
            "vocab": "Okej, ordförrådsläge.",
            "free_conversation": "Okej, fritt samtal.",
        },
        "chinese": {
            "grammar": "好的，现在是语法模式。",
            "vocab": "好的，现在是词汇模式。",
            "free_conversation": "好的，现在是自由对话模式。",
        },
        "arabic_morocco": {
            "grammar": "حسنًا، وضع القواعد.",
            "vocab": "حسنًا، وضع المفردات.",
            "free_conversation": "حسنًا، وضع المحادثة الحرة.",
        },
    }

    return announcements.get(lang, announcements["english"]).get(
        node_name, "Okay."
    )


def get_language_announcement(language_key: str) -> str:
    """Short fixed phrase spoken when switching language."""
    announcements = {
        "english": "Okay, let's continue in English.",
        "swedish": "Okej, vi fortsätter på svenska.",
        "chinese": "好的，我们继续用中文。",
        "arabic_morocco": "حسنًا، سنواصل بالعربية.",
    }
    return announcements.get(language_key, announcements["english"])

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

    # Make flow_manager accessible to the STT language detection callback
    global _active_flow_manager
    _active_flow_manager = flow_manager

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, _client):
        logger.info("Client connected - starting tutor flow")
        conv_state["discussed_topics"] = []
        conv_state["responses"] = {}
        conv_state["current_topics"] = []
        conv_state["current_node"] = "initial"
        conv_state["current_language"] = os.getenv(
            "DEFAULT_TUTOR_LANGUAGE", DEFAULT_LANGUAGE
        )

        # Reset STT language state for new session
        if hasattr(stt, "_confirmed_language"):
            stt._confirmed_language = conv_state["current_language"]
            stt._pending_language = None
            stt._pending_count = 0

        await flow_manager.initialize(create_initial_node())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, _client):
        global _active_flow_manager
        _active_flow_manager = None
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