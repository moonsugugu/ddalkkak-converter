# -*- coding: utf-8 -*-
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "nsDialogs.nsh"
!include "WordFunc.nsh"
!include "x64.nsh"
!ifndef VERSION
!define VERSION "3.1.0"
!endif
!ifndef PAYLOAD
!define PAYLOAD "dist"
!endif
!ifndef OUTPUT
!define OUTPUT "dist\DdalKkak-Setup-${VERSION}.exe"
!endif
!define PRODUCT "딸깍변환"
!define APPKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Moonsunezip.DocQ"
Name "${PRODUCT}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\DocQ"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 8
BrandingText "문수네집 · moonsunezip.com"
Icon "vendor\docq.ico"
UninstallIcon "vendor\docq.ico"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${PRODUCT}"
VIAddVersionKey "FileDescription" "딸깍변환 설치 프로그램"
VIAddVersionKey "CompanyName" "문수네집"
VIAddVersionKey "LegalCopyright" "문수네집"
VIAddVersionKey "FileVersion" "${VERSION}"
!define MUI_ICON "vendor\docq.ico"
!define MUI_UNICON "vendor\docq.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "파일 선택 → F12 → 형식 클릭$\r$\n$\r$\n창 없이 트레이에서 대기하는 파일 변환 도구입니다.$\r$\n원본 파일과 이전 변환 결과는 보존합니다.$\r$\n$\r$\n사용자 계정에 설치하며 관리자 권한이 필요하지 않습니다."
!insertmacro MUI_PAGE_WELCOME
Page custom MaintenancePage MaintenanceLeave
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\DdalKkak.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS "--background"
!define MUI_FINISHPAGE_RUN_TEXT "딸깍변환을 트레이에서 실행"
!define MUI_FINISHPAGE_TEXT "바탕 화면이나 탐색기에서 파일을 선택하고 F12를 누르세요.$\r$\n$\r$\n휠과 좌우 화살표로 원형 메뉴를 넘길 수 있습니다.$\r$\n설정·업데이트·종료는 트레이 우클릭 메뉴에 있습니다."
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "Korean"
Var Existing
Var RepairRadio
Var RemoveRadio
Var Startup
Var SetupLock
Var OwnsSetupLock
Var MainCommitted
Var IconCommitted
Var ReadmeCommitted
Var NoticesCommitted
Var FfmpegCommitted
Var ProbeCommitted
Var LicenseCommitted
Var SourceCommitted
Var UninstallCommitted

!macro CommitFile FILE FLAG
    ClearErrors
    IfFileExists "${FILE}" 0 +2
    Rename "${FILE}" "${FILE}.previous"
    IfErrors rollback
    Rename "${FILE}.new" "${FILE}"
    IfErrors rollback
    StrCpy ${FLAG} 1
!macroend

!macro RestoreFile FILE FLAG
    ${If} ${FileExists} "${FILE}.previous"
        Delete "${FILE}"
        Rename "${FILE}.previous" "${FILE}"
    ${ElseIf} ${FLAG} == 1
        Delete "${FILE}"
    ${EndIf}
!macroend

!macro CleanPrevious FILE
    Delete "${FILE}.previous"
    IfFileExists "${FILE}.previous" failed
!macroend

Function .onInit
    SetShellVarContext current
    ${IfNot} ${RunningX64}
        MessageBox MB_OK|MB_ICONSTOP "이 설치본은 Windows 10/11 64비트용입니다." /SD IDOK
        SetErrorLevel 1633
        Abort
    ${EndIf}
    ${If} ${RunningX64}
        SetRegView 64
    ${EndIf}
    System::Call 'kernel32::CreateMutexW(p0,i0,w "Local\Moonsunezip.DocQ.Setup") p.r0 ?e'
    StrCpy $SetupLock $0
    Pop $1
    ${If} $1 == 183
        MessageBox MB_OK|MB_ICONEXCLAMATION "다른 딸깍변환 설치·제거 작업이 진행 중입니다." /SD IDOK
        SetErrorLevel 1618
        Abort
    ${EndIf}
    StrCpy $OwnsSetupLock 1
    ReadRegStr $Existing HKCU "${APPKEY}" "DisplayVersion"
    ${If} $Existing != ""
        ReadRegStr $INSTDIR HKCU "${APPKEY}" "InstallLocation"
        ${VersionCompare} $Existing "${VERSION}" $0
        ${If} $0 == 1
            MessageBox MB_OK|MB_ICONEXCLAMATION "이미 더 최신 버전 $Existing 이 설치되어 있습니다.$\r$\n구버전 ${VERSION}으로 덮어쓰지 않았습니다." /SD IDOK
            SetErrorLevel 1638
            Abort
        ${EndIf}
    ${EndIf}
    StrCpy $Startup 1
    IfFileExists "$INSTDIR\DocQ.exe" old_installed check_registered
    old_installed:
        IfFileExists "$SMSTARTUP\문서큐.lnk" check_registered 0
        StrCpy $Startup 0
    check_registered:
    ${If} $Existing != ""
        StrCpy $Startup 0
        IfFileExists "$SMSTARTUP\딸깍변환.lnk" 0 +2
        StrCpy $Startup 1
    ${EndIf}
FunctionEnd

Function MaintenancePage
    ${If} $Existing == ""
        Abort
    ${EndIf}
    !insertmacro MUI_HEADER_TEXT "기존 설치 관리" "현재 $Existing / 설치파일 ${VERSION}"
    nsDialogs::Create 1018
    Pop $0
    ${NSD_CreateLabel} 0 0 100% 36u "설정·즐겨찾기·변환 파일은 보존합니다.$\r$\n앱을 삭제해도 사용자 파일을 지우지 않습니다."
    Pop $0
    ${NSD_CreateRadioButton} 0 55u 100% 20u "다시 설치 / 복구 (이전 버전이면 업데이트)"
    Pop $RepairRadio
    ${NSD_Check} $RepairRadio
    ${NSD_CreateRadioButton} 0 85u 100% 20u "딸깍변환 제거"
    Pop $RemoveRadio
    ${NSD_OnClick} $RepairRadio MaintenanceSelection
    ${NSD_OnClick} $RemoveRadio MaintenanceSelection
    Push $RepairRadio
    Call MaintenanceSelection
    nsDialogs::Show
FunctionEnd

Function MaintenanceSelection
    Pop $0
    ${NSD_GetState} $RemoveRadio $0
    GetDlgItem $1 $HWNDPARENT 1
    ${If} $0 == ${BST_CHECKED}
        SendMessage $1 ${WM_SETTEXT} 0 "STR:제거"
    ${ElseIf} $Existing == "${VERSION}"
        SendMessage $1 ${WM_SETTEXT} 0 "STR:복구"
    ${Else}
        SendMessage $1 ${WM_SETTEXT} 0 "STR:업데이트"
    ${EndIf}
FunctionEnd

Function MaintenanceLeave
    ${NSD_GetState} $RemoveRadio $0
    ${If} $0 == ${BST_CHECKED}
        StrCpy $OwnsSetupLock 0
        System::Call 'kernel32::CloseHandle(p $SetupLock)'
        Exec '"$INSTDIR\Uninstall.exe"'
        Quit
    ${EndIf}
FunctionEnd

Function .onGUIEnd
    ${If} $OwnsSetupLock == 1
        Delete "$INSTDIR\DdalKkak.exe.new"
        Delete "$INSTDIR\app.ico.new"
        Delete "$INSTDIR\사용방법.md.new"
        Delete "$INSTDIR\LICENSES.txt.new"
        Delete "$INSTDIR\tools\ffmpeg.exe.new"
        Delete "$INSTDIR\tools\ffprobe.exe.new"
        Delete "$INSTDIR\tools\FFmpeg-LICENSE.txt.new"
        Delete "$INSTDIR\tools\FFmpeg-SOURCE.txt.new"
        Delete "$INSTDIR\Uninstall.exe.new"
    ${EndIf}
FunctionEnd

!macro StopApp PREFIX
Function ${PREFIX}StopApp
    System::Call 'kernel32::OpenEventW(i0x100000,i0,w "Local\Moonsunezip.DocQ.Busy") p.r0'
    ${If} $0 != 0
        System::Call 'kernel32::WaitForSingleObject(p r0,i0) i.r1'
        System::Call 'kernel32::CloseHandle(p r0)'
        ${If} $1 == 0
            MessageBox MB_OK|MB_ICONEXCLAMATION "파일을 변환 중입니다. 변환이 끝난 뒤 다시 실행하세요.$\r$\n설치·제거 작업을 시작하지 않았습니다." /SD IDOK
            SetErrorLevel 1618
            Abort
        ${EndIf}
    ${EndIf}
    System::Call 'kernel32::OpenEventW(i0x0002,i0,w "Local\Moonsunezip.DocQ.Close") p.r0'
    ${If} $0 != 0
        System::Call 'kernel32::SetEvent(p r0)'
        System::Call 'kernel32::CloseHandle(p r0)'
    ${EndIf}
    StrCpy $2 0
    ${Do}
        System::Call 'kernel32::OpenMutexW(i0x100000,i0,w "Local\Moonsunezip.DocQ") p.r0'
        ${If} $0 == 0
            Sleep 500
            Return
        ${EndIf}
        System::Call 'kernel32::CloseHandle(p r0)'
        Sleep 250
        IntOp $2 $2 + 1
    ${LoopUntil} $2 >= 120
    MessageBox MB_OK|MB_ICONEXCLAMATION "앱이 아직 종료 중입니다. 현재 작업을 마친 뒤 다시 실행하세요.$\r$\n기존 앱과 파일은 유지됩니다." /SD IDOK
    SetErrorLevel 1618
    Abort
FunctionEnd
!macroend
!insertmacro StopApp ""
!insertmacro StopApp "un."

Section "딸깍변환"
    Call StopApp
    SetOutPath "$INSTDIR"
    ClearErrors
    File /oname=DdalKkak.exe.new "${PAYLOAD}\DdalKkak.exe"
    File /oname=app.ico.new "vendor\docq.ico"
    File /oname=사용방법.md.new "README.md"
    File /oname=LICENSES.txt.new "${PAYLOAD}\LICENSES.txt"
    SetOutPath "$INSTDIR\tools"
    File /oname=ffmpeg.exe.new "${PAYLOAD}\tools\ffmpeg.exe"
    File /oname=ffprobe.exe.new "${PAYLOAD}\tools\ffprobe.exe"
    File /oname=FFmpeg-LICENSE.txt.new "${PAYLOAD}\tools\FFmpeg-LICENSE.txt"
    File /oname=FFmpeg-SOURCE.txt.new "${PAYLOAD}\tools\FFmpeg-SOURCE.txt"
    IfErrors failed
    WriteUninstaller "$INSTDIR\Uninstall.exe.new"
    IfErrors failed
    !insertmacro CleanPrevious "$INSTDIR\DdalKkak.exe"
    !insertmacro CleanPrevious "$INSTDIR\app.ico"
    !insertmacro CleanPrevious "$INSTDIR\사용방법.md"
    !insertmacro CleanPrevious "$INSTDIR\LICENSES.txt"
    !insertmacro CleanPrevious "$INSTDIR\tools\ffmpeg.exe"
    !insertmacro CleanPrevious "$INSTDIR\tools\ffprobe.exe"
    !insertmacro CleanPrevious "$INSTDIR\tools\FFmpeg-LICENSE.txt"
    !insertmacro CleanPrevious "$INSTDIR\tools\FFmpeg-SOURCE.txt"
    !insertmacro CleanPrevious "$INSTDIR\Uninstall.exe"
    !insertmacro CommitFile "$INSTDIR\DdalKkak.exe" $MainCommitted
    !insertmacro CommitFile "$INSTDIR\app.ico" $IconCommitted
    !insertmacro CommitFile "$INSTDIR\사용방법.md" $ReadmeCommitted
    !insertmacro CommitFile "$INSTDIR\LICENSES.txt" $NoticesCommitted
    !insertmacro CommitFile "$INSTDIR\tools\ffmpeg.exe" $FfmpegCommitted
    !insertmacro CommitFile "$INSTDIR\tools\ffprobe.exe" $ProbeCommitted
    !insertmacro CommitFile "$INSTDIR\tools\FFmpeg-LICENSE.txt" $LicenseCommitted
    !insertmacro CommitFile "$INSTDIR\tools\FFmpeg-SOURCE.txt" $SourceCommitted
    !insertmacro CommitFile "$INSTDIR\Uninstall.exe" $UninstallCommitted
    WriteRegStr HKCU "${APPKEY}" "DisplayName" "딸깍변환"
    WriteRegStr HKCU "${APPKEY}" "Publisher" "문수네집"
    WriteRegStr HKCU "${APPKEY}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKCU "${APPKEY}" "DisplayIcon" "$INSTDIR\DdalKkak.exe,0"
    WriteRegStr HKCU "${APPKEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${APPKEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
    WriteRegStr HKCU "${APPKEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
    WriteRegStr HKCU "${APPKEY}" "URLInfoAbout" "https://moonsunezip.com"
    WriteRegStr HKCU "${APPKEY}" "AppId" "com.moonsunezip.docq"
    WriteRegDWORD HKCU "${APPKEY}" "NoModify" 1
    WriteRegDWORD HKCU "${APPKEY}" "NoRepair" 1
    WriteRegDWORD HKCU "${APPKEY}" "EstimatedSize" 520000
    CreateDirectory "$SMPROGRAMS\딸깍변환"
    CreateShortcut "$DESKTOP\딸깍변환.lnk" "$INSTDIR\DdalKkak.exe" "--background" "$INSTDIR\app.ico" 0 SW_SHOWNORMAL "" "파일 선택 후 F12 · 문수네집"
    CreateShortcut "$SMPROGRAMS\딸깍변환\딸깍변환.lnk" "$INSTDIR\DdalKkak.exe" "--background" "$INSTDIR\app.ico"
    CreateShortcut "$SMPROGRAMS\딸깍변환\딸깍변환 제거.lnk" "$INSTDIR\Uninstall.exe" "" "$INSTDIR\app.ico"
    ${If} $Startup == 1
        CreateShortcut "$SMSTARTUP\딸깍변환.lnk" "$INSTDIR\DdalKkak.exe" "--background" "$INSTDIR\app.ico"
    ${EndIf}
    Delete "$DESKTOP\문서큐.lnk"
    Delete "$SMSTARTUP\문서큐.lnk"
    Delete "$INSTDIR\DocQ.exe"
    Delete "$INSTDIR\DdalKkak.exe.previous"
    Delete "$INSTDIR\app.ico.previous"
    Delete "$INSTDIR\사용방법.md.previous"
    Delete "$INSTDIR\LICENSES.txt.previous"
    Delete "$INSTDIR\tools\ffmpeg.exe.previous"
    Delete "$INSTDIR\tools\ffprobe.exe.previous"
    Delete "$INSTDIR\tools\FFmpeg-LICENSE.txt.previous"
    Delete "$INSTDIR\tools\FFmpeg-SOURCE.txt.previous"
    Delete "$INSTDIR\Uninstall.exe.previous"
    SetErrorLevel 0
    Goto finished
    rollback:
        !insertmacro RestoreFile "$INSTDIR\DdalKkak.exe" $MainCommitted
        !insertmacro RestoreFile "$INSTDIR\app.ico" $IconCommitted
        !insertmacro RestoreFile "$INSTDIR\사용방법.md" $ReadmeCommitted
        !insertmacro RestoreFile "$INSTDIR\LICENSES.txt" $NoticesCommitted
        !insertmacro RestoreFile "$INSTDIR\tools\ffmpeg.exe" $FfmpegCommitted
        !insertmacro RestoreFile "$INSTDIR\tools\ffprobe.exe" $ProbeCommitted
        !insertmacro RestoreFile "$INSTDIR\tools\FFmpeg-LICENSE.txt" $LicenseCommitted
        !insertmacro RestoreFile "$INSTDIR\tools\FFmpeg-SOURCE.txt" $SourceCommitted
        !insertmacro RestoreFile "$INSTDIR\Uninstall.exe" $UninstallCommitted
    failed:
        Delete "$INSTDIR\DdalKkak.exe.new"
        Delete "$INSTDIR\app.ico.new"
        Delete "$INSTDIR\사용방법.md.new"
        Delete "$INSTDIR\LICENSES.txt.new"
        Delete "$INSTDIR\tools\ffmpeg.exe.new"
        Delete "$INSTDIR\tools\ffprobe.exe.new"
        Delete "$INSTDIR\tools\FFmpeg-LICENSE.txt.new"
        Delete "$INSTDIR\tools\FFmpeg-SOURCE.txt.new"
        Delete "$INSTDIR\Uninstall.exe.new"
        MessageBox MB_OK|MB_ICONSTOP "설치에 실패했습니다. 저장 공간·파일 잠금을 확인한 뒤 설치파일을 다시 실행하세요.$\r$\n기존 사용자 설정과 변환 파일은 보존됩니다." /SD IDOK
        SetErrorLevel 1603
        Abort
    finished:
SectionEnd

Function un.onInit
    SetShellVarContext current
    ${If} ${RunningX64}
        SetRegView 64
    ${EndIf}
    ReadRegStr $0 HKCU "${APPKEY}" "InstallLocation"
    ${If} $0 != $INSTDIR
        MessageBox MB_OK|MB_ICONSTOP "등록된 설치 위치와 달라 제거를 시작할 수 없습니다." /SD IDOK
        SetErrorLevel 1603
        Abort
    ${EndIf}
    System::Call 'kernel32::CreateMutexW(p0,i0,w "Local\Moonsunezip.DocQ.Setup") p.r0 ?e'
    Pop $1
    ${If} $1 == 183
        MessageBox MB_OK|MB_ICONEXCLAMATION "다른 설치·제거 작업이 진행 중입니다." /SD IDOK
        SetErrorLevel 1618
        Abort
    ${EndIf}
FunctionEnd

Section "Uninstall"
    Call un.StopApp
    ClearErrors
    Delete "$INSTDIR\DdalKkak.exe"
    IfFileExists "$INSTDIR\DdalKkak.exe" 0 +4
        MessageBox MB_OK|MB_ICONSTOP "앱 파일이 사용 중입니다. 잠시 후 제거를 다시 실행하세요." /SD IDOK
        SetErrorLevel 1603
        Abort
    Delete "$DESKTOP\딸깍변환.lnk"
    Delete "$DESKTOP\문서큐.lnk"
    Delete "$SMSTARTUP\딸깍변환.lnk"
    Delete "$SMSTARTUP\문서큐.lnk"
    Delete "$SMPROGRAMS\딸깍변환\딸깍변환.lnk"
    Delete "$SMPROGRAMS\딸깍변환\딸깍변환 제거.lnk"
    RMDir "$SMPROGRAMS\딸깍변환"
    Delete "$INSTDIR\DdalKkak.exe"
    Delete "$INSTDIR\DocQ.exe"
    Delete "$INSTDIR\app.ico"
    Delete "$INSTDIR\사용방법.md"
    Delete "$INSTDIR\LICENSES.txt"
    Delete "$INSTDIR\tools\ffmpeg.exe"
    Delete "$INSTDIR\tools\ffprobe.exe"
    Delete "$INSTDIR\tools\FFmpeg-LICENSE.txt"
    Delete "$INSTDIR\tools\FFmpeg-SOURCE.txt"
    Delete "$INSTDIR\DdalKkak.exe.new"
    Delete "$INSTDIR\app.ico.new"
    Delete "$INSTDIR\사용방법.md.new"
    Delete "$INSTDIR\LICENSES.txt.new"
    Delete "$INSTDIR\tools\ffmpeg.exe.new"
    Delete "$INSTDIR\tools\ffprobe.exe.new"
    Delete "$INSTDIR\tools\FFmpeg-LICENSE.txt.new"
    Delete "$INSTDIR\tools\FFmpeg-SOURCE.txt.new"
    Delete "$INSTDIR\Uninstall.exe.new"
    RMDir "$INSTDIR\tools"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"
    DeleteRegKey HKCU "${APPKEY}"
    DeleteRegValue HKCU "Software\HNC\HwpAutomation\Modules" "DocQ.FilePathChecker"
    SetErrorLevel 0
SectionEnd
