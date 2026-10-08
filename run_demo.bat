@echo off
setlocal
cd /d "%~dp0"
if not exist compiler.exe (
    call build_windows.bat
    if errorlevel 1 (
        pause
        exit /b 2
    )
)
compiler.exe samples\valid.txt
echo.
compiler.exe samples\nested.txt
echo.
compiler.exe samples\invalid_syntax.txt
echo.
compiler.exe samples\invalid_lexical.txt
echo.
echo The two error examples are intentional.
pause

