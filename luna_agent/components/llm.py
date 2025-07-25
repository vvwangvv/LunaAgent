import json_repair
import logging
from typing import Dict, List

from openai import AsyncOpenAI

logger = logging.getLogger("luna_agent")


def add_user_message(history, message):
    history.append({"role": "user", "content": message})
    return history


def add_agent_message(history, message):
    history.append({"role": "assistant", "content": message})
    return history


DEFAULT_PROMPTS = [
    {
        "role": "system",
        "content": """你是宇生月伴开发的语音助手\"Luna\"""",
    }
]


class LLM:
    def __init__(
        self,
        base_url,
        prompts: List[Dict] = DEFAULT_PROMPTS,
        api_key="token",
        model="Qwen2.5-7B-Instruct",
        is_control: bool = False,
    ):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.prompts = prompts
        if is_control:
            self.__call__ = self.__call_control__

    async def __call__(self, messages):
        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=self.prompts + messages,
            stream=True,
        )
        async for chunk in completion:
            yield chunk.choices[0].delta.content

    async def __call_control__(self, text):
        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=self.prompts + [{"role": "user", "content": text}],
            stream=False,
        )
        control_params: dict = json_repair.loads(completion.choices[0].message.content)
        control_params = self.fix_control(**control_params)
        return control_params

    def fix_control(self, **control_params):
        controls = {
            "diarization": False,
            "response": None,
            "emotion": "default",
            "speed": "default",
            "timbre": "default",
        }
        for k, v in control_params.items():
            if k in controls:
                controls[k] = v
        return controls
