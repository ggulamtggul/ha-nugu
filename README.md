# NUGU Smart Home for Home Assistant

SKT NUGU 인공지능 스피커(아리아)와 Home Assistant를 연동하는 HACS 커스텀 통합구성요소입니다.

## 기능
- NUGU Developers 스마트홈(SmartHome) Pre-built API 완벽 지원
- 인보케이션(호출어) 없이 자연스러운 음성 제어 지원 ("아리아, 거실 조명 켜줘", "아리아, 에어컨 켜줘")
- 조명(LIGHT), 에어컨(AIR_CONDITIONER), 난방(BOILER), 로봇청소기(ROBOT_CLEANER) 지원
- 간이 OAuth 2.0 자동 인증 페이지 내장
- Cloudflare Tunnel 등 외부 HTTPS 엔드포인트 바로 활용 가능

## 설치 방법 (HACS)
1. HACS > 통합구성요소(Integrations) 진입
2. 우측 상단 메뉴 > **사용자 지정 저장소 (Custom repositories)** 선택
3. 저장소 URL에 본 저장소 주소 입력, 범주는 **통합구성요소 (Integration)** 선택 후 추가
4. 목록에서 **NUGU Smart Home** 다운로드
5. Home Assistant 재시작
