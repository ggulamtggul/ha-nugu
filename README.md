# NUGU Smart Home (Lights) for Home Assistant

SKT NUGU 인공지능 스피커(아리아)와 Home Assistant를 연동하는 HACS 커스텀 통합구성요소입니다.  
NUGU Developers 스마트홈(SmartHome) Pre-built API 공식 규격 및 커스텀 플레이(Custom Play) 규격을 100% 준수하여 전등(조명)을 안정적으로 음성 제어합니다.

## 주요 기능
- **스마트홈 Pre-built 완벽 연동**: 호출어 없이 자연어 제어 ("아리아, 거실 조명 켜줘", "아리아, 침실 불 꺼줘")
- **공식 API 스키마 준수**:
  - `TurnOn` / `TurnOff` 표준 Directive 지원
  - `AlreadyTurnOn`, `AlreadyTurnOff`, `NoConnectionDevice`, `NotExistDeviceInSmartHomeBackendProxy` 등 NUGU 표준 에러 코드 지원 (음성 피드백 연동)
  - `properties` 전원 상태 동기화
  - RFC 6749 표준 HTTP 302 리다이렉트 기반 간이 OAuth 2.0 지원 (XSS 취약점 차단)
- **커스텀 플레이(Custom Play) 호환**: "우리집에서 거실 조명 켜줘"와 같은 백엔드 프록시 명령도 완벽 지원

## 설치 및 설정 방법
1. **HACS 설치**:
   - HACS > Integrations > 우측 상단 사용자 지정 저장소(Custom repositories)에 `ggulamtggul/ha-nugu` (통합구성요소) 추가
   - **NUGU Smart Home** 다운로드 후 Home Assistant 재시작
2. **NUGU Developers 스마트홈 Play 설정**:
   - Backend Proxy URL: `https://<YOUR_HA_DOMAIN>` (예: `https://ha.leocothr.co.kr`)
   - OAuth 인증 URL: `https://<YOUR_HA_DOMAIN>/nugu/oauth/authorize`
   - OAuth 토큰 URL: `https://<YOUR_HA_DOMAIN>/nugu/oauth/token`
3. **NUGU 모바일 앱 연동**:
   - NUGU 앱 > 스마트홈 디바이스 추가 > 계정 연동 및 디바이스 검색 완료
