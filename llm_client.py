"""
Single LLM abstraction: local Ollama (LOCAL_LLM=true), Microsoft Foundry, or Anthropic
(only when ALLOW_ANTHROPIC_FALLBACK=true). Returns Ollama-compatible shape so callers
can use ["message"]["content"].
"""
import base64
import os
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("llm_client")

_ollama_session: Optional[Any] = None


def _ollama_http_session():
    """Reuse TCP connections to Ollama (helps when parallel workers hit the same host)."""
    global _ollama_session
    if _ollama_session is None:
        import requests

        _ollama_session = requests.Session()
    return _ollama_session


def _ollama_keep_alive() -> str:
    # Default 0 = unload after each request. Batch ingest alternates text/vision models on
    # one GPU; keeping a 32B model warm blocks the other. Set OLLAMA_KEEP_ALIVE=30m only
    # for interactive chat where cold-start latency matters.
    v = os.getenv("OLLAMA_KEEP_ALIVE")
    if v is None or not str(v).strip():
        return "0"
    return str(v).strip()


def _ollama_vision_timeout() -> int:
    try:
        return max(60, int(os.getenv("OLLAMA_VISION_TIMEOUT", "900")))
    except ValueError:
        return 900


def _ollama_base_url() -> str:
    base = (os.getenv("OLLAMA_URL") or os.getenv("LLM_BASE_URL") or "http://localhost:11434").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    if "/v1/chat" in base:
        base = base.replace("/v1/chat", "").rstrip("/")
    if "/api/chat" in base:
        base = base.replace("/api/chat", "").rstrip("/")
    return base


def _uses_llama_server() -> bool:
    """True when local LLM is llama-server (OpenAI /v1 on :8080), not native Ollama."""
    url = (os.getenv("LLM_BASE_URL") or os.getenv("OLLAMA_URL") or "").strip()
    if ":8080" in url or url.rstrip("/").endswith("/v1"):
        return True
    if os.getenv("LLM_REASONING", "").strip().lower() == "off":
        return True
    return False


def _openai_compat_base_url() -> str:
    base = (os.getenv("LLM_BASE_URL") or os.getenv("OLLAMA_URL") or "http://localhost:8080").rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def _openai_compat_api_key() -> str:
    return (os.getenv("LLM_API_KEY") or os.getenv("OLLAMA_API_KEY") or "ollama").strip()


def _llama_server_extra_body() -> Dict[str, Any]:
    return {
        "reasoning": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }


_openai_client: Optional[Any] = None


def _openai_compat_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(
            base_url=_openai_compat_base_url(),
            api_key=_openai_compat_api_key(),
        )
    return _openai_client


def ollama_unload_model(model: str) -> bool:
    """Free VRAM by unloading a model from Ollama (keep_alive=0). Returns True if request succeeded."""
    if _uses_llama_server():
        return True
    model = (model or "").strip()
    if not model:
        return False
    try:
        r = _ollama_http_session().post(
            f"{_ollama_base_url()}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=30,
        )
        r.raise_for_status()
        log.info("Unloaded Ollama model: %s", model)
        return True
    except Exception as e:
        log.warning("Failed to unload Ollama model %s: %s", model, e)
        return False


def ollama_unload_loaded_models() -> None:
    """Unload all models currently resident in Ollama (/api/ps)."""
    if _uses_llama_server():
        return
    try:
        r = _ollama_http_session().get(f"{_ollama_base_url()}/api/ps", timeout=15)
        r.raise_for_status()
        for entry in r.json().get("models") or []:
            name = (entry.get("name") or entry.get("model") or "").strip()
            if name:
                ollama_unload_model(name)
    except Exception as e:
        log.warning("Could not list Ollama models for unload: %s", e)


def ollama_models_unified() -> bool:
    """True when text and vision env vars point at the same Ollama model (no VRAM swap needed)."""
    text = (os.getenv("OLLAMA_MODEL") or "").strip()
    vision = (
        os.getenv("OLLAMA_VISION_MODEL")
        or os.getenv("PDF_OCR_MODEL")
        or "qwen2.5vl:32b"
    ).strip()
    return bool(text) and text == vision

_LOCAL_UNREACHABLE_MSG = (
    "Error: Local model unreachable and Anthropic fallback not enabled. "
    "Set ALLOW_ANTHROPIC_FALLBACK=true to confirm using Claude (incurs API cost)."
)
_ANTHROPIC_DISABLED_MSG = (
    "Error: Anthropic API key is set but ALLOW_ANTHROPIC_FALLBACK is not enabled. "
    "Set ALLOW_ANTHROPIC_FALLBACK=true to confirm using Claude (incurs API cost)."
)
_ANTHROPIC_CREDITS_MSG = "Error: Anthropic API credits exhausted or billing issue."
_NO_BACKEND_MSG = "Error: No LLM backend configured or reachable."


def _is_local_llm() -> bool:
    v = os.getenv("LOCAL_LLM", "").strip().lower()
    return v in ("true", "1", "yes")


def _use_anthropic() -> bool:
    return bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())


def _allow_anthropic_fallback() -> bool:
    v = os.getenv("ALLOW_ANTHROPIC_FALLBACK", "").strip().lower()
    return v in ("true", "1", "yes")


def _has_foundry_config() -> bool:
    endpoint = (os.getenv("FOUNDRY_ENDPOINT") or os.getenv("AZURE_AI_ENDPOINT") or "").strip()
    api_key = (os.getenv("FOUNDRY_API_KEY") or os.getenv("AZURE_INFERENCE_CREDENTIAL") or "").strip()
    return bool(endpoint and api_key)


def _is_llm_error(result: Dict[str, Any]) -> bool:
    content = ((result.get("message") or {}).get("content") or "").strip()
    return content.startswith("Error:")


def _is_anthropic_billing_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    needles = (
        "credit",
        "billing",
        "balance",
        "insufficient",
        "payment",
        "quota",
        "overloaded",
        "rate limit",
    )
    return any(n in msg for n in needles)


def llm_chat(
    model: str,
    messages: List[Dict[str, str]],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send chat completion request. Backend order:
    1. Local Ollama when LOCAL_LLM=true
    2. Microsoft Foundry when configured
    3. Anthropic only when ALLOW_ANTHROPIC_FALLBACK=true

    Returns dict with "message" -> "content".
    """
    options = options or {}
    last_error: Optional[Dict[str, Any]] = None

    if _is_local_llm():
        result = _local_ollama_chat(model, messages, options)
        if not _is_llm_error(result):
            return result
        last_error = result
        log.warning("Local Ollama request failed; trying configured fallbacks")

    if _has_foundry_config():
        result = _foundry_chat(model, messages, options)
        if not _is_llm_error(result):
            return result
        last_error = result
        log.warning("Foundry request failed; checking Anthropic fallback")

    if _allow_anthropic_fallback() and _use_anthropic():
        return _anthropic_chat(model, messages, options)

    if _is_local_llm():
        return {"message": {"content": _LOCAL_UNREACHABLE_MSG}}
    if _use_anthropic() and not _allow_anthropic_fallback():
        return {"message": {"content": _ANTHROPIC_DISABLED_MSG}}
    if last_error:
        return last_error
    return {"message": {"content": _NO_BACKEND_MSG}}


def _anthropic_chat(
    model: str,
    messages: List[Dict[str, str]],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """Use Anthropic Messages API (Claude) via official SDK with streaming."""
    try:
        from anthropic import Anthropic
    except ImportError:
        log.error("anthropic package required. pip install anthropic")
        return {"message": {"content": "Error: pip install anthropic"}}
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set")
        return {"message": {"content": "Error: ANTHROPIC_API_KEY not set."}}
    model_id = (os.getenv("ANTHROPIC_MODEL") or model or "claude-sonnet-4-20250514").strip()
    max_tokens = options.get("num_predict", 4096)
    anthropic_messages = []
    for m in messages:
        role = (m.get("role") or "user").lower()
        if role == "system":
            anthropic_messages.append({"role": "user", "content": f"[System: {m.get('content', '')}]"})
        else:
            anthropic_messages.append({"role": role, "content": (m.get("content") or "")})
    if not anthropic_messages:
        return {"message": {"content": "Error: No messages."}}
    try:
        client = Anthropic(api_key=api_key)
        content = ""
        with client.messages.stream(
            model=model_id,
            max_tokens=max_tokens,
            messages=anthropic_messages,
            temperature=options.get("temperature", 0.2),
        ) as stream:
            for text in stream.text_stream:
                content += text
        return {"message": {"role": "assistant", "content": content.strip()}}
    except Exception as e:
        if _is_anthropic_billing_error(e):
            log.error("Anthropic billing/credit issue: %s", e)
            return {"message": {"content": _ANTHROPIC_CREDITS_MSG}}
        log.error("Anthropic request failed: %s", e)
        return {"message": {"content": f"Error: Anthropic request failed. {e}"}}


def llm_vision_chat(
    model: str,
    text_prompt: str,
    image_bytes_list: List[bytes],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Vision request: one or more PNG/JPEG images plus a text prompt.
    Backend order:
    1. Local Ollama when LOCAL_LLM=true (OLLAMA_VISION_MODEL)
    2. Anthropic only when ALLOW_ANTHROPIC_FALLBACK=true
    """
    options = options or {}
    vision_model = (
        os.getenv("OLLAMA_VISION_MODEL")
        or os.getenv("PDF_OCR_MODEL")
        or model
        or "qwen2.5vl:32b"
    ).strip()

    if _is_local_llm():
        result = _local_ollama_vision_chat(vision_model, text_prompt, image_bytes_list, options)
        if not _is_llm_error(result):
            return result
        log.warning("Local Ollama vision request failed; checking Anthropic fallback")

    if _allow_anthropic_fallback() and _use_anthropic():
        return _anthropic_vision_chat(model, text_prompt, image_bytes_list, options)

    if _is_local_llm():
        return {"message": {"content": _LOCAL_UNREACHABLE_MSG}}
    if _use_anthropic() and not _allow_anthropic_fallback():
        return {"message": {"content": _ANTHROPIC_DISABLED_MSG}}
    return {
        "message": {
            "content": (
                "Error: Scanned PDF detected; configure LOCAL_LLM=true with OLLAMA_VISION_MODEL, "
                "or set ALLOW_ANTHROPIC_FALLBACK=true for Claude vision OCR."
            )
        }
    }


def _anthropic_vision_chat(
    model: str,
    text_prompt: str,
    image_bytes_list: List[bytes],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """Anthropic vision request via official SDK with streaming."""
    try:
        from anthropic import Anthropic
    except ImportError:
        log.error("anthropic package required. pip install anthropic")
        return {"message": {"content": "Error: pip install anthropic"}}
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set")
        return {"message": {"content": "Error: ANTHROPIC_API_KEY not set."}}
    model_id = (
        os.getenv("PDF_OCR_MODEL")
        or os.getenv("ANTHROPIC_MODEL")
        or model
        or "claude-sonnet-4-20250514"
    ).strip()
    max_tokens = options.get("num_predict", 4096)
    content: List[Dict[str, Any]] = []
    for img in image_bytes_list:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(img).decode("ascii"),
                },
            }
        )
    content.append({"type": "text", "text": text_prompt})
    try:
        client = Anthropic(api_key=api_key)
        text_out = ""
        with client.messages.stream(
            model=model_id,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
            temperature=options.get("temperature", 0.0),
        ) as stream:
            for text in stream.text_stream:
                text_out += text
        return {"message": {"role": "assistant", "content": text_out.strip()}}
    except Exception as e:
        if _is_anthropic_billing_error(e):
            log.error("Anthropic vision billing/credit issue: %s", e)
            return {"message": {"content": _ANTHROPIC_CREDITS_MSG}}
        log.error("Anthropic vision request failed: %s", e)
        return {"message": {"content": f"Error: Anthropic vision request failed. {e}"}}


def _local_openai_compat_vision_chat(
    model: str,
    text_prompt: str,
    image_bytes_list: List[bytes],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """Vision via llama-server OpenAI-compatible API (Qwen3.6 + mmproj)."""
    content: List[Dict[str, Any]] = [{"type": "text", "text": text_prompt}]
    for img in image_bytes_list:
        b64 = base64.standard_b64encode(img).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            }
        )
    try:
        resp = _openai_compat_client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            temperature=options.get("temperature", 0.0),
            max_tokens=options.get("num_predict", 4096),
            extra_body=_llama_server_extra_body(),
        )
        text_out = (resp.choices[0].message.content or "").strip()
        return {"message": {"role": "assistant", "content": text_out}}
    except Exception as e:
        log.error("Local llama-server vision request failed: %s", e)
        return {"message": {"content": f"Error: Unable to connect to llama-server vision. {e}"}}


def _local_openai_compat_chat(
    model: str,
    messages: List[Dict[str, str]],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """Text chat via llama-server OpenAI-compatible API."""
    try:
        resp = _openai_compat_client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=options.get("temperature", 0.3),
            max_tokens=options.get("num_predict", 1000),
            extra_body=_llama_server_extra_body(),
        )
        content = (resp.choices[0].message.content or "").strip()
        return {"message": {"role": "assistant", "content": content}}
    except Exception as e:
        log.error("Local llama-server request failed: %s", e)
        return {"message": {"content": f"Error: Unable to connect to llama-server. {e}"}}


def _local_ollama_vision_chat(
    model: str,
    text_prompt: str,
    image_bytes_list: List[bytes],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """Use local Ollama vision API with base64 images on the user message."""
    if _uses_llama_server():
        return _local_openai_compat_vision_chat(model, text_prompt, image_bytes_list, options)
    images = [base64.standard_b64encode(img).decode("ascii") for img in image_bytes_list]
    url = f"{_ollama_base_url()}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": text_prompt, "images": images}],
        "stream": False,
        "keep_alive": _ollama_keep_alive(),
        "options": {
            "temperature": options.get("temperature", 0.0),
            "top_p": options.get("top_p", 0.9),
            "repeat_penalty": options.get("repeat_penalty", 1.1),
            "num_predict": options.get("num_predict", 4096),
            "stop": options.get("stop"),
            "seed": options.get("seed"),
        },
    }
    payload["options"] = {k: v for k, v in payload["options"].items() if v is not None}
    try:
        r = _ollama_http_session().post(url, json=payload, timeout=_ollama_vision_timeout())
        r.raise_for_status()
        data = r.json()
        return data
    except Exception as e:
        log.error("Local Ollama vision request failed: %s", e)
        return {"message": {"content": f"Error: Unable to connect to Ollama vision. {e}"}}


def _local_ollama_chat(
    model: str,
    messages: List[Dict[str, str]],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """Use local Ollama API (OLLAMA_URL) or llama-server OpenAI /v1 when configured."""
    if _uses_llama_server():
        return _local_openai_compat_chat(model, messages, options)
    url = f"{_ollama_base_url()}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": _ollama_keep_alive(),
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
        r = _ollama_http_session().post(url, json=payload, timeout=600)
        r.raise_for_status()
        data = r.json()
        # Ollama returns {"message": {"role": "assistant", "content": "..."}}
        return data
    except Exception as e:
        log.error("Local Ollama request failed: %s", e)
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
    # Use FOUNDRY_INFERENCE_API_VERSION only here; FOUNDRY_API_VERSION is for *.openai.azure.com (SDK).
    if "services.ai.azure.com" in endpoint:
        api_version = (
            (os.getenv("FOUNDRY_INFERENCE_API_VERSION") or "2024-05-01-preview").strip()
            or "2024-05-01-preview"
        )
        url = f"{endpoint}/models/chat/completions?api-version={api_version}"
        log.debug("Foundry Model Inference host=%s api-version=%s", endpoint, api_version)
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
            log.error("Foundry inference request failed: %s", e)
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
        log.error("Foundry request failed: %s", e)
        return {"message": {"content": f"Error: Foundry request failed. {e}"}}
