import requests
import json
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, api_key, base_url, model):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def chat_completion(self, messages, temperature=0.7, json_mode=False, **kwargs):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }
        
        # Merge kwargs into payload, avoiding duplicates
        for k, v in kwargs.items():
            if k not in payload:
                payload[k] = v

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        timeout = kwargs.get("timeout", settings.TIMEOUT_SECONDS)

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions", 
                headers=headers, 
                json=payload, 
                timeout=timeout
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            logger.error(f"API Request failed: {e}")
            if response is not None:
                logger.error(f"Response content: {response.text}")
            raise

def get_doctor_client():
    return LLMClient(
        api_key=settings.YUNWU_API_KEY,
        base_url=settings.YUNWU_BASE_URL,
        model=settings.DOCTOR_AGENT_MODEL
    )

def get_judge_client():
    return LLMClient(
        api_key=settings.YUNWU_API_KEY,
        base_url=settings.YUNWU_BASE_URL,
        model=settings.JUDGE_AGENT_MODEL
    )
