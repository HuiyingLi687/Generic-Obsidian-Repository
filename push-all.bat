@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
set "REPO=%~dp0"

echo ============================================================
echo   Obsidian Vault  一键提交并推送
echo   %REPO%
echo ============================================================
echo.

rem ==================== 1. 环境检查 ====================
where git >nul 2>&1
if errorlevel 1 (
    echo [X] 未检测到 git 命令
    echo     请先安装 Git for Windows: https://git-scm.com/download/win
    goto :FAIL
)

git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    echo [X] 当前目录不是 Git 仓库
    goto :FAIL
)

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%b"
if not defined BRANCH (
    echo [X] 无法识别当前分支，仓库可能尚未初始化
    goto :FAIL
)
set "URL=(未配置)"
for /f "delims=" %%r in ('git remote get-url origin 2^>nul') do set "URL=%%r"

echo [i] 分支 : !BRANCH!
echo [i] 远端 : !URL!
echo.

rem ==================== 2. 暂存并提交 ====================
git add -A
git diff --cached --quiet
if errorlevel 1 (
    set "MSG=%~1"
    if "!MSG!"=="" (
        set "T=%TIME:~0,5%"
        set "T=!T: =0!"
        set "MSG=sync: %DATE:~0,10% !T!"
    )
    echo [i] 提交信息 : !MSG!
    git commit -m "!MSG!" >nul
    if errorlevel 1 (
        echo [X] 提交失败，请检查上方 git 报错
        goto :FAIL
    )
    echo [v] 已创建提交
) else (
    echo [i] 工作区无新改动，跳过提交
)

rem ==================== 3. 推送（失败自动同步重试） ====================
echo.
set /a TRY=0
:RETRY
set /a TRY+=1
echo [i] 推送中... ^(第 !TRY! 次^)
git push -u origin !BRANCH!
if not errorlevel 1 goto :OK
if !TRY! geq 3 goto :FAIL

echo.
echo [!] 推送失败，先同步远端再重试...
git pull --rebase origin !BRANCH!
if errorlevel 1 (
    echo.
    echo [X] 与远端存在冲突，自动合并已中止
    echo     请手动处理后重新运行本脚本：
    echo       git status
    echo       git rebase --continue    ^(继续^)
    echo       git rebase --abort       ^(放弃^)
    goto :FAIL
)
echo [v] 已同步远端
ping -n 3 127.0.0.1 >nul
goto :RETRY

rem ==================== 4. 结果自查 ====================
:OK
echo.
echo ============================================================
echo   [OK] 推送完成
echo ============================================================
git status -sb
echo.
echo 最近提交：
git --no-pager log --format="%%h  %%ad" --date=format:"%%Y-%%m-%%d %%H:%%M" -3
echo.
set "AHEAD=0"
for /f "delims=" %%c in ('git rev-list --count origin/!BRANCH!..HEAD 2^>nul') do set "AHEAD=%%c"
echo 待推送提交数：!AHEAD!
echo ============================================================
goto :DONE

:FAIL
echo.
echo ============================================================
echo   [X] 操作未完成，见上方错误信息
echo ============================================================

:DONE
echo.
pause
endlocal
exit /b 0
