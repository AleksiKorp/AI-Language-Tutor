import os

from dataclasses import dataclass, field

from conversation_config import (
    CONVERSATION_CONFIG,
    DEFAULT_LANGUAGE,
)

@dataclass
class ConversationState:
    all_topics: list
    current_node: str = "initial"
    discussed_topics: list = field(default_factory=list)
    responses: list = field(default_factory=list)
    current_topics: list = field(default_factory=list)
    current_language: str = "en"


conv_state = ConversationState(
    all_topics=CONVERSATION_CONFIG["topics"],
    current_language=os.getenv(
        "DEFAULT_TUTOR_LANGUAGE",
        DEFAULT_LANGUAGE,
    ),
)