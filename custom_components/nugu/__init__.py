"""NUGU Smart Home Integration for Home Assistant."""
import logging
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the NUGU Smart Home component."""
    _LOGGER.info("Setting up NUGU Smart Home Integration")

    views = [
        NuguOAuthAuthorizeView(),
        NuguOAuthTokenView(),
        NuguDiscoveryView(hass, "/nugu/v1/devices"),
        NuguDiscoveryView(hass, "/v1/devices"),
        NuguControlView(hass, "/nugu/v1/capabilities/{capability}/directives/{directive}"),
        NuguControlView(hass, "/v1/capabilities/{capability}/directives/{directive}"),
        NuguHealthView("/nugu/v1/health"),
        NuguHealthView("/v1/health"),
    ]
    for view in views:
        hass.http.register_view(view)

    return True


class NuguOAuthAuthorizeView(HomeAssistantView):
    """View to handle OAuth 2.0 Authorization request from NUGU app."""
    url = "/nugu/oauth/authorize"
    name = "nugu:oauth:authorize"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        redirect_uri = request.query.get("redirect_uri", "")
        state = request.query.get("state", "")
        callback_url = f"{redirect_uri}?code=nugu_success_code&state={state}"

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Home Assistant - NUGU 연동</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
            background: #f0f2f5;
        }}
        .card {{
            background: white;
            padding: 30px;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            text-align: center;
            max-width: 360px;
            width: 85%;
        }}
        h2 {{ color: #03a9f4; margin-top: 0; }}
        p {{ color: #555; font-size: 15px; line-height: 1.5; }}
        .btn {{
            display: inline-block;
            background: #03a9f4;
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: bold;
            font-size: 16px;
            margin-top: 15px;
        }}
    </style>
    <script>
        setTimeout(function() {{
            window.location.href = "{callback_url}";
        }}, 800);
    </script>
</head>
<body>
    <div class="card">
        <h2>Home Assistant</h2>
        <p>NUGU 스피커 연결을 승인합니다.</p>
        <p style="font-size:12px; color:#888;">잠시 후 자동으로 완료됩니다...</p>
        <a href="{callback_url}" class="btn">연동 승인</a>
    </div>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")


class NuguOAuthTokenView(HomeAssistantView):
    """View to handle OAuth 2.0 Token requests from NUGU."""
    url = "/nugu/oauth/token"
    name = "nugu:oauth:token"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        return web.json_response({
            "access_token": "ha_nugu_token_2026",
            "token_type": "Bearer",
            "expires_in": 315360000,
            "refresh_token": "ha_nugu_refresh_token_2026"
        })


class NuguDiscoveryView(HomeAssistantView):
    """View to handle device discovery for NUGU."""
    requires_auth = False

    def __init__(self, hass: HomeAssistant, url: str) -> None:
        self.hass = hass
        self.url = url
        self.name = f"nugu:discovery:{url}"

    async def post(self, request: web.Request) -> web.Response:
        devices = []

        # 1. Lights
        for state in self.hass.states.async_all("light"):
            devices.append({
                "id": state.entity_id.replace(".", "_"),
                "deviceTypeCode": "LIGHT",
                "deviceTypeName": "조명",
                "deviceModelName": "HomeAssistant",
                "friendlyNameSuggestion": state.name or state.entity_id,
                "manufacturer": "Home Assistant",
                "supportedCapabilities": {
                    "powerControl": {}
                },
                "customData": {
                    "entity_id": state.entity_id,
                    "domain": "light"
                },
                "connectionStatus": state.state != "unavailable"
            })

        # 2. Climates (Aircon & Heater)
        for state in self.hass.states.async_all("climate"):
            is_aircon = "aircon" in state.entity_id.lower() or "에어컨" in (state.name or "")
            devices.append({
                "id": state.entity_id.replace(".", "_"),
                "deviceTypeCode": "AIR_CONDITIONER" if is_aircon else "BOILER",
                "deviceTypeName": "에어컨" if is_aircon else "난방",
                "deviceModelName": "HomeAssistant",
                "friendlyNameSuggestion": state.name or state.entity_id,
                "manufacturer": "Home Assistant",
                "supportedCapabilities": {
                    "powerControl": {},
                    "temperatureControl": {}
                },
                "customData": {
                    "entity_id": state.entity_id,
                    "domain": "climate"
                },
                "connectionStatus": state.state != "unavailable"
            })

        # 3. Vacuums
        for state in self.hass.states.async_all("vacuum"):
            devices.append({
                "id": state.entity_id.replace(".", "_"),
                "deviceTypeCode": "ROBOT_CLEANER",
                "deviceTypeName": "로봇청소기",
                "deviceModelName": "HomeAssistant",
                "friendlyNameSuggestion": state.name or state.entity_id,
                "manufacturer": "Home Assistant",
                "supportedCapabilities": {
                    "powerControl": {}
                },
                "customData": {
                    "entity_id": state.entity_id,
                    "domain": "vacuum"
                },
                "connectionStatus": state.state != "unavailable"
            })

        _LOGGER.info("Returning %d devices to NUGU", len(devices))
        return web.json_response({"devices": devices})


class NuguControlView(HomeAssistantView):
    """View to handle capability directives from NUGU."""
    requires_auth = False

    def __init__(self, hass: HomeAssistant, url: str) -> None:
        self.hass = hass
        self.url = url
        self.name = f"nugu:control:{url}"

    async def post(self, request: web.Request, capability: str, directive: str) -> web.Response:
        data = await request.json()
        request_id = data.get("requestId", "")
        device = data.get("device", {})
        custom_data = device.get("customData", {})
        entity_id = custom_data.get("entity_id") or device.get("id", "").replace("_", ".", 1)
        domain = custom_data.get("domain") or entity_id.split(".")[0]

        try:
            if capability.lower() == "powercontrol":
                if directive == "TurnOn":
                    if domain == "vacuum":
                        await self.hass.services.async_call("vacuum", "start", {"entity_id": entity_id}, blocking=True)
                    else:
                        await self.hass.services.async_call(domain, "turn_on", {"entity_id": entity_id}, blocking=True)
                elif directive == "TurnOff":
                    if domain == "vacuum":
                        await self.hass.services.async_call("vacuum", "return_to_base", {"entity_id": entity_id}, blocking=True)
                    else:
                        await self.hass.services.async_call(domain, "turn_off", {"entity_id": entity_id}, blocking=True)

            elif capability.lower() == "temperaturecontrol" and directive == "SetTargetTemperature":
                temp = data.get("targetTemperature") or data.get("intent", {}).get("temperature")
                if temp:
                    await self.hass.services.async_call("climate", "set_temperature", {
                        "entity_id": entity_id, "temperature": float(temp)
                    }, blocking=True)

            return web.json_response({
                "requestId": request_id,
                "data": [
                    {
                        "resultCode": "OK",
                        "smartHomeDevice": device
                    }
                ]
            })
        except Exception as e:
            _LOGGER.error("Failed to execute NUGU directive: %s", e)
            return web.json_response({
                "requestId": request_id,
                "data": [
                    {
                        "resultCode": "ERROR",
                        "smartHomeDevice": device,
                        "error": str(e)
                    }
                ]
            }, status=500)


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
