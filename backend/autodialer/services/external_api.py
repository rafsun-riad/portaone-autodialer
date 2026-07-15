from __future__ import annotations

from typing import Any

import requests
from django.conf import settings


class ExternalSystemError(Exception):
    def __init__(
        self,
        message: str,
        payload: dict[str, Any] | None = None,
        status_code: int = 400,
    ):
        super().__init__(message)
        self.payload = payload or {}
        self.status_code = status_code


class ExternalSystemClient:
    def __init__(self, access_token: str | None = None):
        self.access_token = access_token
        self.origin = settings.EXTERNAL_SYSTEM_ORIGIN.rstrip("/")

    def _headers(self, access_token: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        token = access_token or self.access_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            response = requests.request(
                method=method,
                url=f"{self.origin}{endpoint}",
                json=payload,
                headers=self._headers(access_token),
                timeout=30,
            )
        except requests.RequestException as exc:
            raise ExternalSystemError(
                "External system request failed.",
                payload={"faultstring": str(exc), "faultcode": "request_error"},
                status_code=502,
            ) from exc

        try:
            data = response.json()
        except ValueError:
            data = {
                "faultstring": response.text
                or "External system returned an invalid response.",
                "faultcode": "invalid_json",
            }

        if response.status_code >= 400 or "faultcode" in data:
            raise ExternalSystemError(
                data.get("faultstring", "External system request failed."),
                payload=data,
                status_code=response.status_code
                if response.status_code >= 400
                else 400,
            )

        return data

    def login(self, username: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/Session/login",
            {"params": {"login": username, "password": password}},
        )

    def change_password(
        self, username: str, password: str, new_password: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/Session/change_password",
            {
                "params": {
                    "login": username,
                    "password": password,
                    "new_password": new_password,
                }
            },
        )

    def get_customer_info(self) -> dict[str, Any]:
        return self._request("POST", "/Customer/get_customer_info", {})

    def get_account_list(self, i_customer: int) -> dict[str, Any]:
        return self._request(
            "POST",
            "/Account/get_account_list",
            {"params": {"i_customer": i_customer}},
        )

    def originate_call(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/CallControl/originate_call", {"params": params})

    def play_audio(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/CallControl/play", {"params": params})
