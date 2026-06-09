"""翻译后端：DeepSeek API / Claude Code headless。

两个后端都暴露同一个接口 `translate(system_prompt, text) -> str`。
通过 `build_backend(name, **kwargs)` 工厂选择实例化哪一个。
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import http.client
from typing import Protocol


class TranslationBackend(Protocol):
    def translate(self, system_prompt: str, text: str) -> str: ...


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


class DeepSeekBackend:
    """DeepSeek (OpenAI 兼容) Chat Completions 后端。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        timeout: int = 120,
        retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.retries = retries

    def translate(self, system_prompt: str, text: str) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": self.temperature,
            "stream": False,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8")
                parsed = json.loads(body)
                return _strip_code_fence(parsed["choices"][0]["message"]["content"])
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError, ConnectionError, http.client.HTTPException) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                wait = min(30, 2 ** attempt)
                print(f"[warn] DeepSeek 请求失败，{wait}s 后重试：{exc}", flush=True)
                time.sleep(wait)

        raise RuntimeError(f"DeepSeek 请求失败：{last_error}")


class ClaudeCodeBackend:
    """通过 `claude -p` headless 模式调用 Claude Code 做翻译。

    认证自动继承当前 shell 的 Claude Code session（无需独立 API key）。
    模型解析优先级：参数 model > 环境变量 CLAUDE_CODE_SUBAGENT_MODEL > 不传 --model。
    """

    def __init__(
        self,
        model: str | None = None,
        timeout: int = 300,
        retries: int = 2,
    ) -> None:
        self.model = model or os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL") or None
        self.timeout = timeout
        self.retries = retries

    def translate(self, system_prompt: str, text: str) -> str:
        prompt = f"{system_prompt}\n\n---\n\n{text}"
        cmd = [
            "claude", "-p", prompt,
            "--output-format", "json",
            "--permission-mode", "dontAsk",
            "--allowedTools", "Read",
            "--max-turns", "1",
        ]
        if self.model:
            cmd += ["--model", self.model]

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"claude -p 返回非零退出码 {result.returncode}: {result.stderr.strip()[:500]}"
                    )
                parsed = json.loads(result.stdout)
                if "result" not in parsed:
                    raise KeyError(f"claude -p 输出无 result 字段: {result.stdout[:500]}")
                return _strip_code_fence(parsed["result"])
            except (subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError, KeyError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                wait = min(30, 2 ** attempt)
                print(f"[warn] claude -p 请求失败，{wait}s 后重试：{exc}", flush=True)
                time.sleep(wait)

        raise RuntimeError(f"claude -p 请求失败：{last_error}")


class AgyBackend:
    """通过 `agy -p` headless 模式调用 Antigravity 做翻译。

    模型解析优先级：参数 model > 环境变量 AGY_SUBAGENT_MODEL > 不传 --model。
    """

    def __init__(
        self,
        model: str | None = None,
        timeout: int = 300,
        retries: int = 2,
    ) -> None:
        self.model = model or os.environ.get("AGY_SUBAGENT_MODEL") or None
        self.timeout = timeout
        self.retries = retries

    def translate(self, system_prompt: str, text: str) -> str:
        prompt = f"{system_prompt}\n\n---\n\n{text}"
        cmd = [
            "agy", "-p", prompt,
        ]
        if self.model:
            cmd += ["--model", self.model]

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"agy -p 返回非零退出码 {result.returncode}: {result.stderr.strip()[:500]}"
                    )
                return _strip_code_fence(result.stdout)
            except (subprocess.TimeoutExpired, RuntimeError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                wait = min(30, 2 ** attempt)
                print(f"[warn] agy -p 请求失败，{wait}s 后重试：{exc}", flush=True)
                time.sleep(wait)

        raise RuntimeError(f"agy -p 请求失败：{last_error}")


def build_backend(name: str, **kwargs: object) -> TranslationBackend:
    """工厂：按名字实例化后端，自动过滤无关 kwargs。"""
    if name == "deepseek":
        accepted = {"api_key", "base_url", "model", "temperature", "max_tokens", "timeout", "retries"}
        return DeepSeekBackend(**{k: v for k, v in kwargs.items() if k in accepted})  # type: ignore[arg-type]
    if name == "claude":
        accepted = {"model", "timeout", "retries"}
        return ClaudeCodeBackend(**{k: v for k, v in kwargs.items() if k in accepted})  # type: ignore[arg-type]
    if name == "agy":
        accepted = {"model", "timeout", "retries"}
        return AgyBackend(**{k: v for k, v in kwargs.items() if k in accepted})  # type: ignore[arg-type]
    raise SystemExit(f"未知 backend: {name}（可选: deepseek / claude / agy）")
