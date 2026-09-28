@echo off
title Haimiya IA - Assistente
cls
echo.
echo ==========================================
echo   Haimiya IA - Assistente
echo ==========================================
echo.

rem Mudar para a pasta deste .bat (garante que run.py e .env sejam encontrados)
cd /d "%~dp0"

rem Definir caminho do Python
set PYTHON_PATH="C:\Program Files\Python312\python.exe"

rem Verificar se o Python existe
if not exist %PYTHON_PATH% (
    echo.
    echo ERRO: Python 3.12 nao encontrado em %PYTHON_PATH%
    echo Por favor, instale o Python ou ajuste a variavel PYTHON_PATH neste arquivo
    pause
    exit /b 1
)

rem Verificar se estamos no diretorio correto
if not exist run.py (
    echo.
    echo ERRO: Arquivo run.py nao encontrado
    echo Certifique-se de que run_ia.bat esta na mesma pasta do run.py
    pause
    exit /b 1
)

rem Verificar se .env existe
if not exist .env (
    echo.
    echo AVISO: Arquivo .env nao encontrado
    echo Sem ele a IA nao arranca. Copie .env.example para .env e preencha as chaves.
    echo.
    pause
    exit /b 1
)

rem Executar a IA
echo.
echo ==========================================
echo   Iniciando Haimiya...
echo ==========================================
echo.
%PYTHON_PATH% run.py
echo.
echo ==========================================
echo Haimiya finalizada.
echo ==========================================
pause
