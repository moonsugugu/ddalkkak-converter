# 외부 구성 요소

`FilePathCheckerModuleExample.dll`은 한컴이 공개한 한글 Automation 보안 모듈 예제를 수정 없이 사용합니다. SHA-256: `9ac5b97c47ac8aed1e8bca27a3eef39411361d8f68c262509f0c40a8f9d21bb6`.

- 공식 개발 안내: https://developer.hancom.com/en-us/hwpautomation
- 공식 예제 보관소: https://github.com/hancom-io/devcenter-archive/tree/main/hwp-automation

한글과 Office 자체는 재배포하지 않습니다. 한글 자동화의 이용 범위는 한컴의 안내와 해당 제품 사용권을 확인하세요. 이 예제 DLL은 앱 소스의 AGPL 라이선스로 재허가하지 않으며 원 제공자의 권리를 유지합니다.

`comgen/`은 설치된 한글의 타입 라이브러리를 pywin32 makepy로 생성한 COM 호출 래퍼입니다. `build_com.py`로 다시 생성합니다. `docq.ico`는 앱의 `icon_image()`로 만든 딸깍변환 아이콘입니다.
