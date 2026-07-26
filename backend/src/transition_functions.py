# ============= Shared Transition Functions =============
# These are created fresh each time a node is built,
# so the handler always returns the correct destination node.

from pipecat_flows import (
    FlowArgs,
    FlowManager,
    FlowsFunctionSchema,
    NodeConfig,
)

from conversation_config import (
    CONVERSATION_CONFIG,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE,
)

from loguru import logger

from pipecat_flows import (
    FlowArgs,
    FlowManager,
    FlowsFunctionSchema,
    NodeConfig,
)

from src.state import conv_state

def create_go_to_grammar_function() -> FlowsFunctionSchema:

    async def handle(args: FlowArgs, flow_manager: FlowManager):
        logger.info("Switching to grammar node")
        conv_state.current_node = "grammar"
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
        conv_state.current_node = "vocab"
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
        conv_state.current_node = "free_conversation"
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
        count_discussed = len(conv_state.discussed_topics)
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
    lang = conv_state.current_language
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
        if conv_state.current_language == language:
            logger.info(f"set_language: already in {language}, skipping rebuild")
            return (
                f"Already tutoring in {SUPPORTED_LANGUAGES[language]['display_name']}.",
                None,   # None = stay on current node, don't rebuild
            )

        conv_state.current_language = language
        cfg = SUPPORTED_LANGUAGES[language]
        display_name = cfg["display_name"]
        logger.info(f"Switched tutor language to {display_name}")

        await push_state_frame(flow_manager, conv_state.current_node)

        current_node = conv_state.current_node

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