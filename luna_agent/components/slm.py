import logging
import hashlib
from typing import List, Dict, Optional
from openai import AsyncOpenAI
from luna_agent.utils import pcm2base64, format_msg
from luna_agent.components.diar import Diar

logger = logging.getLogger("luna_agent")

DEFAULT_PROMPTS = [
    {
        "role": "system",
        "content": """你是宇生月伴开发的语音助手\"Luna\"""",
    }
]


def add_user_message(
    history,
    audio: Optional[bytes] = None,
    text: Optional[str] = None,
    transcript: Optional[str] = "",
):
    content = []
    assert audio or text, "audio or text must be provided"
    if audio:
        content.append(
            {
                "type": "input_audio",
                "input_audio": {
                    "data": pcm2base64(audio, sample_rate=16000),
                    "format": "wav",
                },
                "id": hashlib.md5(audio).hexdigest(),
                "transcript": transcript,
            }
        )
    if text:
        content.append({"type": "text", "text": text})

    history.append({"role": "user", "content": content})
    return history


def add_agent_message(history, message):
    history.append({"role": "assistant", "content": message})
    return history


class SLM:
    def __init__(
        self,
        base_url: str,
        api_key: str = "token",
        model: str = "Qwen/Qwen2.5-7B-Instruct",
        prompts: List[Dict] = DEFAULT_PROMPTS,
        use_text_history: bool = False,
        completion_params: dict = {},
        diar: Optional[Diar] = None,
        max_messages: int = -1,
    ):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.sample_rate = 16000
        self.prompts = prompts
        self.use_text_history = use_text_history
        self.completion_params = completion_params
        self.diar = diar
        self.max_messages = max_messages
    
    async def setup(self, session_id: str):
        if self.diar:
            await self.diar.setup(session_id=session_id)

    async def __call__(self, history: List[Dict], audio: bytes):
        diar: Dict = await self.diar(audio) if self.diar else {}

        messages = []
        for message in history:
            if message["role"] == "user" and "content" in message:
                contents_new = []
                for content in message["content"]:
                    if content["id"] in diar:
                        contents_new.append(
                            {
                                "type": "text",
                                "text": f"[说话人 {diar[content['id']]}] ",
                            }
                        )
                    if self.use_text_history:
                        content = {"type": "text", "text": content["transcript"]}
                    else:
                        content = message["content"]
                    contents_new.append(content)
            contents_new.append(content)
            logger.info(f">>> {format_msg(message['content']).strip()}")
            messages.append({"role": message["role"], "content": content})

        add_user_message(messages, audio=audio)
        completion = await self.client.chat.completions.create(
            model=self.model, messages=self.prompts + messages, stream=True, **self.completion_params
        )

        async def generator():
            async for chunk in completion:
                yield chunk.choices[0].delta.content

        return generator()
