#!/usr/bin/env python3
"""
Simple websocket endpoint compatible with FreeSWITCH mod_audio_stream.

It accepts audio frames (L16) over WebSocket, writes them into WAV files,
and logs any JSON/text metadata that mod_audio_stream sends.
"""

from __future__ import annotations

import asyncio
import json
import logging
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import parse_qs, urlparse

import websockets
from websockets.asyncio.server import ServerConnection
from websockets.legacy.server import WebSocketServerProtocol


HOST: Final[str] = "0.0.0.0"
PORT: Final[int] = 3002
PATH: Final[str] = "/audio-stream"

STREAM_SAMPLE_RATE: Final[int] = 16000
STREAM_CHANNELS: Final[int] = 1  # mono frames by default
STREAM_SAMPLE_WIDTH: Final[int] = 2  # 16-bit PCM

HOST_RECORD_DIR = Path(
    "docker/storage/freeswitch/recordings"
).resolve()
HOST_RECORD_DIR.mkdir(parents=True, exist_ok=True)


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def _ts_prefix() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def _create_wav(uuid: str) -> wave.Wave_write:
    filename = f"{_ts_prefix()}_{uuid}_audio_stream.wav"
    host_path = HOST_RECORD_DIR / filename

    wav = wave.open(str(host_path), "wb")  # noqa: SIM115
    wav.setnchannels(STREAM_CHANNELS)
    wav.setsampwidth(STREAM_SAMPLE_WIDTH)
    wav.setframerate(STREAM_SAMPLE_RATE)
    logging.info("[audio_stream] Recording audio to %s", host_path)
    return wav


@dataclass(slots=True)
class StreamContext:
    uuid: str
    caller: str
    callee: str
    direction: str
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class StreamRecorder:
    ctx: StreamContext
    total_bytes: int = 0
    wav: wave.Wave_write = field(init=False)
    text_frames: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.wav = _create_wav(self.ctx.uuid or "unknown")

    def handle_text(self, payload: str) -> None:
        self.text_frames.append(payload)
        logging.info("[audio_stream] Text frame from %s: %s", self.ctx.uuid, payload)
        try:
            self.ctx.metadata = json.loads(payload)
            logging.debug("[audio_stream] Parsed metadata for %s: %s", self.ctx.uuid, self.ctx.metadata)
        except json.JSONDecodeError:
            logging.debug("[audio_stream] Text frame is not JSON for %s", self.ctx.uuid)

    def handle_audio(self, frame: bytes | bytearray) -> None:
        audio = bytes(frame)
        self.total_bytes += len(audio)
        self.wav.writeframes(audio)

    def close(self) -> None:
        try:
            self.wav.close()
        except Exception:
            pass

        if self.total_bytes:
            bytes_per_second = STREAM_SAMPLE_RATE * STREAM_CHANNELS * STREAM_SAMPLE_WIDTH
            seconds = self.total_bytes / float(bytes_per_second)
            logging.info(
                "[audio_stream] Stats for %s -> %.2f seconds (%d bytes)",
                self.ctx.uuid,
                seconds,
                self.total_bytes,
            )
        else:
            logging.warning("[audio_stream] No audio received for %s", self.ctx.uuid)


class AppAudioStream:
    """Minimal WebSocket server for mod_audio_stream demo."""

    def __init__(self, host: str = HOST, port: int = PORT, path: str = PATH) -> None:
        self.host: Final[str] = host
        self.port: Final[int] = port
        self.path: Final[str] = path

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"AppAudioStream(host={self.host!r}, port={self.port!r}, path={self.path!r})"

    async def _send_ready(self, websocket: ServerConnection | WebSocketServerProtocol, ctx: StreamContext) -> None:
        ack = {
            "type": "ready",
            "uuid": ctx.uuid,
            "message": "WebSocket endpoint connected",
        }
        await websocket.send(json.dumps(ack))
        logging.info("[audio_stream] Ready ack sent for %s", ctx.uuid)

    def _parse_context(self, full_path: str) -> StreamContext:
        parsed = urlparse(full_path)
        if parsed.path != self.path:
            logging.warning("[audio_stream] Unexpected path %s (expected %s)", parsed.path, self.path)
        query = parse_qs(parsed.query)
        return StreamContext(
            uuid=(query.get("uuid") or ["unknown"])[0],
            caller=(query.get("caller") or ["unknown"])[0],
            callee=(query.get("to") or ["unknown"])[0],
            direction=(query.get("direction") or ["unknown"])[0],
        )

    async def handle_call(
        self,
        websocket: ServerConnection | WebSocketServerProtocol,
    ) -> None:
        request = getattr(websocket, "request", None)
        if request is not None and hasattr(request, "path"):
            full_path = request.path  # type: ignore[assignment]
        else:
            full_path = getattr(websocket, "path", self.path) or self.path

        ctx = self._parse_context(full_path)
        logging.info(
            "[audio_stream] New session uuid=%s caller=%s callee=%s direction=%s",
            ctx.uuid,
            ctx.caller,
            ctx.callee,
            ctx.direction,
        )

        recorder = StreamRecorder(ctx)
        await self._send_ready(websocket, ctx)

        try:
            async for message in websocket:
                if isinstance(message, str):
                    recorder.handle_text(message)
                elif isinstance(message, (bytes, bytearray)):
                    recorder.handle_audio(message)
                else:
                    logging.warning("[audio_stream] Unsupported frame type %s", type(message))
        except websockets.ConnectionClosed as exc:  # pragma: no cover - network runtime
            logging.info("[audio_stream] Connection closed for %s: %s", ctx.uuid, exc)
        except Exception:  # pragma: no cover - runtime logging
            logging.exception("[audio_stream] Error handling session %s", ctx.uuid)
        finally:
            recorder.close()
            logging.info("[audio_stream] Session %s finished", ctx.uuid)

    async def serve(self) -> None:
        logging.info(
            "Starting AppAudioStream on ws://%s:%d%s (SR=%d, channels=%d)",
            self.host,
            self.port,
            self.path,
            STREAM_SAMPLE_RATE,
            STREAM_CHANNELS,
        )
        async with websockets.serve(self.handle_call, self.host, self.port):  # type: ignore[arg-type]
            await asyncio.Future()  # run forever


if __name__ == "__main__":
    server = AppAudioStream()
    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        logging.info("AppAudioStream stopped by user")
