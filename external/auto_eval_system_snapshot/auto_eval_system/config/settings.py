import os

# API Configuration
# Using "yunwu" for GPT-4o as primary
YUNWU_API_KEY = "sk-VhkXAjouzkRQJXrUpYyuV7Gb9uhMiADv8uGsiyF1BNQLdxdf"
YUNWU_BASE_URL = "https://yunwu.ai/v1"

# Using "gala" for Gemini as secondary (if needed, e.g. for patient voice generation)
GALA_API_KEY = "sk-Tf8DOPvvHy34h3owxFZdSlZAj068a7IJWOOmUhTd3nbp75ZB"
GALA_BASE_URL = "https://www.galaapi.com/v1"

# Model Selection
PRIMARY_MODEL = "gpt-4o"
SECONDARY_MODEL = "gemini-2.5-pro"

# Agent Configurations
DOCTOR_AGENT_MODEL = PRIMARY_MODEL
JUDGE_AGENT_MODEL = PRIMARY_MODEL  # Using GPT-4o for judging as well for better reasoning
PATIENT_VOICE_MODEL = SECONDARY_MODEL

# Retry Settings
MAX_RETRIES = 3
TIMEOUT_SECONDS = 60
