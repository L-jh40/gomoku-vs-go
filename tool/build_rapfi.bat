@echo off
rem (build Rapfi CLI; outputs to toolapfi_build)
rem (build Rapfi CLI; outputs to toolapfi_build)
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" 1>nul 2>&1
where cl >nul 2>&1
if errorlevel 1 (
    echo [build] vcvars64 failed
    exit /b 1
)
set "RAPFI=C:\Users\lin\Downloads\rapfi-250615\rapfi-250615\Rapfi"
set "OUT=%~dp0rapfi_build"
cd /d "%RAPFI%"
if not exist "%OUT%" mkdir "%OUT%"
set "INC=/I. /Iexternal\simde\include /Iexternal\thread-pool\include /Iexternal\cpptoml\include /Iexternal\cxxopts\include /Iexternal\libnpy\include /Iexternal\lz4\include /Iexternal\flat.hpp\headers /Iexternal\flat.hpp\headers\flat.hpp"
set "CFLAGS=/nologo /utf-8 /EHsc /O2 /std:c++17 /DMULTI_THREADING /DUSE_AVX2 /arch:AVX2 %INC%"

cl %CFLAGS% /Fo%OUT%\ config.cpp internalConfig.cpp main.cpp
for %%f in ("%RAPFI%\command\*.cpp")      do @cl %CFLAGS% /Fo%OUT%\cmd_%%~nf.obj /c "%%f"
for %%f in ("%RAPFI%\core\*.cpp")         do @cl %CFLAGS% /Fo%OUT%\core_%%~nf.obj /c "%%f"
for %%f in ("%RAPFI%\database\*.cpp")     do @cl %CFLAGS% /Fo%OUT%\db_%%~nf.obj /c "%%f"
for %%f in ("%RAPFI%\eval\*.cpp")         do @cl %CFLAGS% /Fo%OUT%\eval_%%~nf.obj /c "%%f"
for %%f in ("%RAPFI%\game\*.cpp")         do @cl %CFLAGS% /Fo%OUT%\game_%%~nf.obj /c "%%f"
for %%f in ("%RAPFI%\search\*.cpp")       do @cl %CFLAGS% /Fo%OUT%\s_%%~nf.obj /c "%%f"
for %%f in ("%RAPFI%\search\ab\*.cpp")    do @cl %CFLAGS% /Fo%OUT%\sab_%%~nf.obj /c "%%f"
for %%f in ("%RAPFI%\search\mcts\*.cpp")  do @cl %CFLAGS% /Fo%OUT%\smcts_%%~nf.obj /c "%%f"
for %%f in ("%RAPFI%\tuning\*.cpp")       do @cl %CFLAGS% /Fo%OUT%\tun_%%~nf.obj /c "%%f"
cl /nologo /utf-8 /EHsc /O2 /c /Iexternal\lz4\include /Iexternal\lz4\src /Fo%OUT%\ external\lz4\src\lz4_all.c external\lz4\src\xxhash.c
if errorlevel 1 (
    echo [build] lz4/xxhash compile failed
    exit /b 1
)
link /nologo /OUT:"%OUT%\rapfi_cli.exe" "%OUT%\*.obj" advapi32.lib
echo [build] exit=%errorlevel%
