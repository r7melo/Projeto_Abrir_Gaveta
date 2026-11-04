@echo off
chcp 65001 > nul
title Empacotar MSIX - Abrir Gaveta PDV
cd /d "%~dp0"

echo ========================================================
echo        Gerando pacote MSIX - Abrir Gaveta PDV
echo ========================================================
echo.

if not exist "Store\abrir_gaveta\abrir_gaveta.exe" (
    echo ERRO: Store\abrir_gaveta\abrir_gaveta.exe nao encontrado.
    echo Rode o compilar.bat primeiro.
    goto erro
)

set "MAKEAPPX="
for /f "delims=" %%i in ('dir /b /s "%ProgramFiles(x86)%\Windows Kits\10\bin\makeappx.exe" 2^>nul ^| findstr /i "x64"') do set "MAKEAPPX=%%i"

if not defined MAKEAPPX (
    echo ERRO: makeappx.exe nao encontrado.
    echo Instale o Windows SDK: https://developer.microsoft.com/windows/downloads/windows-sdk/
    goto erro
)
echo Usando: %MAKEAPPX%
echo.

echo [1/3] Montando a pasta do pacote...
if exist msix_pkg rmdir /s /q msix_pkg
mkdir msix_pkg
xcopy /e /i /q /y "Store\abrir_gaveta\*" "msix_pkg\" > nul
if errorlevel 1 goto erro
copy /y "msix\AppxManifest.xml" "msix_pkg\AppxManifest.xml" > nul
xcopy /e /i /q /y "msix\Assets" "msix_pkg\Assets\" > nul
if errorlevel 1 goto erro

echo [2/3] Gerando o .msix...
if exist Abrir_Gaveta_PDV.msix del /q Abrir_Gaveta_PDV.msix
"%MAKEAPPX%" pack /d "msix_pkg" /p "Abrir_Gaveta_PDV.msix" /o
if errorlevel 1 goto erro

echo [3/3] Limpando...
rmdir /s /q msix_pkg

echo.
echo Pronto! Envie este arquivo no Partner Center, em Pacotes:
echo   %~dp0Abrir_Gaveta_PDV.msix
echo.
echo Observacao: o pacote nao e assinado. A Microsoft assina na certificacao,
echo entao ele nao instala localmente, so depois de publicado na Store.
if not defined CI pause
exit /b 0

:erro
echo.
echo Ocorreu um erro. Veja as mensagens acima.
if not defined CI pause
exit /b 1
