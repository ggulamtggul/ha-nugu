"""NUGU Smart Home & Custom Play Unified Integration for Home Assistant.

Specifically tailored for Light control adhering 100% to NUGU Pre-built SmartHome
and Custom Play specifications.
"""
import logging
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the NUGU Light integration with both SmartHome and Custom Play support."""
    _LOGGER.info("Setting up NUGU Light Integration v%s", VERSION)

    views = [
        # --- 1. Custom Play (커스텀 플레이: 우리집에서 / myhahome에서) 엔드포인트 ---
        NuguActionView(hass, "/nugu/action"),
        NuguActionView(hass, "/nugu/action/{action_name}"),
        NuguActionView(hass, "/nugu/{action_name}"),
        NuguActionView(hass, "/{action_name}"),

        # --- 2. Smart Home Pre-built (호출어 없이 바로 제어) 엔드포인트 ---
        NuguOAuthAuthorizeView("/nugu/oauth/authorize"),
        NuguOAuthAuthorizeView("/oauth/authorize"),
        NuguOAuthTokenView("/nugu/oauth/token"),
        NuguOAuthTokenView("/oauth/token"),

        NuguDiscoveryView(hass, "/nugu/v1/devices"),
        NuguDiscoveryView(hass, "/v1/devices"),
        NuguDiscoveryView(hass, "/devices"),

        NuguControlView(hass, "/nugu/v1/capabilities/{capability}/directives/{directive}"),
        NuguControlView(hass, "/v1/capabilities/{capability}/directives/{directive}"),
        NuguControlView(hass, "/capabilities/{capability}/directives/{directive}"),
        NuguControlView(hass, "/nugu/v1/control"),
        NuguControlView(hass, "/v1/control"),

        # --- 3. Health Check 엔드포인트 ---
        NuguHealthView("/nugu/v1/health"),
        NuguHealthView("/v1/health"),
        NuguHealthView("/health"),
    ]
    for view in views:
        hass.http.register_view(view)

    return True


# =====================================================================
# 1. 커스텀 플레이 (Custom Play) 핸들러
# =====================================================================
class NuguActionView(HomeAssistantView):
    """View to handle Custom Play requests from NUGU Backend Proxy."""
    requires_auth = False

    def __init__(self, hass: HomeAssistant, url: str) -> None:
        self.hass = hass
        self.url = url
        self.name = f"nugu:action:{url}"

    async def post(self, request: web.Request, action_name: str = "") -> web.Response:
        try:
            data = await request.json()
        except Exception:
            data = {}

        _LOGGER.warning("NUGU Custom Action Request on %s: %s", self.url, data)
        action = data.get("action", {})
        params = action.get("parameters", {})

        # 파라미터 추출
        extracted = {}
        for k, v in params.items():
            if isinstance(v, dict):
                extracted[k] = v.get("value", "")
            else:
                extracted[k] = str(v)

        location = extracted.get("location", "").strip()
        device_type = extracted.get("device", "").strip()
        action_type = extracted.get("action_type", "").strip()
        combined_text = f"{location} {device_type} {action_type}"

        # 켜기 / 끄기 판별
        is_turn_off = any(w in combined_text for w in ["꺼", "끄", "중지", "종료", "멈춰", "off", "정지", "소등"])

        # 전체 제어 여부 판별
        is_all = any(w in combined_text for w in ["다", "전체", "모두", "전부", "모든", "집안", "일괄"])

        output_data = {k: v for k, v in extracted.items()}

        try:
            if is_all:
                targets = [s.entity_id for s in self.hass.states.async_all("light")]
                loc_name = "집안 전체"
            else:
                loc_map = {
                    "거실": ["light.room_1_light_1", "light.room_1_light_2"],
                    "안방": ["light.room_2_light_1"],
                    "침실": ["light.room_2_light_1"],
                    "컴퓨터방": ["light.room_3_light_1"],
                    "서재": ["light.room_3_light_1"],
                    "끝방": ["light.room_4_light_1"],
                    "작은방": ["light.room_4_light_1"],
                    "세탁실": ["light.setagsil_jeondeungseuwici"],
                    "복도": ["light.room_1_light_4"],
                    "창가": ["light.room_1_light_3"]
                }
                targets = []
                for k, v in loc_map.items():
                    if k in location:
                        targets.extend(v)
                        break
                if not targets:
                    targets = ["light.room_1_light_1", "light.room_1_light_2"]
                    location = "거실"
                loc_name = location if location else "거실"

            service = "turn_off" if is_turn_off else "turn_on"
            for l_id in targets:
                await self.hass.services.async_call("light", service, {"entity_id": l_id}, blocking=True)

            action_str = "껐습니다" if is_turn_off else "켰습니다"
            msg = f"{loc_name} 조명을 {action_str}."

        except Exception as e:
            _LOGGER.error("Failed NUGU custom action execution: %s", e)
            msg = "조명 제어 중 오류가 발생했습니다."

        output_data["message"] = msg
        return web.json_response({"version": "2.0", "resultCode": "OK", "output": output_data})


# =====================================================================
# 2. 스마트홈 Pre-built (OAuth 2.0, Discovery, Control)
# =====================================================================
class NuguOAuthAuthorizeView(HomeAssistantView):
    """View to handle OAuth 2.0 Authorization code redirect for NUGU."""
    requires_auth = False

    def __init__(self, url: str) -> None:
        self.url = url
        self.name = f"nugu:oauth:authorize:{url}"

    async def get(self, request: web.Request) -> web.Response:
        _LOGGER.warning("NUGU OAuth Authorize query: %s", request.query)
        redirect_uri = request.query.get("redirect_uri", "")
        state = request.query.get("state", "")

        if not redirect_uri:
            return web.Response(status=400, text="Missing redirect_uri parameter")

        sep = "&" if "?" in redirect_uri else "?"
        callback_url = f"{redirect_uri}{sep}code=nugu_auth_code_2026&state={state}"
        _LOGGER.warning("Redirecting OAuth client (302 Found) to: %s", callback_url)
        raise web.HTTPFound(location=callback_url)


class NuguOAuthTokenView(HomeAssistantView):
    """View to issue OAuth 2.0 Bearer access tokens to NUGU."""
    requires_auth = False

    def __init__(self, url: str) -> None:
        self.url = url
        self.name = f"nugu:oauth:token:{url}"

    async def post(self, request: web.Request) -> web.Response:
        _LOGGER.warning("NUGU OAuth Token exchange request")
        return web.json_response({
            "access_token": "nugu_token_2026_lights",
            "token_type": "Bearer",
            "expires_in": 315360000,
            "refresh_token": "nugu_refresh_token_2026"
        })


class NuguDiscoveryView(HomeAssistantView):
    """View to handle NUGU Smart Home Device Discovery for Lights."""
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
        _LOGGER.warning("NUGU Discovery request on %s: %s", self.url, body)

        # 오직 조명(LIGHT) 도메인만 엄격히 조회 및 규격 일치화
        devices = []
        for state in self.hass.states.async_all("light"):
            name = state.name or state.entity_id
            devices.append({
                "id": state.entity_id.replace(".", "_"),
                "deviceTypeCode": "LIGHT",
                "deviceTypeName": "조명",
                "deviceModelName": "HomeAssistant",
                "type": "LIGHT",
                "model": "HomeAssistant",
                "modelName": "HomeAssistant",
                "friendlyName": name,
                "friendlyNameSuggestion": name,
                "manufacturer": "HomeAssistant",
                "supportedCapabilities": {
                    "powerControl": {}
                },
                "customData": {
                    "entity_id": state.entity_id,
                    "domain": "light"
                },
                "connectionStatus": state.state != "unavailable"
            })

        _LOGGER.warning("Discovered %d lights for NUGU SmartHome", len(devices))
        return web.json_response({"devices": devices})


class NuguControlView(HomeAssistantView):
    """View to handle NUGU Smart Home Control Directives (TurnOn, TurnOff)."""
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

        _LOGGER.warning("NUGU Control Request on %s: cap=%s, dir=%s, body=%s", self.url, capability, directive, data)

        req_id = data.get("requestId", "")
        action = data.get("action", {})
        command = action.get("command", {}) if isinstance(action, dict) else {}

        # Directive 추출 (URL 파라미터 우선, 그 후 body action.command)
        actual_directive = directive or command.get("smartHomeDirective", "")
        dir_lower = str(actual_directive).lower()
        is_off = any(w in dir_lower for w in ["turnoff", "off", "꺼", "소등", "stop", "close"])

        # 타겟 디바이스 목록 추출 (모든 공식/비공식 payload 위치 안전 파싱)
        target_devices = []
        if isinstance(action, dict) and "smartHomeDevices" in action:
            target_devices = action.get("smartHomeDevices") or []
        elif "smartHomeDevices" in data:
            target_devices = data.get("smartHomeDevices") or []
        elif "smartHomeDevice" in data:
            target_devices = [data["smartHomeDevice"]]
        elif "device" in data:
            target_devices = [data["device"]]

        # 만약 디바이스가 비어있는 경우(전체 제어 발화 등) 전체 조명 매핑
        if not target_devices:
            for s in self.hass.states.async_all("light"):
                target_devices.append({
                    "id": s.entity_id.replace(".", "_"),
                    "deviceTypeCode": "LIGHT",
                    "customData": {"entity_id": s.entity_id, "domain": "light"}
                })

        results = []
        for dev in target_devices:
            if not isinstance(dev, dict):
                continue

            custom = dev.get("customData", {})
            entity_id = custom.get("entity_id") or dev.get("id", "").replace("_", ".", 1)

            # 1. 기기 존재 확인
            current_state = self.hass.states.get(entity_id)
            if current_state is None:
                _LOGGER.warning("Device %s not found in Home Assistant", entity_id)
                results.append({
                    "resultCode": "NotExistDeviceInSmartHomeBackendProxy",
                    "smartHomeDevice": dev,
                    "errorProperties": {}
                })
                continue

            # 2. 연결 상태 확인
            if current_state.state == "unavailable":
                _LOGGER.warning("Device %s is unavailable", entity_id)
                results.append({
                    "resultCode": "NoConnectionDevice",
                    "smartHomeDevice": dev,
                    "errorProperties": {}
                })
                continue

            # 3. AlreadyTurnOn / AlreadyTurnOff 확인
            if not is_off and current_state.state == "on":
                _LOGGER.warning("Device %s is already turned on", entity_id)
                results.append({
                    "resultCode": "AlreadyTurnOn",
                    "smartHomeDevice": dev,
                    "errorProperties": {}
                })
                continue

            if is_off and current_state.state == "off":
                _LOGGER.warning("Device %s is already turned off", entity_id)
                results.append({
                    "resultCode": "AlreadyTurnOff",
                    "smartHomeDevice": dev,
                    "errorProperties": {}
                })
                continue

            # 4. 실제 제어 실행
            service = "turn_off" if is_off else "turn_on"
            try:
                _LOGGER.warning("Executing light.%s on %s", service, entity_id)
                await self.hass.services.async_call("light", service, {"entity_id": entity_id}, blocking=True)
                results.append({
                    "resultCode": "OK",
                    "smartHomeDevice": dev,
                    "properties": {
                        "power": "OFF" if is_off else "ON"
                    }
                })
            except Exception as e:
                _LOGGER.error("Failed to control light %s: %s", entity_id, e)
                results.append({
                    "resultCode": "NoConnectionDevice",
                    "smartHomeDevice": dev,
                    "errorProperties": {}
                })

        # NUGU Pre-built SmartHome 공식 응답 규격: 최상위에는 requestId와 data만 포함
        response_payload = {
            "requestId": req_id,
            "data": results
        }
        _LOGGER.warning("NUGU Control Response: %s", response_payload)
        return web.json_response(response_payload)


# =====================================================================
# 3. 헬스 체크
# =====================================================================
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
