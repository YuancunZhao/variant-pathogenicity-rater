from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from variant_pathogenicity_rater.data_sources.config import DataSourceConfig


@dataclass(frozen=True)
class ProviderHTTPResponse:
    url: str
    status: int | None
    text: str
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.text)


class ProviderHTTPError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        method: str = "GET",
        status: int | None = None,
        response_text: str | None = None,
        cause_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.method = method
        self.status = status
        self.response_text = response_text
        self.cause_type = cause_type

    def to_payload(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "url": self.url,
            "method": self.method,
            "status": self.status,
            "response_text": self.response_text,
            "cause_type": self.cause_type,
        }


class ProviderHTTPClient:
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        response = self.request("GET", url, params=params)
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise ProviderHTTPError(
                f"Provider returned malformed JSON: {exc.msg}",
                url=response.url,
                method="GET",
                status=response.status,
                response_text=response.text[:500],
                cause_type=exc.__class__.__name__,
            ) from exc

    def post_json(self, url: str, payload: dict[str, Any]) -> Any:
        response = self.request("POST", url, json_payload=payload)
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise ProviderHTTPError(
                f"Provider returned malformed JSON: {exc.msg}",
                url=response.url,
                method="POST",
                status=response.status,
                response_text=response.text[:500],
                cause_type=exc.__class__.__name__,
            ) from exc

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> ProviderHTTPResponse:
        full_url = _url_with_params(url, params)
        data = None
        if json_payload is not None:
            data = json.dumps(json_payload).encode("utf-8")
        headers = {
            "User-Agent": self.config.user_agent
            or "variant-pathogenicity-rater/0.3.0 optional-online-provider",
        }
        if json_payload is not None:
            headers["Content-Type"] = "application/json"
            headers["Accept"] = "application/json"
        last_error: ProviderHTTPError | None = None
        attempts = self.config.retry_count + 1
        for attempt in range(attempts):
            try:
                request = urllib.request.Request(full_url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(
                    request,
                    timeout=self.config.timeout_seconds,
                ) as response:
                    body = response.read().decode("utf-8")
                    return ProviderHTTPResponse(
                        url=full_url,
                        status=getattr(response, "status", None),
                        text=body,
                        headers=dict(getattr(response, "headers", {}) or {}),
                    )
            except urllib.error.HTTPError as exc:
                text = exc.read().decode("utf-8", errors="replace")
                last_error = ProviderHTTPError(
                    f"Provider HTTP error {exc.code}",
                    url=full_url,
                    method=method,
                    status=exc.code,
                    response_text=text[:500],
                    cause_type=exc.__class__.__name__,
                )
            except Exception as exc:  # noqa: BLE001 - callers turn provider errors into limitations.
                last_error = ProviderHTTPError(
                    f"Provider HTTP request failed: {exc.__class__.__name__}: {exc}",
                    url=full_url,
                    method=method,
                    cause_type=exc.__class__.__name__,
                )
            if attempt + 1 < attempts and self.config.retry_backoff_seconds:
                time.sleep(self.config.retry_backoff_seconds)
        raise last_error or ProviderHTTPError("Provider HTTP request failed.", url=full_url, method=method)


def _url_with_params(url: str, params: dict[str, Any] | None = None) -> str:
    if not params:
        return url
    return f"{url}?{urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})}"
