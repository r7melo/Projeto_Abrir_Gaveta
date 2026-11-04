@echo off
chcp 65001 > nul
title Compilar - Abrir Gaveta PDV
cd /d "%~dp0"

echo ========================================================
echo        Compilando - Abrir Gaveta PDV
echo ========================================================
echo.

python -m pip install --quiet -r requirements.txt
if errorlevel 1 goto erro

echo [1/2] Programa principal (pasta, usada no MSIX)...
python -m PyInstaller --noconfirm --clean --noconsole --onedir --name abrir_gaveta --icon=icon-open-drawer.ico --add-data "icon-open-drawer.ico;." --distpath Store abrir_gaveta.py
if errorlevel 1 goto erro

echo [2/2] Executavel de inicio com o Windows (segundo plano)...
python -m PyInstaller --noconfirm --clean --noconsole --onefile --name gaveta_inicio --icon=icon-open-drawer.ico --add-data "icon-open-drawer.ico;." --distpath dist_inicio abrir_gaveta.py
if errorlevel 1 goto erro
copy /y "dist_inicio\gaveta_inicio.exe" "Store\abrir_gaveta\gaveta_inicio.exe" > nul
if errorlevel 1 goto erro

rmdir /s /q build 2> nul
rmdir /s /q dist_inicio 2> nul
del /q *.spec 2> nul

echo.
echo Pronto! Programa em: Store\abrir_gaveta\
echo Proximo passo: empacotar_msix.bat
if not defined CI pause
exit /b 0

:erro
echo.
echo Ocorreu um erro na compilacao.
if not defined CI pause
exit /b 1
