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
    allowed_user_id: int | None = None
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
            allowed_user_id=_optional_int("DISCORD_ALLOWED_USER_ID"),
        )

    def authorizes(self, *, user_id: int, guild_id: int | None, voice_channel_id: int | None) -> bool:
        if self.allowed_user_id is not None and user_id != self.allowed_user_id:
            return False
        if self.guild_id is not None and guild_id != self.guild_id:
            return False
        if self.voice_channel_id is not None and voice_channel_id != self.voice_channel_id:
            return False
        return True


def _optional_int(name: str) -> int | None:
    value = os.environ.get(name, "").strip()
    return int(value) if value else None


class VoiceBridge:
    """Pycord bridge for join/leave/start/stop and spoken replies."""

    # One early STT snapshot is enough to capture a conclusion-first request.
    # The rest of the utterance is transcribed once after VAD detects silence.
    VOICE_HEAD_MS = 2_000
    VOICE_HEAD_OVERLAP_MS = 400

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
        self._voice_head_tasks: dict[int, asyncio.Task] = {}
        self.bot = None
        # Keep the policy and audio-turn code importable in dependency-light
        # environments (and in tests).  The production runner's preflight
        # still requires Pycord before it attempts to connect to Discord.
        if not hasattr(discord, "Bot"):
            self.voice_client = None
            return
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

    def _authorized_current_voice(self, ctx) -> bool:
        channel = getattr(self.voice_client, "channel", None)
        guild_id = getattr(getattr(ctx, "guild", None), "id", None)
        channel_id = getattr(channel, "id", self.settings.voice_channel_id)
        return self.settings.authorizes(
            user_id=ctx.author.id,
            guild_id=guild_id,
            voice_channel_id=channel_id,
        )

    def _register_commands(self) -> None:
        discord = self.discord

        @self.bot.slash_command(description="Join your current voice channel")
        async def join(ctx: discord.ApplicationContext):
            if not getattr(ctx.author, "voice", None) or not ctx.author.voice.channel:
                await ctx.respond("先にボイスチャンネルへ入ってください。", ephemeral=True)
                return
            voice_channel = ctx.author.voice.channel
            guild_id = getattr(getattr(ctx, "guild", None), "id", None)
            if not self.settings.authorizes(
                user_id=ctx.author.id,
                guild_id=guild_id,
                voice_channel_id=voice_channel.id,
            ):
                await ctx.respond("この音声会議への参加権限がありません。", ephemeral=True)
                return
            self.voice_client = await voice_channel.connect()
            await ctx.respond("ボイス会議に参加しました。/record で録音を開始できます。")

        @self.bot.slash_command(description="Leave the voice channel")
        async def leave(ctx: discord.ApplicationContext):
            if not self._authorized_current_voice(ctx):
                await ctx.respond("この音声会議の操作権限がありません。", ephemeral=True)
                return
            if self.voice_client:
                await self._cancel_voice_head_tasks()
                await self.voice_client.disconnect()
                self.voice_client = None
            await ctx.respond("ボイス会議から退出しました。")

        @self.bot.slash_command(description="Start a voice turn recording")
        async def record(ctx: discord.ApplicationContext):
            if not self.voice_client:
                await ctx.respond("先に /join を実行してください。", ephemeral=True)
                return
            if not self._authorized_current_voice(ctx):
                await ctx.respond("この音声会議の操作権限がありません。", ephemeral=True)
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
            if not self._authorized_current_voice(ctx):
                await ctx.respond("この音声会議の操作権限がありません。", ephemeral=True)
                return
            if self.voice_client.is_recording():
                await ctx.respond("すでに聞き取り中です。", ephemeral=True)
                return
            sink = StreamingSink.as_pycord_sink(
                self._on_pcm_turn,
                on_head=self._schedule_voice_head,
                head_ms=self.VOICE_HEAD_MS,
                loop=asyncio.get_running_loop(),
            )
            self.voice_client.start_recording(sink, self._stream_finished, ctx.channel)
            await ctx.respond("自動聞き取りを開始しました。無音で発話を区切ります。")

        @self.bot.slash_command(description="Stop continuous listening")
        async def stop_listen(ctx: discord.ApplicationContext):
            if not self._authorized_current_voice(ctx):
                await ctx.respond("この音声会議の操作権限がありません。", ephemeral=True)
                return
            if self.voice_client and self.voice_client.is_recording():
                self.voice_client.stop_recording()
            await ctx.respond("自動聞き取りを停止しました。")

        @self.bot.slash_command(description="Show privacy-safe session metrics")
        async def stats(ctx: discord.ApplicationContext):
            if not self._authorized_current_voice(ctx):
                await ctx.respond("この音声会議の参照権限がありません。", ephemeral=True)
                return
            await ctx.respond(self.metrics.report(), ephemeral=True)

        @self.bot.slash_command(description="Show connection and listening status")
        async def health(ctx: discord.ApplicationContext):
            if not self._authorized_current_voice(ctx):
                await ctx.respond("この音声会議の参照権限がありません。", ephemeral=True)
                return
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
            if not self._authorized_current_voice(ctx):
                await ctx.respond("この音声会議の操作権限がありません。", ephemeral=True)
                return
            if not self.voice_client or not self.voice_client.is_recording():
                await ctx.respond("録音中ではありません。", ephemeral=True)
                return
            self.voice_client.stop_recording()
            await ctx.respond("音声を処理しています。")

    async def _on_pcm_turn(self, user_id: int, pcm: bytes) -> None:
        """Process one VAD-completed turn without taking down the bot."""
        head_task = self._voice_head_tasks.pop(user_id, None)
        if self.settings.allowed_user_id is not None and user_id != self.settings.allowed_user_id:
            if head_task and not head_task.done():
                head_task.cancel()
            return
        started = time.monotonic()
        interrupted = self._interrupt_playback()
        output: Path | None = None
        try:
            if self.brain is None:
                if head_task and not head_task.done():
                    head_task.cancel()
                return
            text, stt_bytes = await self._transcribe_two_stage(pcm, head_task)
            user_text = self.meeting.user_turn(text)
            if user_text and self.meeting.is_cancel_command(user_text):
                # Cancellation is terminal for this turn: do not call the brain,
                # do not synthesize, and do not execute any pending action.
                return
            if not user_text:
                self.metrics.record_clarification()
                reply = self.meeting.clarification_reply()
                with tempfile.NamedTemporaryFile(prefix="hermes-reply-", suffix=".mp3", delete=False) as raw_output:
                    clarification_output = Path(raw_output.name)
                output = clarification_output
                await asyncio.to_thread(
                    retry_call,
                    lambda: self.synthesizer.synthesize(reply, clarification_output),
                )
                self.metrics.record_turn(
                    duration_seconds=time.monotonic() - started,
                    stt_bytes=stt_bytes,
                    reply_seconds=0.0,
                    interrupted=interrupted,
                )
                self._play_audio_file(output)
                output = None
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

    def _schedule_voice_head(self, user_id: int, pcm: bytes) -> None:
        """Start exactly one non-queued STT task for the first two seconds."""
        existing = self._voice_head_tasks.get(user_id)
        if existing and not existing.done():
            # Never build a backlog.  The completed-turn path can still
            # transcribe the available audio without this early result.
            return
        loop = asyncio.get_running_loop()
        self._voice_head_tasks[user_id] = loop.create_task(
            self._transcribe_pcm(pcm, prefix="hermes-head-")
        )

    async def _transcribe_two_stage(
        self,
        pcm: bytes,
        head_task: asyncio.Task | None,
    ) -> tuple[str, int]:
        """Transcribe one head and one tail, never a queue of chunks."""
        bytes_per_ms = 48_000 * 2 // 1000
        head_bytes = bytes_per_ms * self.VOICE_HEAD_MS
        overlap_bytes = bytes_per_ms * self.VOICE_HEAD_OVERLAP_MS

        if head_task is None:
            return await self._transcribe_pcm(pcm, prefix="hermes-turn-")

        # For turns longer than the head window, transcribe the remaining
        # audio immediately.  A small overlap protects words at the boundary.
        tail_task = None
        if len(pcm) > head_bytes:
            tail_pcm = pcm[max(0, head_bytes - overlap_bytes):]
            tail_task = asyncio.create_task(
                self._transcribe_pcm(tail_pcm, prefix="hermes-tail-")
            )

        tasks = [head_task] + ([tail_task] if tail_task is not None else [])
        results = await asyncio.gather(*tasks, return_exceptions=True)

        head_result = results[0]
        tail_result = results[1] if tail_task is not None else None
        head_text, head_bytes_written = self._transcription_result(head_result)
        tail_text, tail_bytes_written = self._transcription_result(tail_result)
        text = self._merge_transcripts(head_text, tail_text)
        return text, head_bytes_written + tail_bytes_written

    async def _transcribe_pcm(self, pcm: bytes, *, prefix: str) -> tuple[str, int]:
        """Encode and transcribe one PCM segment, cleaning up its temp file."""
        input_path: Path | None = None
        try:
            # Close the temporary file before ffmpeg opens it.  Windows keeps
            # an open NamedTemporaryFile locked.
            with tempfile.NamedTemporaryFile(prefix=prefix, suffix=".webm", delete=False) as raw:
                input_path = Path(raw.name)
            pcm_to_webm_opus(pcm, input_path)
            stt_bytes = input_path.stat().st_size
            text = await asyncio.to_thread(
                retry_call,
                lambda: self.transcriber.transcribe(input_path),
            )
            return text, stt_bytes
        finally:
            if input_path is not None:
                input_path.unlink(missing_ok=True)

    @staticmethod
    def _transcription_result(result) -> tuple[str, int]:
        if isinstance(result, BaseException) or result is None:
            return "", 0
        text, stt_bytes = result
        return str(text or "").strip(), int(stt_bytes)

    @staticmethod
    def _merge_transcripts(head: str, tail: str) -> str:
        """Join overlapping Japanese/Latin STT text without obvious repeats."""
        head = head.strip()
        tail = tail.strip()
        if not head:
            return tail
        if not tail:
            return head
        max_overlap = min(64, len(head), len(tail))
        for size in range(max_overlap, 1, -1):
            if head[-size:] == tail[:size]:
                return f"{head}{tail[size:]}".strip()
        return f"{head} {tail}".strip()

    async def _cancel_voice_head_tasks(self) -> None:
        """Cancel early STT work without leaving tasks behind on disconnect."""
        tasks = [task for task in self._voice_head_tasks.values() if not task.done()]
        self._voice_head_tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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
        if self.bot is None:
            raise RuntimeError("Pycord is required to run the Discord voice bot")
        self.bot.run(self.settings.token)
