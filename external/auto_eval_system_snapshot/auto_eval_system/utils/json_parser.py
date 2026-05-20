import json
import re
import logging

logger = logging.getLogger(__name__)

def extract_json(text):
    """
    Extracts JSON from a string, handling markdown code blocks and potential noise.
    """
    try:
        # First try direct parsing
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code blocks
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding the first { and last }
    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
            
    logger.error(f"Failed to extract JSON from text: {text[:200]}...")
    return None
