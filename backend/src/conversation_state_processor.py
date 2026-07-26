from typing import Any, Dict

from pipecat.frames.frames import (
    Frame,
    FunctionCallResultFrame,
    LLMFullResponseEndFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import (
    RTVIServerMessageFrame,
)

from src.state import conv_state

# ============= Custom Frame Processors =============


class ConversationStateProcessor(FrameProcessor):
    """Sends conversation state updates to the frontend via RTVI messages."""

    def __init__(self, conv_state: dict):
        super().__init__()
        self.conv_state = conv_state
        self.last_sent_state: Dict[str, Any] = {}

    async def send_state_update(self):

        current_state = {
            "type": "conversation_state_update",
            "all_topics": self.conv_state.all_topics,
            "discussed_topics": self.conv_state.discussed_topics,
            "current_topics": self.conv_state.current_topics,
            "responses": self.conv_state.responses,
            "current_node": self.conv_state.current_node,
            "progress": f"{len(self.conv_state.discussed_topics)}/{len(self.conv_state.all_topics)}",
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
