@echo off
rem 双击运行外置插件：Rapfi / Yixin 局面 -> 粘贴板.md
cd /d "%~dp0"
py -3.14 rapfi_plugin.py
if errorlevel 1 pause
