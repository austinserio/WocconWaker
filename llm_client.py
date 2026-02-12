"""
Single LLM abstraction: local Ollama (LOCAL_LLM=true) or Microsoft Foundry (LOCAL_LLM=false).
Returns Ollama-compatible shape so callers can use ["message"]["content"].
"""
import os
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("llm_client")


def _is_local_llm() -> bool:
    v = os.getenv("LOCAL_LLM", "").strip().lower()
    return v in ("true", "1", "yes")


def llm_chat(
    model: str,
    messages: List[Dict[str, str]],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send chat completion request. Backend is chosen by LOCAL_LLM env var.
    Returns dict with "message" -> "content" for compatibility with ollama.chat() callers.
    """
    options = options or {}
    if _is_local_llm():
        return _local_ollama_chat(model, messages, options)
    return _foundry_chat(model, messages, options)


def _local_ollama_chat(
    model: str,
    messages: List[Dict[str, str]],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """Use local Ollama API (OLLAMA_URL)."""
    import requests
    base = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    if "/v1/chat" in base:
        base = base.replace("/v1/chat", "").rstrip("/")
    if "/api/chat" in base:
        base = base.replace("/api/chat", "").rstrip("/")
    url = f"{base}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "options": {
            "temperature": options.get("temperature", 0.3),
            "top_p": options.get("top_p", 0.9),
            "repeat_penalty": options.get("repeat_penalty", 1.1),
            "num_predict": options.get("num_predict", 1000),
            "stop": options.get("stop"),
            "seed": options.get("seed"),
        },
    }
    # Drop None values
    payload["options"] = {k: v for k, v in payload["options"].items() if v is not None}
    try:
        r = requests.post(url, json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()
        # Ollama returns {"message": {"role": "assistant", "content": "..."}}
        return data
    except Exception as e:
        log.error(f"Local Ollama request failed: {e}")
        return {"message": {"content": f"Error: Unable to connect to Ollama. {e}"}}


def _foundry_chat(
    model: str,
    messages: List[Dict[str, str]],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """Use Microsoft Foundry: Azure AI inference (.services.ai.azure.com) or Azure OpenAI (.openai.azure.com)."""
    import requests
    endpoint = (os.getenv("FOUNDRY_ENDPOINT") or os.getenv("AZURE_AI_ENDPOINT") or "").rstrip("/")
    api_key = os.getenv("FOUNDRY_API_KEY") or os.getenv("AZURE_INFERENCE_CREDENTIAL")
    deployment = (os.getenv("FOUNDRY_DEPLOYMENT") or "Meta-Llama-3.1-8B-Instruct").strip() or "Meta-Llama-3.1-8B-Instruct"
    model_for_api = (os.getenv("FOUNDRY_MODEL_ID") or "").strip() or deployment
    if not endpoint or not api_key:
        log.error("FOUNDRY_ENDPOINT and FOUNDRY_API_KEY (or AZURE_AI_ENDPOINT / AZURE_INFERENCE_CREDENTIAL) required")
        return {"message": {"content": "Error: Foundry endpoint and API key not configured."}}

    # Azure AI Model Inference endpoint: POST .../models/chat/completions?api-version=...
    if "services.ai.azure.com" in endpoint:
        api_version = os.getenv("FOUNDRY_API_VERSION", "2024-05-01-preview")
        url = f"{endpoint}/models/chat/completions?api-version={api_version}"
        headers = {"Content-Type": "application/json", "api-key": api_key}
        payload = {
            "model": model_for_api,
            "messages": messages,
            "max_tokens": options.get("num_predict", 1000),
            "temperature": options.get("temperature", 0.3),
        }
        if options.get("stop"):
            payload["stop"] = options["stop"]
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            r.raise_for_status()
            data = r.json()
            content = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
            return {"message": {"role": "assistant", "content": content}}
        except Exception as e:
            log.error(f"Foundry inference request failed: {e}")
            return {"message": {"content": f"Error: Foundry request failed. {e}"}}

    # Azure OpenAI endpoint (.openai.azure.com): use SDK
    try:
        from openai import AzureOpenAI
    except ImportError:
        log.error("openai package required for Foundry. pip install openai")
        return {"message": {"content": "Error: openai package not installed for Foundry mode."}}
    api_version = os.getenv("FOUNDRY_API_VERSION", "2024-10-21")
    try:
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        max_tokens = options.get("num_predict", 1000)
        resp = client.chat.completions.create(
            model=model_for_api,
            messages=messages,
            temperature=options.get("temperature", 0.3),
            max_tokens=max_tokens,
            stop=options.get("stop"),
        )
        content = (resp.choices[0].message.content or "").strip()
        return {"message": {"role": "assistant", "content": content}}
    except Exception as e:
        log.error(f"Foundry request failed: {e}")
        return {"message": {"content": f"Error: Foundry request failed. {e}"}}
