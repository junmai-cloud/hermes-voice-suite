"""Discord voice bridge prototype.

This module intentionally keeps Discord, STT, and TTS at adapter boundaries.
The first bridge uses Pycord's recording sink; low-latency VAD and barge-in are
next-layer concerns, while the shared MeetingOrchestrator is already testable.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .audio import pcm_to_webm_opus
from .meeting import MeetingOrchestrator
from .metrics import SessionMetrics
from .retry import retry_call
from .streaming import StreamingSink


class Brain(Protocol):
    def answer(self, text: str) -> str: ...


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
        brain: Brain | None = None,
        meeting: MeetingOrchestrator | None = None,
        metrics: SessionMetrics | None = None,
    ) -> None:
        try:
            import discord
        except ImportError as exc:  # pragma: no cover - optional runtime dep
            raise RuntimeError("Install the voice extra: pip install -e '.[voice]'") from exc
        self.discord = discord
        self.settings = settings
        self.transcriber = transcriber
        self.synthesizer = synthesizer
        self.brain = brain
        self.meeting = meeting or MeetingOrchestrator()
        self.metrics = metrics or SessionMetrics()
        intents = discord.Intents.default()
        intents.message_content = True
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        self.bot = discord.Bot(intents=intents, loop=loop)
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

        @self.bot.slash_command(description="Listen continuously and split turns by silence")
        async def listen(ctx: discord.ApplicationContext):
            if not self.voice_client:
                await ctx.respond("先に /join を実行してください。", ephemeral=True)
                return
            if self.voice_client.is_recording():
                await ctx.respond("すでに聞き取り中です。", ephemeral=True)
                return
            sink = StreamingSink.as_pycord_sink(self._on_pcm_turn, loop=asyncio.get_running_loop())
            self.voice_client.start_recording(sink, self._stream_finished, ctx.channel)
            await ctx.respond("自動聞き取りを開始しました。無音で発話を区切ります。")

        @self.bot.slash_command(description="Stop continuous listening")
        async def stop_listen(ctx: discord.ApplicationContext):
            if self.voice_client and self.voice_client.is_recording():
                self.voice_client.stop_recording()
            await ctx.respond("自動聞き取りを停止しました。")

        @self.bot.slash_command(description="Show privacy-safe session metrics")
        async def stats(ctx: discord.ApplicationContext):
            await ctx.respond(self.metrics.report(), ephemeral=True)

        @self.bot.slash_command(description="Show connection and listening status")
        async def health(ctx: discord.ApplicationContext):
            client = self.voice_client
            connected = client is not None
            recording = bool(client and client.is_recording())
            playing = bool(client and client.is_playing())
            await ctx.respond(
                f"接続: {'正常' if connected else '未接続'}。"
                f"聞き取り: {'実行中' if recording else '停止中'}。"
                f"再生: {'実行中' if playing else '停止中'}。",
                ephemeral=True,
            )

        @self.bot.slash_command(description="Stop the current voice turn")
        async def stop(ctx: discord.ApplicationContext):
            if not self.voice_client or not self.voice_client.is_recording():
                await ctx.respond("録音中ではありません。", ephemeral=True)
                return
            self.voice_client.stop_recording()
            await ctx.respond("音声を処理しています。")

    async def _on_pcm_turn(self, user_id: int, pcm: bytes) -> None:
        """Process one VAD-completed turn without taking down the bot."""
        started = time.monotonic()
        interrupted = self._interrupt_playback()
        output: Path | None = None
        try:
            if self.brain is None:
                return
            with tempfile.NamedTemporaryFile(prefix="hermes-turn-", suffix=".webm", delete=True) as raw:
                pcm_to_webm_opus(pcm, Path(raw.name))
                stt_bytes = Path(raw.name).stat().st_size
                text = await asyncio.to_thread(
                    retry_call,
                    lambda: self.transcriber.transcribe(Path(raw.name)),
                )
            user_text = self.meeting.user_turn(text)
            if not user_text:
                return
            reply_started = time.monotonic()
            reply = await asyncio.to_thread(
                retry_call,
                lambda: self._reply_for(user_text),
            )
            reply_seconds = time.monotonic() - reply_started
            with tempfile.NamedTemporaryFile(prefix="hermes-reply-", suffix=".mp3", delete=False) as raw_output:
                output = Path(raw_output.name)
            await asyncio.to_thread(
                retry_call,
                lambda: self.synthesizer.synthesize(reply, output),
            )
            self.metrics.record_turn(
                duration_seconds=time.monotonic() - started,
                stt_bytes=stt_bytes,
                reply_seconds=reply_seconds,
                interrupted=interrupted,
            )
            self._play_audio_file(output)
            output = None
        except Exception:
            self.metrics.record_error()
        finally:
            if output is not None:
                output.unlink(missing_ok=True)

    async def _stream_finished(self, sink, channel) -> None:
        return None

    def _interrupt_playback(self) -> bool:
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            return True
        return False

    def _play_audio_file(self, path: Path) -> None:
        if not self.voice_client or not path.exists():
            return
        self._interrupt_playback()
        source = self.discord.FFmpegPCMAudio(str(path))

        def cleanup(_error):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

        self.voice_client.play(source, after=cleanup)

    async def _recording_finished(self, sink, channel) -> None:
        """Transcribe each speaker's WAV and play a reply when available."""
        for user_id, audio in sink.audio_data.items():
            with tempfile.TemporaryDirectory(prefix="hermes-voice-") as temp:
                wav_path = Path(temp) / f"{user_id}.wav"
                audio.file.seek(0)
                wav_path.write_bytes(audio.file.read())
                text = await asyncio.to_thread(
                    retry_call,
                    lambda: self.transcriber.transcribe(wav_path),
                )
                user_text = self.meeting.user_turn(text)
                if not user_text:
                    continue
                reply = await asyncio.to_thread(
                    retry_call,
                    lambda: self._reply_for(user_text),
                )
                output = Path(temp) / "reply.mp3"
                await asyncio.to_thread(
                    retry_call,
                    lambda: self.synthesizer.synthesize(reply, output),
                )
                await channel.send(reply, file=self.discord.File(str(output)))

    def _reply_for(self, text: str) -> str:
        if self.brain is None:
            raise RuntimeError("A conversation brain is required before starting the voice bot")
        return self.meeting.prepare_reply(self.brain.answer(text))

    def run(self) -> None:
        self.bot.run(self.settings.token)
