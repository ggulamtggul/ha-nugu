"""NUGU Smart Home & Custom Play Unified Integration for Home Assistant."""
import logging
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the NUGU integration with both SmartHome and Custom Play support."""
    _LOGGER.info("Setting up NUGU Unified Integration v1.6.0")

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


class NuguActionView(HomeAssistantView):
    """View to handle Custom Play (일반 커스텀 플레이) requests from NUGU."""
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
        actual_action_name = action.get("actionName", action_name)
        params = action.get("parameters", {})

        # 파라미터 값 추출
        extracted = {}
        for k, v in params.items():
            if isinstance(v, dict):
                extracted[k] = v.get("value", "")
            else:
                extracted[k] = str(v)

        location = extracted.get("location", "").strip()
        device_type = extracted.get("device", "").strip()
        action_type = extracted.get("action_type", "").strip()
        temp_val = extracted.get("temperature", "").strip()

        combined_text = f"{location} {device_type} {action_type}"

        # 켜기/끄기 판별
        is_turn_off = any(w in combined_text for w in ["꺼", "끄", "중지", "종료", "멈춰", "off", "정지", "소등"])
        is_turn_on = any(w in combined_text for w in ["켜", "틀", "시작", "작동", "돌려", "on", "점등"]) or not is_turn_off

        # 전체 일괄 제어 여부 판별
        is_all = any(w in combined_text for w in ["다", "전체", "모두", "전부", "모든", "집안", "일괄"])

        msg = "명령을 수행했습니다."
        output_data = {k: v for k, v in extracted.items()}

        try:
            # 0. 외출 모드
            if any(w in combined_text for w in ["외출", "외출모드", "외출 모드"]):
                for s in self.hass.states.async_all("light"):
                    await self.hass.services.async_call("light", "turn_off", {"entity_id": s.entity_id}, blocking=True)
                for s in self.hass.states.async_all("climate"):
                    if "aircon" in s.entity_id:
                        await self.hass.services.async_call("climate", "turn_off", {"entity_id": s.entity_id}, blocking=True)
                msg = "외출 모드를 실행하여 집안 전체 조명과 에어컨을 모두 껐습니다."

            # 1. 로봇청소기
            elif any(w in device_type for w in ["청소기", "로봇", "로보킹"]):
                if is_turn_off:
                    await self.hass.services.async_call("vacuum", "return_to_base", {}, blocking=True)
                    msg = "로봇청소기를 충전대로 보냈습니다."
                else:
                    await self.hass.services.async_call("vacuum", "start", {}, blocking=True)
                    msg = "로봇청소기를 시작했습니다."

            # 2. 에어컨
            elif any(w in device_type for w in ["에어컨", "냉방"]):
                target_climates = []
                for s in self.hass.states.async_all("climate"):
                    if "aircon" in s.entity_id or "에어컨" in (s.name or ""):
                        if is_all or not location or location in (s.name or "") or location in s.entity_id:
                            target_climates.append(s.entity_id)

                if not target_climates:
                    target_climates = ["climate.lg_system_aircon_livingroom"]

                for c_id in target_climates:
                    if temp_val:
                        try:
                            t_num = float(''.join(filter(lambda x: x.isdigit() or x == '.', temp_val)))
                            await self.hass.services.async_call("climate", "set_temperature", {"entity_id": c_id, "temperature": t_num}, blocking=True)
                            msg = f"에어컨 온도를 {int(t_num)}도로 맞췄습니다."
                        except Exception:
                            pass
                    elif is_turn_off:
                        await self.hass.services.async_call("climate", "turn_off", {"entity_id": c_id}, blocking=True)
                        msg = "모든 에어컨을 껐습니다." if is_all else "에어컨을 껐습니다."
                    else:
                        await self.hass.services.async_call("climate", "turn_on", {"entity_id": c_id}, blocking=True)
                        msg = "모든 에어컨을 켰습니다." if is_all else "에어컨을 켰습니다."

            # 3. 난방 / 보일러
            elif any(w in device_type for w in ["난방", "보일러"]):
                target_heaters = []
                for s in self.hass.states.async_all("climate"):
                    if "heater" in s.entity_id or "난방" in (s.name or ""):
                        if is_all or not location or location in (s.name or ""):
                            target_heaters.append(s.entity_id)

                if not target_heaters:
                    target_heaters = ["climate.room_heater_1_0"]

                for h_id in target_heaters:
                    if is_turn_off:
                        await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": h_id, "hvac_mode": "off"}, blocking=True)
                        msg = "모든 난방을 껐습니다." if is_all else "난방을 껐습니다."
                    else:
                        await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": h_id, "hvac_mode": "heat"}, blocking=True)
                        msg = "모든 난방을 켰습니다." if is_all else "난방을 켰습니다."

            # 4. 조명
            else:
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
            msg = "장치 제어 중 오류가 발생했습니다."

        output_data["message"] = msg
        return web.json_response({"version": "2.0", "resultCode": "OK", "output": output_data})


# --- 2. 스마트홈 Pre-built 뷰 ---
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
            name = state.name or state.entity_id
            devices.append({
                "id": state.entity_id.replace(".", "_"),
                "type": "LIGHT",
                "deviceTypeCode": "LIGHT",
                "deviceTypeName": "조명",
                "model": "HA",
                "modelName": "HA",
                "deviceModelName": "HA",
                "friendlyName": name,
                "friendlyNameSuggestion": name,
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
                results.append({
                    "resultCode": "OK",
                    "smartHomeDevice": dev,
                    "properties": {"power": "OFF" if is_off else "ON"}
                })
            except Exception as e:
                _LOGGER.error("Failed to control %s: %s", entity_id, e)
                results.append({"resultCode": "DeviceControlFailed", "smartHomeDevice": dev})

        if not results:
            results = [{"resultCode": "OK"}]

        resp = {
            "resultCode": "OK",
            "requestId": req_id,
            "parameters": {},
            "data": results
        }
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
