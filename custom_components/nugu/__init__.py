"""NUGU Smart Home & Custom Play Integration for Home Assistant."""
import logging
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the NUGU integration."""
    _LOGGER.info("Setting up NUGU Integration")

    views = [
        # Custom Play (일반 Play) Backend Proxy 엔드포인트 (모든 URL 패턴 대응)
        NuguActionView(hass, "/nugu/action"),
        NuguActionView(hass, "/nugu/action/{action_name}"),
        NuguActionView(hass, "/nugu/{action_name}"),
        NuguActionView(hass, "/{action_name}"),

        # Smart Home Pre-built 호환 엔드포인트
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


class NuguActionView(HomeAssistantView):
    """View to handle Custom Play (일반 Play) requests from NUGU."""
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

        _LOGGER.info("NUGU Action Request on %s: %s", self.url, data)
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

        _LOGGER.info("Extracted -> location: '%s', device: '%s', action: '%s', temp: '%s'",
                     location, device_type, action_type, temp_val)

        # 켜기/끄기 판별
        is_turn_off = any(w in action_type for w in ["꺼", "끄", "중지", "종료", "멈춰", "off", "정지"])
        is_turn_on = any(w in action_type for w in ["켜", "틀", "시작", "작동", "돌려", "on"]) or not is_turn_off

        # 응답 메시지 초기화
        msg = "명령을 수행했습니다."
        output_data = {k: v for k, v in extracted.items()}

        try:
            # 1. 로봇청소기
            if any(w in device_type for w in ["청소기", "로봇", "로보킹"]):
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
                        if not location or location in (s.name or "") or location in s.entity_id:
                            target_climates.append(s.entity_id)

                if not target_climates:
                    target_climates = ["climate.lg_system_aircon_livingroom"]

                for c_id in target_climates:
                    if temp_val:
                        try:
                            t_num = float(''.join(filter(lambda x: x.isdigit() or x=='.', temp_val)))
                            await self.hass.services.async_call("climate", "set_temperature", {"entity_id": c_id, "temperature": t_num}, blocking=True)
                            msg = f"에어컨 온도를 {int(t_num)}도로 맞췄습니다."
                        except Exception:
                            pass
                    elif is_turn_off:
                        await self.hass.services.async_call("climate", "turn_off", {"entity_id": c_id}, blocking=True)
                        msg = "에어컨을 껐습니다."
                    else:
                        await self.hass.services.async_call("climate", "turn_on", {"entity_id": c_id}, blocking=True)
                        msg = "에어컨을 켰습니다."

            # 3. 난방 / 보일러
            elif any(w in device_type for w in ["난방", "보일러"]):
                target_heaters = []
                for s in self.hass.states.async_all("climate"):
                    if "heater" in s.entity_id or "난방" in (s.name or ""):
                        if not location or location in (s.name or ""):
                            target_heaters.append(s.entity_id)

                if not target_heaters:
                    target_heaters = ["climate.room_heater_1_0"]

                for h_id in target_heaters:
                    if is_turn_off:
                        await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": h_id, "hvac_mode": "off"}, blocking=True)
                        msg = "난방을 껐습니다."
                    else:
                        await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": h_id, "hvac_mode": "heat"}, blocking=True)
                        msg = "난방을 켰습니다."

            # 4. 조명 (기본값)
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
                    if "전체" in location or "모두" in location or "다" in location:
                        targets = [s.entity_id for s in self.hass.states.async_all("light")]
                        location = "집안 전체"
                    else:
                        targets = ["light.room_1_light_1", "light.room_1_light_2"]
                        location = "거실"

                service = "turn_off" if is_turn_off else "turn_on"
                loc_name = location if location else "거실"
                for l_id in targets:
                    await self.hass.services.async_call("light", service, {"entity_id": l_id}, blocking=True)
                
                action_str = "껐습니다" if is_turn_off else "켰습니다"
                msg = f"{loc_name} 조명을 {action_str}."

        except Exception as e:
            _LOGGER.error("Failed NUGU action execution: %s", e)
            msg = "장치 제어 중 오류가 발생했습니다."

        output_data["message"] = msg

        response_body = {
            "version": "2.0",
            "resultCode": "OK",
            "output": output_data
        }
        _LOGGER.info("NUGU Action Response: %s", response_body)
        return web.json_response(response_body)


# --- 이하 스마트홈 호환 뷰 ---
class NuguOAuthAuthorizeView(HomeAssistantView):
    url = "/nugu/oauth/authorize"
    name = "nugu:oauth:authorize"
    requires_auth = False
    async def get(self, request: web.Request) -> web.Response:
        redirect_uri = request.query.get("redirect_uri", "")
        state = request.query.get("state", "")
        callback_url = f"{redirect_uri}?code=nugu_success_code&state={state}"
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><script>window.location.href="{callback_url}";</script></head><body><p>연동 완료</p></body></html>"""
        return web.Response(text=html, content_type="text/html")

class NuguOAuthTokenView(HomeAssistantView):
    url = "/nugu/oauth/token"
    name = "nugu:oauth:token"
    requires_auth = False
    async def post(self, request: web.Request) -> web.Response:
        return web.json_response({"access_token": "ha_nugu_token_2026", "token_type": "Bearer", "expires_in": 315360000, "refresh_token": "ha_nugu_refresh_token_2026"})

class NuguDiscoveryView(HomeAssistantView):
    requires_auth = False
    def __init__(self, hass: HomeAssistant, url: str) -> None:
        self.hass = hass
        self.url = url
        self.name = f"nugu:discovery:{url}"
    async def post(self, request: web.Request) -> web.Response:
        devices = []
        for state in self.hass.states.async_all("light"):
            devices.append({"id": state.entity_id.replace(".", "_"), "deviceTypeCode": "LIGHT", "deviceTypeName": "조명", "deviceModelName": "HA", "friendlyNameSuggestion": state.name or state.entity_id, "manufacturer": "HA", "supportedCapabilities": {"powerControl": {}}, "customData": {"entity_id": state.entity_id, "domain": "light"}, "connectionStatus": state.state != "unavailable"})
        return web.json_response({"devices": devices})

class NuguControlView(HomeAssistantView):
    requires_auth = False
    def __init__(self, hass: HomeAssistant, url: str) -> None:
        self.hass = hass
        self.url = url
        self.name = f"nugu:control:{url}"
    async def post(self, request: web.Request, capability: str, directive: str) -> web.Response:
        data = await request.json()
        req_id = data.get("requestId", "")
        device = data.get("device", {})
        entity_id = device.get("customData", {}).get("entity_id") or device.get("id", "").replace("_", ".", 1)
        domain = device.get("customData", {}).get("domain") or entity_id.split(".")[0]
        service = "turn_on" if directive == "TurnOn" else "turn_off"
        await self.hass.services.async_call(domain, service, {"entity_id": entity_id}, blocking=True)
        return web.json_response({"requestId": req_id, "data": [{"resultCode": "OK", "smartHomeDevice": device}]})

class NuguHealthView(HomeAssistantView):
    requires_auth = False
    def __init__(self, url: str) -> None:
        self.url = url
        self.name = f"nugu:health:{url}"
    async def get(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "UP"})
    async def post(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "UP"})
