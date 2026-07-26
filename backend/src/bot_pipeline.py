import os

from conversation_config import DEFAULT_LANGUAGE

from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask

from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair

from pipecat.processors.filters.stt_mute_filter import (
    STTMuteConfig,
    STTMuteFilter,
    STTMuteStrategy,
)

from pipecat.processors.frameworks.rtvi import (
    RTVIObserver, RTVIConfig, RTVIProcessor
)
from pipecat.runner.types import SmallWebRTCRunnerArguments
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from pipecat_flows import FlowManager

from src.service_factories import (
    create_stt_service,
    create_tts_service,
    create_llm_service,
)

from src.conversation_state_processor import ConversationStateProcessor

from src.transition_functions import create_initial_node

from src.state import conv_state

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
        conv_state.discussed_topics = []
        conv_state.responses = {}
        conv_state.current_topics = []
        conv_state.current_node = "initial"
        conv_state.current_language = os.getenv(
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