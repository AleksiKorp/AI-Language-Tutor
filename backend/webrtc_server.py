#!/usr/bin/env python3
"""Language Tutor Course Assistant - Pipecat Flows + WebRTC."""

import os
from typing import Any, Dict

from dotenv import load_dotenv

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from pipecat.runner.types import SmallWebRTCRunnerArguments
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

from src.bot_pipeline import run_bot

load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    override=True,
)

pcs_map: Dict[str, Any] = {}

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