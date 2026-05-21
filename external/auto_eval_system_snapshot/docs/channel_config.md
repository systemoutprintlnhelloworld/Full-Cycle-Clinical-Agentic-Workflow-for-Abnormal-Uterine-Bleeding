# 渠道配置方案 v2.0

> 支持每个模型使用不同API渠道，并提供fallback机制。

---

## 设计目标

1. **每模型独立渠道**: 不同模型可使用不同API endpoint和key
2. **Fallback机制**: 主渠道失败自动切换到备用渠道
3. **灵活配置**: YAML格式，易于维护
4. **渠道管理器**: 统一的渠道管理和故障转移逻辑

---

## 配置文件格式

### `config/channels.yaml`

```yaml
# 渠道定义
channels:
  yunwu_api:  # 综合节点
    base_url: "https://yunwu.ai/v1"
    api_key: "${YUNWU_API_KEY}"
    timeout: 300
    max_retries: 3
    
  gala_api:  # gemini节点
    base_url: "https://www.galaapi.com/v1"
    api_key: "${GALA_API_KEY}"
    timeout: 60
    max_retries: 3
    
  cld_api:  # cld节点
    base_url: "https://api.oaipro.com/"
    api_key: "${CLD_API_KEY}"
    timeout: 300
    max_retries: 2
    
  ds_api:  # ds节点
    base_url: "https://api.ephone.chat/v1"
    api_key: "${DS_API_KEY}"
    timeout: 300
    max_retries: 3
    
  vveai_api:  # 稳定gpt节点
    base_url: "https://api.vveai.com/v1"
    api_key: "${VVEAI_API_KEY}"
    timeout: 120
    max_retries: 2

# 模型与渠道映射
model_channels:
  gemini-2.5-pro:
    primary: gala_api
    fallback: [yunwu_api]
    
  gpt-5-2025-08-07:
    primary: vveai_api  # 302主要
    fallback: [yunwu_api]
    
  claude-opus-4-1-20250805:
    primary: cld_api
    fallback: [yunwu_api]
    
  deepseek-v3-1-think-250821:
    primary: ds_api
    fallback: [yunwu_api]
    
  grok-4:
    primary: yunwu_api
    fallback: []

# 全局fallback策略
global_fallback:
  enabled: true
  max_attempts: 3  # 包括主渠道在内，最多尝试3次（主+2个备用）
  retry_delay: 2  # 失败后等待2秒再尝试下一个渠道
```

---

## 渠道管理器实现

### `auto_eval_system/utils/channel_manager.py`

```python
import yaml
import os
import time
import logging
from typing import Dict, List, Optional
from openai import OpenAI

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
            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
        return self.client

class ChannelManager:
    """渠道管理器"""
    def __init__(self, config_path: str = "config/channels.yaml"):
        self.config = self._load_config(config_path)
        self.channels = self._init_channels()
        self.model_channels_map = self.config["model_channels"]
        self.global_fallback = self.config.get("global_fallback", {})
    
    def _load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 替换环境变量
        for channel_name, channel_info in config["channels"].items():
            api_key = channel_info["api_key"]
            if api_key.startswith("${") and api_key.endswith("}"):
                env_var = api_key[2:-1]
                config["channels"][channel_name]["api_key"] = os.getenv(env_var)
        
        return config
    
    def _init_channels(self) -> Dict[str, Channel]:
        """初始化所有渠道"""
        channels = {}
        for name, info in self.config["channels"].items():
            channels[name] = Channel(
                name=name,
                base_url=info["base_url"],
                api_key=info["api_key"],
                timeout=info["timeout"],
                max_retries=info["max_retries"]
            )
        return channels
    
    def get_client_for_model(self, model_name: str, attempt: int = 0) -> Optional[OpenAI]:
        """
        获取指定模型的客户端
        
        Args:
            model_name: 模型名称
            attempt: 当前尝试次数（0=主渠道，1+=fallback）
        
        Returns:
            OpenAI客户端，如果所有渠道都失败则返回None
        """
        if model_name not in self.model_channels_map:
            logger.error(f"模型 {model_name} 未在配置中定义")
            return None
        
        channel_config = self.model_channels_map[model_name]
        
        # 第0次尝试：使用主渠道
        if attempt == 0:
            channel_name = channel_config["primary"]
            logger.info(f"模型 {model_name} 使用主渠道: {channel_name}")
            return self.channels[channel_name].get_client()
        
        # 第1+次尝试：使用fallback渠道
        fallback_list = channel_config.get("fallback", [])
        fallback_index = attempt - 1
        
        if fallback_index < len(fallback_list):
            channel_name = fallback_list[fallback_index]
            logger.warning(f"模型 {model_name} 使用fallback渠道({attempt}): {channel_name}")
            return self.channels[channel_name].get_client()
        
        # 所有渠道都失败
        logger.error(f"模型 {model_name} 所有渠道均失败")
        return None
    
    def call_with_fallback(self, model_name: str, messages: list, **kwargs) -> dict:
        """
        带fallback的LLM调用
        
        Args:
            model_name: 模型名称
            messages: 消息列表
            **kwargs: 其他参数（temperature, max_tokens等）
        
        Returns:
            LLM响应
        
        Raises:
            Exception: 所有渠道都失败后抛出
        """
        max_attempts = self.global_fallback.get("max_attempts", 3)
        retry_delay = self.global_fallback.get("retry_delay", 2)
        
        last_error = None
        
        for attempt in range(max_attempts):
            client = self.get_client_for_model(model_name, attempt)
            
            if client is None:
                break
            
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    **kwargs
                )
                logger.info(f"模型 {model_name} 调用成功（尝试次数: {attempt + 1}）")
                return response
            
            except Exception as e:
                last_error = e
                logger.error(f"模型 {model_name} 调用失败（尝试次数: {attempt + 1}）: {e}")
                
                # 如果不是最后一次尝试，等待后重试
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)
        
        # 所有尝试都失败
        raise Exception(f"模型 {model_name} 所有渠道调用均失败。最后错误: {last_error}")

# 全局单例
_channel_manager = None

def get_channel_manager() -> ChannelManager:
    """获取全局渠道管理器单例"""
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
    return _channel_manager
```

---

## 使用示例

### 在DoctorAgent中使用

```python
from auto_eval_system.utils.channel_manager import get_channel_manager

class DoctorAgent:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.channel_manager = get_channel_manager()
    
    def make_outpatient_decision(self, patient_data: dict) -> dict:
        messages = [
            {"role": "system", "content": OUTPATIENT_SYSTEM_PROMPT},
            {"role": "user", "content": self._format_user_prompt(patient_data)}
        ]
        
        # 使用渠道管理器调用（自动fallback）
        response = self.channel_manager.call_with_fallback(
            model_name=self.model_name,
            messages=messages,
            temperature=0.5,
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)
```

---

## 环境变量配置

### `.env` 文件

```bash
# Yunwu API
YUNWU_API_KEY=<redacted_api_key>

# Gala API (Gemini)
GALA_API_KEY=<redacted_api_key>

# Claude API
CLD_API_KEY=<redacted_api_key>

# DeepSeek API
DS_API_KEY=<redacted_api_key>

# 综合API
COMP_API_KEY=<redacted_api_key>
```

---

## 监控和日志

### 渠道使用统计

```python
class ChannelManager:
    def __init__(self, ...):
        ...
        self.stats = {
            "total_calls": 0,
            "channel_usage": {},  # {channel_name: count}
            "fallback_usage": 0,
            "failures": {}  # {channel_name: count}
        }
    
    def call_with_fallback(self, ...):
        self.stats["total_calls"] += 1
        
        for attempt in range(max_attempts):
            channel_name = self._get_channel_name(model_name, attempt)
            self.stats["channel_usage"][channel_name] = self.stats["channel_usage"].get(channel_name, 0) + 1
            
            try:
                ...
            except Exception as e:
                self.stats["failures"][channel_name] = self.stats["failures"].get(channel_name, 0) + 1
                if attempt > 0:
                    self.stats["fallback_usage"] += 1
                ...
    
    def get_stats(self) -> dict:
        """获取渠道使用统计"""
        return self.stats
```

---

## 配置验证

### 启动时验证

```python
def validate_config():
    """验证配置文件"""
    manager = get_channel_manager()
    
    # 检查所有模型都有配置
    for model in ["gemini-2.5-pro", "gpt-5-2025-08-07", ...]:
        if model not in manager.model_channels_map:
            raise ValueError(f"模型 {model} 未在配置中定义")
    
    # 检查所有引用的渠道都存在
    for model, config in manager.model_channels_map.items():
        if config["primary"] not in manager.channels:
            raise ValueError(f"渠道 {config['primary']} 不存在")
        for fb in config.get("fallback", []):
            if fb not in manager.channels:
                raise ValueError(f"Fallback渠道 {fb} 不存在")
    
    logger.info("渠道配置验证通过")
```

---

**实现位置**: `auto_eval_system/utils/channel_manager.py` + `config/channels.yaml`
