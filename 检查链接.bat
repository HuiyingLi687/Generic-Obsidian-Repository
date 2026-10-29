@echo off
chcp 65001 >nul
cd /d "%~dp0"
color 0F
echo ========================================================
echo   Obsidian 仓库链接体检
echo ========================================================
echo.
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没找到 python，请先安装 Python 或把它加进 PATH
    echo.
    pause
    exit /b 1
)
python tools\linkcheck.py %*
echo.
echo --------------------------------------------------------
echo   想自动修复上面「可自动修复」的项，把本文件拖到
echo   命令行后面加 --fix 运行，或执行：
echo     python tools\linkcheck.py --fix
echo --------------------------------------------------------
pause
