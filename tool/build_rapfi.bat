@echo on
rem 构建 Rapfi CLI（只读 Rapfi 源码，所有产物输出到本仓库 tool\rapfi_build）
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
set RAPFI=C:\Users\lin\Downloads\rapfi-250615\rapfi-250615\Rapfi
set OUT=%~dp0rapfi_build
cd /d "%RAPFI%"
if not exist "%OUT%" mkdir "%OUT%"
set INC=/I. /Iexternal\simde\include /Iexternal\thread-pool\include /Iexternal\cpptoml\include /Iexternal\cxxopts\include /Iexternal\libnpy\include /Iexternal\lz4\include /Iexternal\flat.hpp\headers /Iexternal\flat.hpp\headers\flat.hpp
for /f "usebackq delims=" %%f in (`dir /s /b *.cpp ^| findstr /v /i "onnxevaluator"`) do @cl /nologo /utf-8 /EHsc /O2 /std:c++17 /DMULTI_THREADING %INC% /Fo%OUT%\ /c "%%f"
cl /nologo /utf-8 /EHsc /O2 /c /Iexternal\lz4\src /Fo%OUT%\ external\lz4\src\xxhash.c external\lz4\src\lz4.c external\lz4\src\lz4frame.c
link /nologo /OUT:"%OUT%\rapfi_cli.exe" "%OUT%\*.obj" advapi32.lib
