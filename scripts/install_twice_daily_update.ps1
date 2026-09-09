# 정부지원사업 자동 업데이트 예약 작업 설치
# 이 파일을 한 번 실행하면 매일 09:30과 15:30에 자동 업데이트가 실행됩니다.

$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $projectRoot "scripts\update_all_sources.py"
$pythonPath = (Get-Command python.exe -ErrorAction Stop).Path

# Windows 작업 스케줄러 명령줄의 따옴표 해석 차이를 피하기 위해
# schtasks.exe 대신 PowerShell의 예약 작업 기능을 사용한다.
$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument ('"' + $runner + '"') `
    -WorkingDirectory $projectRoot

$morning = New-ScheduledTaskTrigger -Daily -At "09:30"
$afternoon = New-ScheduledTaskTrigger -Daily -At "15:30"

Register-ScheduledTask `
    -TaskName "Government Funding App Update 0930" `
    -Action $action `
    -Trigger $morning `
    -Description "정부지원사업 자료를 매일 오전 9시 30분에 업데이트합니다." `
    -Force | Out-Null

Register-ScheduledTask `
    -TaskName "Government Funding App Update 1530" `
    -Action $action `
    -Trigger $afternoon `
    -Description "정부지원사업 자료를 매일 오후 3시 30분에 업데이트합니다." `
    -Force | Out-Null

Write-Output "자동 업데이트 예약 작업이 등록되었습니다."
Write-Output "실행 시간: 매일 09:30, 15:30"
Write-Output "업데이트 로그: $projectRoot\collector\logs"
