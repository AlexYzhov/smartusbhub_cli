"""HTTP client for remote CLI mode.

When ``--remote URL`` is provided, the CLI delegates commands to the REST API
using this thin client so that local and remote usage look identical.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from smartusbhub_cli.commit import get_commit_hash


class HTTPClientError(Exception):
    """Raised when the HTTP server returns an error envelope."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class HTTPClient:
    """Client that talks to a smartusbhub_cli HTTP server."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(
            timeout=timeout,
            headers={"X-Commit-Hash": get_commit_hash()},
        )

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Make an HTTP request and return the JSON ``data`` field."""
        url = f"{self.base_url}{path}"
        response = self._client.request(method, url, json=json_data, params=params)
        try:
            payload = response.json()
        except Exception as exc:
            raise HTTPClientError(
                f"Invalid JSON response from server: {response.text}",
                status_code=response.status_code,
            ) from exc

        if not payload.get("success", False):
            raise HTTPClientError(
                payload.get("error") or f"Server returned success=false for {path}",
                status_code=response.status_code,
            )
        return payload.get("data")

    @staticmethod
    def _channels_param(channels: List[int]) -> str:
        return ",".join(str(ch) for ch in channels)

    # ------------------------------------------------------------------
    # Power
    # ------------------------------------------------------------------
    @staticmethod
    def _int_keys(data: Dict[str, Any]) -> Dict[int, Any]:
        """Convert stringified integer keys back to integers."""
        return {int(k): v for k, v in data.items()}

    def set_power(self, channels: List[int], state: bool) -> bool:
        return self._request("POST", "/power", {"channels": channels, "state": state})["set"]

    def get_power(self, channels: List[int]) -> Dict[int, bool]:
        return self._int_keys(
            self._request("GET", "/power", params={"channels": self._channels_param(channels)})
        )

    def set_interlock(self, channel: int) -> bool:
        self._request("POST", f"/interlock/{channel}")
        return True

    # ------------------------------------------------------------------
    # Dataline
    # ------------------------------------------------------------------
    def set_dataline(self, channels: List[int], state: bool) -> bool:
        return self._request("POST", "/dataline", {"channels": channels, "state": state})["set"]

    def get_dataline(self, channels: List[int]) -> Dict[int, bool]:
        return self._int_keys(
            self._request("GET", "/dataline", params={"channels": self._channels_param(channels)})
        )

    # ------------------------------------------------------------------
    # Measurements
    # ------------------------------------------------------------------
    def get_voltage(self, channel: int) -> float:
        return self._request("GET", f"/voltage/{channel}")["voltage"]

    def get_current(self, channel: int) -> float:
        return self._request("GET", f"/current/{channel}")["current"]

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def set_default_power(
        self, channels: List[int], enable: bool, state: Optional[bool] = None
    ) -> bool:
        payload: Dict[str, Any] = {"channels": channels, "enable": enable}
        if state is not None:
            payload["state"] = state
        return self._request("POST", "/config/default-power", payload)["set"]

    def get_default_power(self, channels: List[int]) -> Dict[int, Dict[str, bool]]:
        return self._int_keys(
            self._request(
                "GET", "/config/default-power", params={"channels": self._channels_param(channels)}
            )
        )

    def set_default_dataline(
        self, channels: List[int], enable: bool, state: Optional[bool] = None
    ) -> bool:
        payload: Dict[str, Any] = {"channels": channels, "enable": enable}
        if state is not None:
            payload["state"] = state
        return self._request("POST", "/config/default-dataline", payload)["set"]

    def get_default_dataline(self, channels: List[int]) -> Dict[int, Dict[str, bool]]:
        return self._int_keys(
            self._request(
                "GET",
                "/config/default-dataline",
                params={"channels": self._channels_param(channels)},
            )
        )

    def set_auto_restore(self, enable: bool) -> bool:
        return self._request("POST", "/config/auto-restore", {"enable": enable})["enabled"]

    def get_auto_restore(self) -> bool:
        return self._request("GET", "/config/auto-restore")["enabled"]

    def set_button_control(self, enable: bool) -> bool:
        return self._request("POST", "/config/button-control", {"enable": enable})["enabled"]

    def get_button_control(self) -> bool:
        return self._request("GET", "/config/button-control")["enabled"]

    def set_operate_mode(self, mode: str) -> str:
        return self._request("POST", "/config/operate-mode", {"mode": mode})["mode"]

    def get_operate_mode(self) -> str:
        return self._request("GET", "/config/operate-mode")["mode"]

    def set_device_address(self, address: int) -> int:
        return self._request("POST", "/config/device-address", {"address": address})["address"]

    def get_device_address(self) -> int:
        return self._request("GET", "/config/device-address")["address"]

    def factory_reset(self) -> bool:
        return self._request("POST", "/factory-reset")["reset"]

    def get_firmware_version(self) -> str:
        return self._request("GET", "/version/firmware")["version"]

    def get_hardware_version(self) -> str:
        return self._request("GET", "/version/hardware")["version"]

    def get_device_info(self) -> Dict[str, Any]:
        return self._request("GET", "/device-info")
