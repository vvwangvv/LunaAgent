from typing import Dict, List
from asyncstdlib.itertools import tee
import asyncio
import logging
from uuid import uuid4
from typing import Optional

from luna_agent.utils import safe_create_task
from luna_agent.components import ASR, LLM, SLM, TTS, WebRTCEvent, WebRTCAudio, VAD
from luna_agent.components.slm import add_user_message, add_agent_message

logger = logging.getLogger("luna_agent")


class LunaAgent:
    sessions = {}

    def __init__(self, config):
        self.vad: VAD = config["vad"]
        self.asr: ASR = config["asr"]
        self.slm: SLM = config["slm"]
        self.tts: TTS = config["tts"]
        self.stream: WebRTCAudio = config["stream"]
        self.event: WebRTCEvent = config["event"]
        self.tts_control: Optional[LLM] = config["tts_control"]
        self.diar_control: Optional[LLM] = config["diar_control"]

        self.session_id = uuid4().hex
        self.sample_rate = 16000

        self.history: List[Dict] = []
        self._user_is_speaking = False
        self.buffer = b""

    @classmethod
    async def create(cls, config, user_audio_sample_rate: int = 16000):
        session = cls(config)
        await asyncio.gather(
            session.vad.setup(),
            session.stream.setup(user_audio_sample_rate=user_audio_sample_rate, session_id=session.session_id),
            session.event.setup(session_id=session.session_id),
            session.slm.setup(session_id=session.session_id),
        )
        cls.sessions[session.session_id] = session
        return session

    async def listen(self):

        async def receive_user_audio():
            async for chunk in self.stream.read():
                self.buffer += chunk

        async def detect_speech():
            while True:
                if len(self.buffer) == 0:
                    await asyncio.sleep(0)
                    continue
                buffer, self.buffer = self.buffer, b""
                await self.vad(buffer)

        async def response_if_speech():
            prev_response_task = None
            async for user_is_speaking, user_speech in self.vad.results():
                self.user_is_speaking = user_is_speaking
                if user_speech:
                    if prev_response_task and not prev_response_task.done():
                        prev_response_task.cancel()
                    prev_response_task = safe_create_task(self.response(user_speech))

        await asyncio.gather(receive_user_audio(), detect_speech(), response_if_speech())
    
    def mute_user(self):
        self.buffer += b"0x00" * self.sample_rate

    async def response(self, user_speech: bytes):
        response_id = uuid4().hex
        asr_task = safe_create_task(self.asr(user_speech))
        slm_task = safe_create_task(self.slm(history=self.history, audio=user_speech))
        user_transcript = await asr_task
        add_user_message(self.history, audio=user_speech, transcript=user_transcript)

        tts_control_task = safe_create_task(
            self.tts_control(user_transcript) if self.tts_control else asyncio.sleep(0, result={})
        )
        diar_control_task = safe_create_task(
            self.diar_control(user_transcript) if self.diar_control else asyncio.sleep(0, result={})
        )
        tts_control, diar_control = await asyncio.gather(tts_control_task, diar_control_task)
        tts_control["speech"] = user_speech
        tts_control["transcript"] = user_transcript

        if self.user_is_speaking or not diar_control.get("response", True):
            return

        agent_text_generator = await slm_task
        agent_text_generator1, agent_text_generator2 = tee(agent_text_generator, 2)
        tts_task = safe_create_task(self.tts(text_generateor=agent_text_generator1, control=tts_control))
        await self.event.set_avatar(tts_control["timbre"])

        agent_speech_generator = await tts_task
        try:
            async for agent_speech in agent_speech_generator:
                if self.user_is_speaking:
                    break
                await self.stream.write(agent_speech, response_id)
        except asyncio.CancelledError:
            logger.info(f"response {response_id} cancelled")
        finally:
            await agent_text_generator.aclose()
            await agent_speech_generator.aclose()
            agent_text = "".join([chunk async for chunk in agent_text_generator2])
            add_agent_message(history=self.history, message=agent_text)

    @property
    def user_is_speaking(self):
        return self._user_is_speaking

    @user_is_speaking.setter
    def user_is_speaking(self, user_is_speaking: bool):
        if self._user_is_speaking != user_is_speaking:
            self.event.set_agent_can_speak(agent_can_speak=not user_is_speaking)
        self._user_is_speaking = user_is_speaking
