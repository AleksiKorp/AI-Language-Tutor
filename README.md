# Conversational AI Language Tutor

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Node](https://img.shields.io/badge/Node.js-18+-green?logo=node.js&logoColor=white)
![pipecat-ai](https://img.shields.io/badge/pipecat--ai-0.0.86-7c3aed?logo=python&logoColor=white)
![pipecat-ai-flows](https://img.shields.io/badge/pipecat--ai--flows-0.0.22-7c3aed?logo=python&logoColor=white)

A real-time voice-based language tutoring application built with **Pipecat**, **WebRTC**, **FastAPI**, **React**, and modern AI services.

The system enables natural spoken interaction with an AI tutor capable of switching between grammar practice, vocabulary learning, and free conversation. The bot speaks 4 languages: English, Chinese, Swedish and Moroccoan Arabic allowing the user to communicate in English. It supports streaming speech recognition, large language models, speech synthesis, and real-time frontend synchronization through a state-driven conversation architecture.

<img width="1912" height="867" alt="Screenshot_20260728_211305" src="https://github.com/user-attachments/assets/4c4a945b-342e-41dd-85d7-b5cd418d68e8" />


## Features

### Real-Time Voice Interaction

- WebRTC-based audio streaming
- Voice Activity Detection (VAD)
- Speech-to-Text (STT)
- Text-to-Speech (TTS)
- Interruptible conversations
- Low-latency conversational experience

### AI-Powered Conversation Management

- Multi-node conversation flow architecture
- LLM-driven function calling
- Dynamic mode switching
- Context-aware tutoring
- Structured conversational state management

### Frontend Synchronization

- Real-time state updates
- Progress tracking
- Conversation mode indicators
- Responsive React UI
- Backend-to-frontend communication using RTVI

### Multi-Provider AI Support

The application supports different providers for each AI component:

| Service | Providers |
|----------|----------|
| LLM | OpenAI, Azure OpenAI, Google Gemini |
| STT | Azure Speech, Deepgram, OpenAI |
| TTS | Azure Speech, Deepgram, OpenAI, ElevenLabs |

Providers can be changed through environment variables without modifying application code.

---

# Architecture

```text
┌─────────────────────────────┐
│     React Frontend          │
│      TypeScript UI          │
└──────────────┬──────────────┘
               │
               │ WebRTC Audio
               │ RTVI Messages
               ▼
┌─────────────────────────────┐
│      FastAPI Backend        │
│        (Pipecat)            │
├─────────────────────────────┤
│ Voice Activity Detection    │
│ Speech Recognition (STT)    │
│ LLM Processing              │
│ Flow Management             │
│ State Synchronization       │
│ Speech Synthesis (TTS)      │
└──────────────┬──────────────┘
               │
               ▼
       AI Service Providers
```

---

# Conversation Flow

The application uses **Pipecat Flows** to manage conversation states through LLM function calls.

```text
                ┌─────────────┐
                │   Start     │
                └──────┬──────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼

 ┌────────────┐ ┌────────────┐ ┌──────────────┐
 │  Grammar   │ │ Vocabulary │ │ Free Chat    │
 └─────┬──────┘ └─────┬──────┘ └──────┬───────┘
       │              │               │
       └──────────────┼───────────────┘
                      ▼
                  End Session
```

The language model decides when to trigger transitions between nodes based on user intent.

Example function calls:

```python
go_to_grammar()
go_to_vocab()
go_to_free_conversation()
exit_conversation()
```

---

# Technical Highlights

## Function-Driven State Management

Instead of relying on hardcoded keyword matching, conversation transitions are implemented using LLM function calling.

This allows users to naturally say things such as:

- "Let's work on grammar."
- "Can we practice vocabulary?"
- "I'd like to just have a conversation."

The model determines which transition function to invoke.

---

## Real-Time Frontend Synchronization

One of the more interesting technical aspects of this project is the custom state synchronization layer between Pipecat and React.

Backend state is pushed using:

```python
RTVIServerMessageFrame
```

Frontend state is received through:

```typescript
onServerMessage()
```

This enables:

- Live UI updates
- Conversation progress tracking
- Dynamic mode switching
- State synchronization without page refreshes

---

## AI Provider Abstraction

Services are created through factory functions:

```python
create_llm_service()
create_stt_service()
create_tts_service()
```

Changing providers requires only environment variable updates:

```env
LLM_PROVIDER=openai
STT_PROVIDER=deepgram
TTS_PROVIDER=elevenlabs
```

No application logic needs to be modified.

---

# Technology Stack

## Backend

- Python 3.11+
- FastAPI
- Pipecat
- Pipecat Flows
- WebRTC
- Loguru
- Uvicorn

## Frontend

- React
- TypeScript
- Vite
- Pipecat Client SDK
- Web Audio API

## AI Services

### LLM Providers

- OpenAI GPT
- Azure OpenAI
- Google Gemini

### Speech Recognition

- Azure Speech
- Deepgram
- OpenAI Whisper

### Speech Synthesis

- Azure Speech
- Deepgram Aura
- OpenAI TTS
- ElevenLabs

---

## Project Structure

## Project Structure

```text
project-root/
│
├── backend/
│   ├── src/
│   │   ├── bot_pipeline.py
│   │   ├── conversation_state_processor.py
│   │   ├── dynamic_azure_services.py
│   │   ├── service_factories.py
│   │   ├── state.py
│   │   └── transition_functions.py
│   │
│   ├── .env.example
│   ├── conversation_config.py
│   ├── requirements.txt
│   └── webrtc_server.py
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── ShowcaseLayout.tsx
│   │   │
│   │   ├── App.tsx
│   │   ├── conversationInfoDisplayed.tsx
│   │   ├── index.css
│   │   └── main.tsx
│   │
│   ├── eslint.config.js
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts
│
├── .gitignore
├── LICENSES.md
├── package-lock.json
└── README.md
```

---

## Backend Setup

```bash
cd backend

python -m venv .venv

source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

pip install -r requirements.txt
```

Create environment configuration:

```bash
cp .env.example .env
```

Edit `.env` and add your API credentials.

Start the backend:

```bash
python webrtc_server.py
```

---

## Frontend Setup

Open a second terminal:

```bash
cd frontend

npm install
npm run dev
```

---

# Future Improvements

Potential future extensions include:

- Persistent conversation history
- Multi-language STT support
- Pronunciation scoring
- Broad character support in UI
- Retrieval-Augmented Generation (RAG)
- User analytics dashboard
- Session persistence

---

# Academic Context

This project was developed as part of coursework in conversational AI and voice interfaces at Tampere University (HTI.560). While initially created for academic purposes, the implementation was extended as a software engineering project focusing on real-time conversational systems, AI integration, and scalable conversation architecture.
