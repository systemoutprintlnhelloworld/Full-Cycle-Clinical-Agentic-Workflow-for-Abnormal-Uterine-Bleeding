
import yaml
import os
import time
import logging
from typing import Dict, List, Optional
from openai import OpenAI
from dotenv import load_dotenv

# 加载 .env 环境变量
load_dotenv()

logger = logging.getLogger(__name__)

class Channel:
    """单个API渠道"""
    def __init__(self, name: str, base_url: str, api_key: str, timeout: int, max_retries: int):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = None
    
    def get_client(self) -> OpenAI:
        """获取OpenAI客户端（懒加载）"""
        if self.client is None:
            if not self.api_key:
                logger.warning(f"渠道 {self.name} 的 API Key 为空，可能导致调用失败。")
            
            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
        return self.client

class ChannelManager:
    """渠道管理器：支持多模型路由和自动Fallback"""
    
    def __init__(self, config_path: str = "auto_eval_system/config/channels.yaml"):
        # 获取绝对路径，容错
        if not os.path.exists(config_path):
            # 尝试相对于脚本运行目录的路径
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config", "channels.yaml")
            
        self.config = self._load_config(config_path)
        self.channels = self._init_channels()
        self.model_channels_map = self.config["model_channels"]
        self.global_fallback = self.config.get("global_fallback", {})
        
        # 统计数据
        self.stats = {
            "total_calls": 0,
            "channel_usage": {},
            "fallback_usage": 0,
            "failures": {}
        }
        
        # Circuit Breaker: Channel Name -> Unblock Timestamp
        self.blocked_channels = {}
        
        # Swap State: Model Name -> Boolean (False=Primary First, True=Fallback First)
        self.swap_state = {}

    def _is_channel_blocked(self, channel_name: str) -> bool:
        """Check if channel is currently blocked"""
        if channel_name in self.blocked_channels:
            if time.time() < self.blocked_channels[channel_name]:
                return True
            else:
                del self.blocked_channels[channel_name] # Expired
        return False

    def _block_channel(self, channel_name: str, duration: int = 60):
        """Block a channel for a duration (seconds)"""
        self.blocked_channels[channel_name] = time.time() + duration
        logger.warning(f"CIRCUIT BREAKER: Channel {channel_name} blocked for {duration}s due to Saturation/429.")

    
    def _load_config(self, config_path: str) -> dict:
        """加载配置文件并替换环境变量"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"渠道配置文件未找到: {config_path}")
            
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 替换环境变量: ${ENV_VAR} -> 实际值
        for channel_name, channel_info in config["channels"].items():
            api_key_tmpl = channel_info["api_key"]
            if isinstance(api_key_tmpl, str) and api_key_tmpl.startswith("${") and api_key_tmpl.endswith("}"):
                env_var = api_key_tmpl[2:-1]
                env_val = os.getenv(env_var)
                if not env_val:
                    logger.warning(f"环境变量 {env_var} 未设置，渠道 {channel_name} 可能不可用")
                config["channels"][channel_name]["api_key"] = env_val if env_val else ""
        
        return config
    
    def _init_channels(self) -> Dict[str, Channel]:
        """初始化所有渠道"""
        channels = {}
        for name, info in self.config["channels"].items():
            channels[name] = Channel(
                name=name,
                base_url=info["base_url"],
                api_key=info["api_key"],
                timeout=info.get("timeout", 120),
                max_retries=info.get("max_retries", 2)
            )
        return channels
    
    def get_client_for_model(self, model_name: str, attempt: int = 0) -> tuple[Optional[OpenAI], str]:
        """
        获取指定模型的客户端和渠道名称
        
        Args:
            model_name: 模型名称
            attempt: 当前尝试次数（0=主渠道，1+=fallback）
            
        Returns:
            (OpenAI客户端, 渠道名称)
        """
        if model_name not in self.model_channels_map:
            logger.error(f"模型 {model_name} 未在配置中定义，请检查 channels.yaml")
            return None, ""
        
        channel_config = self.model_channels_map[model_name]
        
        # 第0次尝试：主渠道
        if attempt == 0:
            channel_name = channel_config["primary"]
            return self.channels[channel_name].get_client(), channel_name
        
        # Fallback尝试
        fallback_list = channel_config.get("fallback", [])
        fallback_index = attempt - 1
        
        if fallback_index < len(fallback_list):
            channel_name = fallback_list[fallback_index]
            return self.channels[channel_name].get_client(), channel_name
        
        return None, ""
    
    def _toggle_swap_state(self, model_name: str):
        """Toggle the primary/fallback priority for a model"""
        current_state = self.swap_state.get(model_name, False)
        self.swap_state[model_name] = not current_state
        new_primary = "Fallback" if self.swap_state[model_name] else "Primary"
        logger.warning(f"SWAP TRIGGERED: Model {model_name} priority swapped. New Leader: {new_primary}")

    def call_with_fallback(self, model_name: str, messages: list, **kwargs) -> dict:
        """
        带fallback的LLM调用, 支持 Saturation Swap 机制
        """
        self.stats["total_calls"] += 1
        max_attempts = self.global_fallback.get("max_attempts", 3)
        retry_delay = self.global_fallback.get("retry_delay", 2)
        
        channel_config = self.model_channels_map.get(model_name, {})
        primary_channel = channel_config.get("primary")
        fallback_channels = channel_config.get("fallback", [])
        
        # Build Priority List based on Swap State
        is_swapped = self.swap_state.get(model_name, False)
        
        if is_swapped and fallback_channels:
            # Fallback First: [Fallback 0, Primary, Rest of Fallbacks...]
            candidate_channels = [fallback_channels[0], primary_channel] + fallback_channels[1:]
        else:
            # Primary First: [Primary, All Fallbacks...]
            candidate_channels = [primary_channel] + fallback_channels
            
        # Filter Nones and Duplicates (preserving order)
        priority_list = []
        seen = set()
        for c in candidate_channels:
            if c and c not in seen:
                priority_list.append(c)
                seen.add(c)

        last_error = None
        attempted_channels = []
        
        # Iterate through priority list
        for attempt, channel_name in enumerate(priority_list):
            if attempt >= max_attempts:
                break
                
            if channel_name not in self.channels:
                logger.error(f"Channel {channel_name} not configured.")
                continue

            client = self.channels[channel_name].get_client()
            
            # Circuit Breaker Check
            if self._is_channel_blocked(channel_name):
                logger.info(f"Skipping blocked channel: {channel_name}")
                continue

            attempted_channels.append(channel_name)
            
            # 记录使用统计
            self.stats["channel_usage"][channel_name] = self.stats["channel_usage"].get(channel_name, 0) + 1
            if attempt > 0:
                self.stats["fallback_usage"] += 1
                logger.info(f"Model {model_name} trying: {channel_name} (Priority {attempt+1})")
            
            # Determine effective model name
            effective_model_name = channel_config.get("channel_map", {}).get(channel_name, model_name)

            try:
                # 显式请求 logprobs，如果用户需要
                # 注意：不是所有模型/渠道都支持logprobs，如果不支持可能会报错
                # 这里我们假设如果kwargs里有logprobs=True，则传递
                
                response = client.chat.completions.create(
                    model=effective_model_name,
                    messages=messages,
                    **kwargs
                )
                
                return response
            
            except Exception as e:
                last_error = e
                error_msg = str(e)
                
                # EXTRACT DETAILED ERROR INFO
                status_code = getattr(e, "status_code", "N/A")
                response_body = "N/A"
                if hasattr(e, "response") and e.response:
                    try:
                        # Try to parse JSON body
                        response_json = e.response.json()
                        response_body = str(response_json)
                        
                        # --- SATURATION SWAP LOGIC ---
                        # Check for specific Chinese error message in body
                        if isinstance(response_json, dict):
                            err_obj = response_json.get("error", {})
                            if isinstance(err_obj, dict):
                                msg = err_obj.get("message", "")
                                code = err_obj.get("code", "")
                                type_err = err_obj.get("type", "")
                                
                                # Saturation / Load Check
                                if "负载已饱和" in msg or "saturation" in msg.lower():
                                    logger.warning(f"Saturation detected on {channel_name}. Triggering Priority Swap.")
                                    self._toggle_swap_state(model_name)
                                    self._block_channel(channel_name, duration=60)
                                
                                # Quota / Credit Check (Claude/OpenAI)
                                if "quota" in msg.lower() or "credit" in msg.lower() or "balance" in msg.lower() or \
                                   "insufficient_quota" in str(code) or "billing" in str(type_err):
                                    logger.critical(f"QUOTA EXCEEDED on {channel_name}. Blocking and Swapping.")
                                    self._toggle_swap_state(model_name)
                                    self._block_channel(channel_name, duration=300) # Block longer for quota
                            
                    except:
                        response_body = getattr(e.response, "text", str(e.response))
                
                # Check 429 in status code as well
                if "429" in str(status_code) or "429" in error_msg:
                     self._block_channel(channel_name, duration=60)
                     logger.warning(f"429 Rate Limit detected on {channel_name}. Triggering Priority Swap.")
                     self._toggle_swap_state(model_name)
                
                # Check Quota in generic error message if JSON parse failed
                if "quota" in error_msg.lower() or "insufficient" in error_msg.lower():
                     self._block_channel(channel_name, duration=300)
                     logger.warning(f"Quota error expected from msg on {channel_name}. Swapping.")
                     self._toggle_swap_state(model_name)

                error_detail = f"Status: {status_code} | Body: {response_body[:500]}..." # Truncate body
                
                self.stats["failures"][channel_name] = self.stats["failures"].get(channel_name, 0) + 1
                
                logger.error(f"渠道 {channel_name} 调用失败: {error_msg}")
                logger.error(f"  -> {error_detail}")
                
                # 特定错误判断：如果是不支持logprobs导致的错误，可能需要移除参数重试？
                # 但根据需求，我们希望获取logprobs，如果拿不到，可能宁愿失败或者在fallback中尝试。
                # 暂时保持简单逻辑：失败就换下一个渠道。
                
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)
        
        # 所有尝试均失败
        error_summary = f"模型 {model_name} 调用失败，已尝试渠道: {attempted_channels}。最后错误: {last_error}"
        logger.critical(error_summary)
        raise Exception(error_summary)

# 全局单例
_channel_manager = None

def get_channel_manager() -> ChannelManager:
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
    return _channel_manager
