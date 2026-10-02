@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
cl /nologo /utf-8 /EHsc /O2 /std:c++17 /Fe:dbg.exe dbg.cpp src\board.cpp src\forbidden.cpp src\pattern_table.cpp src\pattern_count.cpp src\eval.cpp src\search.cpp src\vcfvct.cpp
