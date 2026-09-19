from __future__ import annotations

from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientSession, ClientTimeout


class VeyraApiError(Exception):
    """Base Veyra API error."""


class VeyraConnectionError(VeyraApiError):
    """Veyra is unreachable."""


class VeyraApi:
    def __init__(self, session: ClientSession, host: str, port: int) -> None:
        self.session = session
        self.host = host.strip().replace("http://", "").replace("https://", "").strip("/")
        self.port = int(port)
        self.info_data: dict[str, Any] = {}

    @property
    def base_url(self) -> str:
        host = self.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.port}"

    async def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with self.session.request(
                method,
                self.base_url + path,
                timeout=ClientTimeout(total=6),
                **kwargs,
            ) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise VeyraApiError(f"HTTP {resp.status}: {text[:200]}")
                data = await resp.json()
                if not isinstance(data, dict):
                    raise VeyraApiError("Invalid Veyra response")
                return data
        except VeyraApiError:
            raise
        except (ClientError, TimeoutError, OSError) as err:
            raise VeyraConnectionError(str(err)) from err

    async def async_info(self) -> dict[str, Any]:
        self.info_data = await self._json("GET", "/api/ha/v1/info")
        return self.info_data

    async def async_status(self) -> dict[str, Any]:
        return await self._json("GET", "/api/ha/v1/status")

    async def async_set_global(self, feature: str, enabled: bool) -> dict[str, Any]:
        return await self._json(
            "PUT", "/api/ha/v1/runtime", json={"feature": feature, "enabled": bool(enabled)}
        )

    async def async_set_camera(self, camera: str, feature: str, enabled: bool) -> dict[str, Any]:
        return await self._json(
            "PUT",
            f"/api/ha/v1/cameras/{camera}/runtime",
            json={"feature": feature, "enabled": bool(enabled)},
        )

    async def _image(self, path: str, error_name: str) -> bytes | None:
        try:
            async with self.session.get(
                self.base_url + path,
                timeout=ClientTimeout(total=6),
            ) as resp:
                if resp.status == 404:
                    return None
                if resp.status >= 400:
                    raise VeyraApiError(f"{error_name} HTTP {resp.status}")
                return await resp.read()
        except VeyraApiError:
            raise
        except (ClientError, TimeoutError, OSError) as err:
            raise VeyraConnectionError(str(err)) from err

    async def async_camera_image(self, camera: str) -> bytes | None:
        return await self._image(
            f"/api/ha/v1/cameras/{quote(str(camera), safe='')}/snapshot.jpg",
            "Snapshot",
        )

    async def async_event_thumbnail(self, event_id: str) -> bytes | None:
        safe_id = quote(str(event_id), safe="")
        return await self._image(
            f"/api/ainvr/notifications/{safe_id}/thumbnail.jpg",
            "Event thumbnail",
        )

    async def async_event_current_image(self, event_id: str) -> bytes | None:
        safe_id = quote(str(event_id), safe="")
        return await self._image(
            f"/api/ainvr/notifications/{safe_id}/current.jpg",
            "Current notification frame",
        )

    def rtsp_url(self, stream: str) -> str:
        port = int(((self.info_data.get("go2rtc") or {}).get("rtsp_port") or 8554))
        host = self.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"rtsp://{host}:{port}/{stream}"
