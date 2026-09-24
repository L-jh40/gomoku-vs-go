@echo off
rem build.bat - compile every source under cpp/src into build\engine.exe with MSVC.
rem Works from any working directory: switch to the script's own directory first.
setlocal
cd /d "%~dp0"

if not exist build mkdir build

call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 (
    echo [build] failed to initialize MSVC environment
    exit /b 1
)

cl /nologo /utf-8 /EHsc /O2 /std:c++17 /MT /Fo:build\ /Fe:build\engine.exe src\*.cpp
if errorlevel 1 (
    echo [build] compile failed
    exit /b 1
)

echo [build] ok: build\engine.exe
