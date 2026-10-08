@echo off
setlocal
cd /d "%~dp0"
where flex >nul 2>nul
if errorlevel 1 (
    echo flex is required and must be on PATH.
    exit /b 2
)
where gcc >nul 2>nul
if errorlevel 1 (
    echo gcc is required and must be on PATH.
    exit /b 2
)
flex lexer.l
if errorlevel 1 exit /b 2
gcc -std=c99 -Wall -Wextra syntax_checker.c lex.yy.c -o compiler.exe
if errorlevel 1 exit /b 2
echo Build successful. Run: compiler.exe samples\valid.txt

