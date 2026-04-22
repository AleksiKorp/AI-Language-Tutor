# Pipecat-based conversational speech interface template

**HTI.560 Conversational Interaction with AI** (Tampere University)

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Node](https://img.shields.io/badge/Node.js-18+-green?logo=node.js&logoColor=white)
![pipecat-ai](https://img.shields.io/badge/pipecat--ai-0.0.86-7c3aed?logo=python&logoColor=white)
![pipecat-ai-flows](https://img.shields.io/badge/pipecat--ai--flows-0.0.22-7c3aed?logo=python&logoColor=white)

An AI-powered conversational language tutor that enables real-time voice interaction, helping users practice speaking, learn new expressions, and get instant translations. Built on a flexible Pipecat-based architecture, it can be adapted to different learning contexts with minimal configuration.

Requires API keys: [OpenAI](https://platform.openai.com/api-keys) (for the LLM) and a speech provider for voice input (STT/ASR) and output (TTS). You can use API keys from any service provider directly, eg. [Azure](https://portal.azure.com), [Deepgram](https://console.deepgram.com), or [OpenAI](https://platform.openai.com/api-keys).

## Structure

**Backend (using [Pipecat](https://docs.pipecat.ai/) + [Pipecat Flows](https://docs.pipecat.ai/guides/features/pipecat-flows)):**
- Conversation state machines with LLM function calling
- Real-time audio streaming via WebRTC (STT/TTS)
- Backend-to-frontend state sync via RTVI protocol

**Frontend (React + TypeScript + [Pipecat Client SDK](https://www.npmjs.com/package/@pipecat-ai/client-react)):**
- Real-time state management with WebRTC events
- Audio visualization (Web Audio API, waveform rendering)
- Responsive UI driven by conversation state

## How It Works

```
Browser (React)  ←── WebRTC audio + RTVI messages ──→  Backend (Pipecat)

Frontend receives state:                 Backend sends state:
onServerMessage callback                 RTVIServerMessageFrame
  ↓                                        ↑
Updates topic cards,                     FlowManager transitions between nodes:
transcript, visualizer                   initial → questions → back/exit
```

**The conversation has two nodes:**
1. **initial** — Bot greets user, waits for topic selection. When user asks about a topic, `record_topic_interest` fires → transitions to questions node
2. **questions** — Bot answers detailed questions about that topic. User can `go_back_to_topics` or `exit_conversation`

**Backend → frontend sync** (the part not well documented elsewhere):
- Backend pushes conversation state via [`RTVIServerMessageFrame`](https://docs.pipecat.ai/server/frameworks/rtvi/rtvi-processor) in `webrtc_server.py`
- Frontend receives it via [`onServerMessage`](https://docs.pipecat.ai/client/js/api-reference/callbacks) callback
- This is how topic cards update from ⭕ → ✅ in real time without page reloads
- See `ConversationStateProcessor` in `backend/webrtc_server.py` for the implementation


## Quick Start

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Then edit .env with your API keys
python webrtc_server.py

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.
