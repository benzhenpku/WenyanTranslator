@echo off
cd /d "%~dp0"
if exist "D:\python\pythonw.exe" (
    start "" "D:\python\pythonw.exe" wenyan_translator.pyw
) else (
    start "" pythonw.exe wenyan_translator.pyw
)
