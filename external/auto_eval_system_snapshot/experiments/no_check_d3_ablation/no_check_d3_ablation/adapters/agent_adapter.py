from __future__ import annotations

import logging
import os
import threading
import time
from typing import Iterable

from auto_eval_system.modules.doctor_agent import DoctorAgent
from auto_eval_system.modules.judge_agent import JudgeAgent
from auto_eval_system.utils.channel_manager import Channel, get_channel_manager

logger = logging.getLogger(__name__)

DOCTOR_CALL_SEMAPHORE = threading.Semaphore(6)
JUDGE_CALL_SEMAPHORE = threading.Semaphore(2)

YUNWU_ROUTE_PREFERENCES = {
    "gemini-2.5-pro": ["yunwu_api"],
    "gpt-5-2025-08-07": ["yunwu_api", "vveai_api"],
    "claude-opus-4-1-20250805-thinking": ["yunwu_api", "cld_api"],
    "deepseek-v3-1-think-250821": ["yunwu_deepseek_special", "yunwu_api"],
    "grok-4": ["yunwu_grok_special", "yunwu_api"],
    "gpt-4o": ["yunwu_api"],
}


def normalize_openai_base_url(base_url: str, default_base_url: str) -> str:
    """统一 OpenAI 兼容渠道的 base_url，兼容未显式带 /v1 的输入。"""
    resolved = (base_url or "").strip() or default_base_url
    resolved = resolved.rstrip("/")
    if not resolved:
        return default_base_url
    if resolved.endswith("/v1"):
        return resolved
    return f"{resolved}/v1"


def ensure_runtime_channel(
    channel_name: str,
    base_url: str,
    api_key: str,
    timeout: int = 120,
    max_retries: int = 3,
) -> bool:
    """运行时注册/覆盖渠道，不写入任何配置文件。"""
    if not channel_name or not base_url or not api_key:
        logger.warning("渠道 %s 注册失败：缺少必要参数。", channel_name)
        return False

    channel_manager = get_channel_manager()
    channel_manager.channels[channel_name] = Channel(
        name=channel_name,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
    )
    logger.info("运行时渠道 %s 已注册，base_url=%s", channel_name, base_url)
    return True


def enable_xingchen_for_gemini() -> bool:
    """若提供了星辰密钥，则注册星辰渠道。"""
    api_key = os.getenv("XINGCHEN_API_KEY", "").strip()
    base_url = normalize_openai_base_url(
        os.getenv("XINGCHEN_BASE_URL", "").strip(),
        "https://ai.centos.hk/v1",
    )
    if not api_key:
        logger.info("未检测到 XINGCHEN_API_KEY，跳过星辰路由。")
        return False

    if not ensure_runtime_channel(
        channel_name="xingchen_api",
        base_url=base_url,
        api_key=api_key,
        timeout=120,
        max_retries=3,
    ):
        return False

    return True


def enable_duckcoding_for_gemini() -> bool:
    """若提供了 duckcoding 密钥，则注册 duckcoding 渠道。"""
    api_key = os.getenv("DUCKCODING_API_KEY", "").strip()
    base_url = normalize_openai_base_url(
        os.getenv("DUCKCODING_BASE_URL", "").strip(),
        "https://api.duckcoding.ai/v1",
    )
    if not api_key:
        logger.info("未检测到 DUCKCODING_API_KEY，跳过 duckcoding 路由。")
        return False

    if not ensure_runtime_channel(
        channel_name="duckcoding_api",
        base_url=base_url,
        api_key=api_key,
        timeout=120,
        max_retries=3,
    ):
        return False

    return True


def set_model_routing(model_name: str, preferred_channels: Iterable[str]) -> None:
    channel_manager = get_channel_manager()
    if not model_name:
        return
    if model_name not in channel_manager.model_channels_map:
        logger.warning("模型 %s 未在 channels.yaml 中定义，跳过路由覆盖。", model_name)
        return

    available = channel_manager.model_channels_map[model_name]
    preferred = [name for name in preferred_channels if name in channel_manager.channels]
    if not preferred:
        logger.warning("模型 %s 没有命中的候选渠道，保留原路由。", model_name)
        return

    available["primary"] = preferred[0]
    available["fallback"] = preferred[1:]
    logger.info("模型 %s 已切换路由，primary=%s fallback=%s", model_name, preferred[0], preferred[1:])


def force_yunwu_routing(model_names: Iterable[str]) -> None:
    """仅修改运行时路由，不修改任何原配置文件。"""
    for model_name in set(model_names):
        preferred = YUNWU_ROUTE_PREFERENCES.get(model_name, ["yunwu_api"])
        set_model_routing(model_name, preferred)


def wait_for_available_channel(model_name: str, max_wait_seconds: int = 75) -> None:
    channel_manager = get_channel_manager()
    channel_config = channel_manager.model_channels_map.get(model_name, {})
    candidate_channels = [channel_config.get("primary")] + channel_config.get("fallback", [])
    candidate_channels = [name for index, name in enumerate(candidate_channels) if name and name not in candidate_channels[:index]]
    if not candidate_channels:
        return

    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        available = [name for name in candidate_channels if not channel_manager._is_channel_blocked(name)]
        if available:
            return
        unblock_times = [channel_manager.blocked_channels.get(name) for name in candidate_channels if name in channel_manager.blocked_channels]
        if not unblock_times:
            return
        sleep_seconds = max(1, min(int(min(unblock_times) - time.time()) + 1, 5))
        logger.info(
            "模型 %s 的候选渠道均 blocked（%s），等待 %s 秒后重试。",
            model_name,
            ",".join(candidate_channels),
            sleep_seconds,
        )
        time.sleep(sleep_seconds)


class DoctorClient:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.agent = DoctorAgent(model_name=model_name)

    def decide(self, stage_name: str, system_prompt: str, user_prompt: str) -> dict:
        with DOCTOR_CALL_SEMAPHORE:
            wait_for_available_channel(self.model_name)
            return self.agent.make_decision_with_context(stage_name, system_prompt, user_prompt)


class JudgeClient:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.agent = JudgeAgent(model_name=model_name)

    def evaluate_with_d3_scoring(self, system_prompt: str) -> dict:
        with JUDGE_CALL_SEMAPHORE:
            wait_for_available_channel(self.model_name)
            return self.agent._call_judge(system_prompt=system_prompt, stage_name="judge_decision3_gate")
