"""FastAPI HTTP server exposing SmartUSBHub operations."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from smartusbhub_cli import config as config_module
from smartusbhub_cli.commit import get_commit_hash
from smartusbhub_cli.protocol import (
    HubError,
    HubNotFoundError,
    HubProtocol,
    HubState,
    HubTimeoutError,
)
from smartusbhub_cli.utils import resolve_channels


class PowerRequest(BaseModel):
    channels: List[int]
    state: bool


class DatalineRequest(BaseModel):
    channels: List[int]
    state: bool


class DefaultStatusRequest(BaseModel):
    channels: List[int]
    enable: bool
    state: Optional[bool] = None


class ToggleRequest(BaseModel):
    enable: bool


class ModeRequest(BaseModel):
    mode: str  # "normal" or "interlock"


class AddressRequest(BaseModel):
    address: int


class APIResponse(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None


class ServerState:
    """Shared server state holding the HubProtocol instance."""

    def __init__(self) -> None:
        self.protocol: Optional[HubProtocol] = None


_server_state = ServerState()


def _get_protocol() -> HubProtocol:
    if _server_state.protocol is None:
        raise HubNotFoundError("No serial connection configured")
    return _server_state.protocol


def _parse_channels(channels: str) -> List[int]:
    if not channels.strip():
        return [1, 2, 3, 4]
    parsed = []
    for part in channels.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError as exc:
            raise ValueError(f"Invalid channel value: {part}") from exc
        parsed.append(value)
    return resolve_channels(parsed, all_channels=False)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage the shared HubProtocol instance across requests."""
    if _server_state.protocol is None:
        cfg = config_module.load_config()
        device = getattr(lifespan, "port_name", None) or cfg.device

        if device:
            try:
                _server_state.protocol = HubProtocol(device, cfg.baudrate, cfg.timeout)
            except HubError:
                # The server can still start; endpoints will return 503 until
                # the connection is available.
                _server_state.protocol = None

    yield

    if _server_state.protocol is not None:
        _server_state.protocol.close()
        _server_state.protocol = None


app = FastAPI(title="SmartUSBHub REST API", version="0.1.0", lifespan=lifespan)

logger = logging.getLogger(__name__)
EXPECTED_COMMIT_HASH = get_commit_hash()


@app.middleware("http")
async def _commit_hash_middleware(request: Request, call_next: Any) -> JSONResponse:
    """Validate that every request carries the matching git commit hash."""
    client_hash = request.headers.get("X-Commit-Hash")
    if client_hash != EXPECTED_COMMIT_HASH:
        client_host = request.client.host if request.client else "-"
        logger.warning(
            "Commit hash mismatch from %s at %s: expected %s, got %s",
            client_host,
            datetime.now(timezone.utc).isoformat(),
            EXPECTED_COMMIT_HASH,
            client_hash,
        )
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "data": None,
                "error": (
                    f"Commit hash mismatch: expected {EXPECTED_COMMIT_HASH}, "
                    f"got {client_hash}"
                ),
            },
        )
    return await call_next(request)


@app.exception_handler(HubError)
async def _hub_error_handler(_request: Request, exc: HubError) -> JSONResponse:
    status_code = 503 if isinstance(exc, HubNotFoundError) else 504
    if isinstance(exc, HubTimeoutError):
        status_code = 504
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "data": None, "error": str(exc)},
    )


@app.exception_handler(ValueError)
async def _value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"success": False, "data": None, "error": str(exc)},
    )


@app.get("/")
async def root() -> Dict[str, str]:
    return {"name": "smartusbhub-cli-api", "version": "0.1.0"}


@app.get("/health")
async def health() -> APIResponse:
    return APIResponse(
        success=True,
        data={"connected": _server_state.protocol is not None},
    )


# ------------------------------------------------------------------
# Power
# ------------------------------------------------------------------
@app.post("/power")
async def set_power(req: PowerRequest) -> APIResponse:
    channels = resolve_channels(req.channels)
    _get_protocol().set_power(channels, req.state)
    return APIResponse(success=True, data={"set": True})


@app.get("/power")
async def get_power(channels: str = "1,2,3,4") -> APIResponse:
    channels_list = _parse_channels(channels)
    data = _get_protocol().get_power(channels_list)
    return APIResponse(success=True, data=data)


@app.post("/interlock/{channel}")
async def set_interlock(channel: int) -> APIResponse:
    _get_protocol().set_interlock(channel)
    return APIResponse(success=True, data={"channel": channel, "interlock": True})


# ------------------------------------------------------------------
# Dataline
# ------------------------------------------------------------------
@app.post("/dataline")
async def set_dataline(req: DatalineRequest) -> APIResponse:
    channels = resolve_channels(req.channels)
    _get_protocol().set_dataline(channels, req.state)
    return APIResponse(success=True, data={"set": True})


@app.get("/dataline")
async def get_dataline(channels: str = "1,2,3,4") -> APIResponse:
    channels_list = _parse_channels(channels)
    data = _get_protocol().get_dataline(channels_list)
    return APIResponse(success=True, data=data)


# ------------------------------------------------------------------
# Measurements
# ------------------------------------------------------------------
@app.get("/voltage/{channel}")
async def get_voltage(channel: int) -> APIResponse:
    data = _get_protocol().get_voltage(channel)
    return APIResponse(success=True, data={"channel": channel, "voltage": data})


@app.get("/current/{channel}")
async def get_current(channel: int) -> APIResponse:
    data = _get_protocol().get_current(channel)
    return APIResponse(success=True, data={"channel": channel, "current": data})


# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
@app.post("/config/default-power")
async def set_default_power(req: DefaultStatusRequest) -> APIResponse:
    channels = resolve_channels(req.channels)
    _get_protocol().set_default_power(channels, req.enable, req.state)
    return APIResponse(success=True, data={"set": True})


@app.get("/config/default-power")
async def get_default_power(channels: str = "1,2,3,4") -> APIResponse:
    channels_list = _parse_channels(channels)
    data = _get_protocol().get_default_power(channels_list)
    return APIResponse(success=True, data=data)


@app.post("/config/default-dataline")
async def set_default_dataline(req: DefaultStatusRequest) -> APIResponse:
    channels = resolve_channels(req.channels)
    _get_protocol().set_default_dataline(channels, req.enable, req.state)
    return APIResponse(success=True, data={"set": True})


@app.get("/config/default-dataline")
async def get_default_dataline(channels: str = "1,2,3,4") -> APIResponse:
    channels_list = _parse_channels(channels)
    data = _get_protocol().get_default_dataline(channels_list)
    return APIResponse(success=True, data=data)


@app.post("/config/auto-restore")
async def set_auto_restore(req: ToggleRequest) -> APIResponse:
    data = _get_protocol().set_auto_restore(req.enable)
    return APIResponse(success=True, data={"enabled": data})


@app.get("/config/auto-restore")
async def get_auto_restore() -> APIResponse:
    data = _get_protocol().get_auto_restore()
    return APIResponse(success=True, data={"enabled": data})


@app.post("/config/button-control")
async def set_button_control(req: ToggleRequest) -> APIResponse:
    data = _get_protocol().set_button_control(req.enable)
    return APIResponse(success=True, data={"enabled": data})


@app.get("/config/button-control")
async def get_button_control() -> APIResponse:
    data = _get_protocol().get_button_control()
    return APIResponse(success=True, data={"enabled": data})


@app.post("/config/operate-mode")
async def set_operate_mode(req: ModeRequest) -> APIResponse:
    data = _get_protocol().set_operate_mode(req.mode)
    return APIResponse(success=True, data={"mode": data})


@app.get("/config/operate-mode")
async def get_operate_mode() -> APIResponse:
    data = _get_protocol().get_operate_mode()
    return APIResponse(success=True, data={"mode": data})


@app.post("/config/device-address")
async def set_device_address(req: AddressRequest) -> APIResponse:
    data = _get_protocol().set_device_address(req.address)
    return APIResponse(success=True, data={"address": data})


@app.get("/config/device-address")
async def get_device_address() -> APIResponse:
    data = _get_protocol().get_device_address()
    return APIResponse(success=True, data={"address": data})


@app.post("/factory-reset")
async def factory_reset() -> APIResponse:
    _get_protocol().factory_reset()
    return APIResponse(success=True, data={"reset": True})


@app.get("/version/firmware")
async def get_firmware_version() -> APIResponse:
    data = _get_protocol().get_firmware_version()
    return APIResponse(success=True, data={"version": data})


@app.get("/version/hardware")
async def get_hardware_version() -> APIResponse:
    data = _get_protocol().get_hardware_version()
    return APIResponse(success=True, data={"version": data})


@app.get("/device-info")
async def get_device_info() -> APIResponse:
    info = _get_protocol().get_device_info()
    if isinstance(info, HubState):
        data = info.to_dict()
    else:
        data = info
    return APIResponse(success=True, data=data)


def run_server(host: str, port: int, port_name: Optional[str] = None) -> None:
    """Run the uvicorn server."""
    import uvicorn

    # Pass the requested serial port into the lifespan context.
    lifespan.port_name = port_name
    uvicorn.run(app, host=host, port=port)
