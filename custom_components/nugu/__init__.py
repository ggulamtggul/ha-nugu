"""NUGU Smart Home Pre-built Integration for Home Assistant."""
import logging
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the NUGU Smart Home integration."""
    _LOGGER.info("Setting up NUGU Smart Home Integration v1.5.0")

    views = [
        # OAuth 2.0 Account Linking 엔드포인트
        NuguOAuthAuthorizeView("/nugu/oauth/authorize"),
        NuguOAuthAuthorizeView("/oauth/authorize"),
        NuguOAuthTokenView("/nugu/oauth/token"),
        NuguOAuthTokenView("/oauth/token"),

        # Device Discovery 엔드포인트
        NuguDiscoveryView(hass, "/nugu/v1/devices"),
        NuguDiscoveryView(hass, "/v1/devices"),
        NuguDiscoveryView(hass, "/devices"),

        # Device Control 엔드포인트 (Capability Directives)
        NuguControlView(hass, "/nugu/v1/capabilities/{capability}/directives/{directive}"),
        NuguControlView(hass, "/v1/capabilities/{capability}/directives/{directive}"),
        NuguControlView(hass, "/capabilities/{capability}/directives/{directive}"),
        NuguControlView(hass, "/nugu/v1/control"),
        NuguControlView(hass, "/v1/control"),

        # Health Check 엔드포인트
        NuguHealthView("/nugu/v1/health"),
        NuguHealthView("/v1/health"),
        NuguHealthView("/health"),
    ]
    for view in views:
        hass.http.register_view(view)

    return True


class NuguOAuthAuthorizeView(HomeAssistantView):
    """View to handle OAuth 2.0 Authorization code flow for NUGU."""
    requires_auth = False

    def __init__(self, url: str) -> None:
        self.url = url
        self.name = f"nugu:oauth:authorize:{url}"

    async def get(self, request: web.Request) -> web.Response:
        _LOGGER.warning("NUGU OAuth Authorize query: %s", request.query)
        redirect_uri = request.query.get("redirect_uri", "")
        state = request.query.get("state", "")
        callback_url = f"{redirect_uri}?code=nugu_success_code&state={state}"
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><script>window.location.href="{callback_url}";</script></head><body><p>연동 완료</p></body></html>"""
        return web.Response(text=html, content_type="text/html")


class NuguOAuthTokenView(HomeAssistantView):
    """View to issue OAuth 2.0 access tokens to NUGU."""
    requires_auth = False

    def __init__(self, url: str) -> None:
        self.url = url
        self.name = f"nugu:oauth:token:{url}"

    async def post(self, request: web.Request) -> web.Response:
        _LOGGER.warning("NUGU OAuth Token request")
        return web.json_response({
            "access_token": "ha_nugu_token_2026",
            "token_type": "Bearer",
            "expires_in": 315360000,
            "refresh_token": "ha_nugu_refresh_token_2026"
        })


class NuguDiscoveryView(HomeAssistantView):
    """View to handle NUGU Smart Home Device Discovery."""
    requires_auth = False

    def __init__(self, hass: HomeAssistant, url: str) -> None:
        self.hass = hass
        self.url = url
        self.name = f"nugu:discovery:{url}"

    async def post(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        _LOGGER.warning("NUGU Discovery on %s: %s", self.url, body)
        devices = []
        for state in self.hass.states.async_all("light"):
            devices.append({
                "id": state.entity_id.replace(".", "_"),
                "deviceTypeCode": "LIGHT",
                "deviceTypeName": "조명",
                "deviceModelName": "HA",
                "friendlyNameSuggestion": state.name or state.entity_id,
                "manufacturer": "HA",
                "supportedCapabilities": {"powerControl": {}},
                "customData": {"entity_id": state.entity_id, "domain": "light"},
                "connectionStatus": state.state != "unavailable"
            })
        return web.json_response({"devices": devices})


class NuguControlView(HomeAssistantView):
    """View to handle NUGU Smart Home Control Directives."""
    requires_auth = False

    def __init__(self, hass: HomeAssistant, url: str) -> None:
        self.hass = hass
        self.url = url
        self.name = f"nugu:control:{url}"

    async def post(self, request: web.Request, capability: str = "", directive: str = "") -> web.Response:
        try:
            data = await request.json()
        except Exception:
            data = {}

        _LOGGER.warning("NUGU Control Request on %s: cap=%s, dir=%s, data=%s", self.url, capability, directive, data)

        req_id = data.get("requestId", "")
        action = data.get("action", {})
        command = action.get("command", {}) if isinstance(action, dict) else {}

        # Directive 추출 (URL 파라미터 또는 Body command)
        actual_directive = directive or command.get("smartHomeDirective", "")
        dir_lower = str(actual_directive).lower()
        is_off = any(w in dir_lower for w in ["turnoff", "off", "꺼", "소등", "stop", "close"])

        # 타겟 디바이스 목록 추출 (NUGU 스마트홈 smartHomeDevices 배열)
        target_devices = []
        if isinstance(action, dict) and "smartHomeDevices" in action:
            target_devices = action.get("smartHomeDevices") or []
        elif "device" in data:
            target_devices = [data["device"]]
        elif "smartHomeDevice" in data:
            target_devices = [data["smartHomeDevice"]]

        results = []
        for dev in target_devices:
            if not isinstance(dev, dict):
                continue
            custom = dev.get("customData", {})
            entity_id = custom.get("entity_id") or dev.get("id", "").replace("_", ".", 1)
            domain = custom.get("domain") or (entity_id.split(".")[0] if "." in entity_id else "light")
            service = "turn_off" if is_off else "turn_on"

            try:
                _LOGGER.warning("NUGU executing: %s.%s on %s", domain, service, entity_id)
                await self.hass.services.async_call(domain, service, {"entity_id": entity_id}, blocking=True)
                results.append({"resultCode": "OK", "smartHomeDevice": dev})
            except Exception as e:
                _LOGGER.error("Failed to control %s: %s", entity_id, e)
                results.append({"resultCode": "DeviceControlFailed", "smartHomeDevice": dev})

        if not results:
            results = [{"resultCode": "OK"}]

        resp = {"requestId": req_id, "data": results}
        _LOGGER.warning("NUGU Control Response: %s", resp)
        return web.json_response(resp)


class NuguHealthView(HomeAssistantView):
    """View to handle health checks."""
    requires_auth = False

    def __init__(self, url: str) -> None:
        self.url = url
        self.name = f"nugu:health:{url}"

    async def get(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "UP"})

    async def post(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "UP"})
