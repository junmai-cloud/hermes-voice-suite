"""Discord voice bridge prototype.

This module intentionally keeps Discord, STT, and TTS at adapter boundaries.
The first bridge uses Pycord's recording sink; low-latency VAD and barge-in are
next-layer concerns, while the shared MeetingOrchestrator is already testable.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .meeting import MeetingOrchestrator


class AudioTranscriber(Protocol):
    def transcribe(self, wav_path: Path) -> str: ...


class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str, output_path: Path) -> Path: ...


@dataclass(frozen=True)
class VoiceBotSettings:
    token: str
    guild_id: int | None = None
    voice_channel_id: int | None = None
    command_prefix: str = "!"

    @classmethod
    def from_env(cls) -> "VoiceBotSettings":
        token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_BOT_TOKEN is required")
        return cls(
            token=token,
            guild_id=_optional_int("DISCORD_GUILD_ID"),
            voice_channel_id=_optional_int("DISCORD_VOICE_CHANNEL_ID"),
        )


def _optional_int(name: str) -> int | None:
    value = os.environ.get(name, "").strip()
    return int(value) if value else None


class VoiceBridge:
    """Pycord bridge for join/leave/start/stop and spoken replies."""

    def __init__(
        self,
        settings: VoiceBotSettings,
        *,
        transcriber: AudioTranscriber,
        synthesizer: SpeechSynthesizer,
        meeting: MeetingOrchestrator | None = None,
    ) -> None:
        try:
            import discord
        except ImportError as exc:  # pragma: no cover - optional runtime dep
            raise RuntimeError("Install the voice extra: pip install -e '.[voice]'") from exc
        self.discord = discord
        self.settings = settings
        self.transcriber = transcriber
        self.synthesizer = synthesizer
        self.meeting = meeting or MeetingOrchestrator()
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = discord.Bot(intents=intents)
        self.voice_client = None
        self._register_commands()

    def _register_commands(self) -> None:
        discord = self.discord

        @self.bot.slash_command(description="Join your current voice channel")
        async def join(ctx: discord.ApplicationContext):
            if not getattr(ctx.author, "voice", None) or not ctx.author.voice.channel:
                await ctx.respond("先にボイスチャンネルへ入ってください。", ephemeral=True)
                return
            self.voice_client = await ctx.author.voice.channel.connect()
            await ctx.respond("ボイス会議に参加しました。/record で録音を開始できます。")

        @self.bot.slash_command(description="Leave the voice channel")
        async def leave(ctx: discord.ApplicationContext):
            if self.voice_client:
                await self.voice_client.disconnect()
                self.voice_client = None
            await ctx.respond("ボイス会議から退出しました。")

        @self.bot.slash_command(description="Start a voice turn recording")
        async def record(ctx: discord.ApplicationContext):
            if not self.voice_client:
                await ctx.respond("先に /join を実行してください。", ephemeral=True)
                return
            if self.voice_client.is_recording():
                await ctx.respond("すでに録音中です。", ephemeral=True)
                return
            await ctx.respond("聞いています。終わったら /stop を押してください。")
            self.voice_client.start_recording(
                self.discord.sinks.WaveSink(), self._recording_finished, ctx.channel
            )

        @self.bot.slash_command(description="Stop the current voice turn")
        async def stop(ctx: discord.ApplicationContext):
            if not self.voice_client or not self.voice_client.is_recording():
                await ctx.respond("録音中ではありません。", ephemeral=True)
                return
            self.voice_client.stop_recording()
            await ctx.respond("音声を処理しています。")

    async def _recording_finished(self, sink, channel) -> None:
        """Transcribe each speaker's WAV and play a reply when available."""
        for user_id, audio in sink.audio_data.items():
            with tempfile.TemporaryDirectory(prefix="hermes-voice-") as temp:
                wav_path = Path(temp) / f"{user_id}.wav"
                audio.file.seek(0)
                wav_path.write_bytes(audio.file.read())
                text = await asyncio.to_thread(self.transcriber.transcribe, wav_path)
                user_text = self.meeting.user_turn(text)
                if not user_text:
                    continue
                reply = await asyncio.to_thread(self._reply_for, user_text)
                output = Path(temp) / "reply.mp3"
                await asyncio.to_thread(self.synthesizer.synthesize, reply, output)
                await channel.send(reply, file=self.discord.File(str(output)))

    def _reply_for(self, text: str) -> str:
        # The Hermes adapter will replace this deterministic first bridge.
        return self.meeting.prepare_reply(f"受け取りました。次は『{text}』について整理します。")

    def run(self) -> None:
        self.bot.run(self.settings.token)
