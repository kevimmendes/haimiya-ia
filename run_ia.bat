@echo off
title Rem IA Assistant - Versão Evoluída
cls
echo.
echo ==========================================
echo   Rem IA Assistant - Evoluída
echo ==========================================
echo.
echo Iniciando o sistema...
echo.

rem Definir caminho do Python
set PYTHON_PATH="C:\Program Files\Python312\python.exe"

rem Verificar se o Python existe
if not exist %PYTHON_PATH% (
    echo.
    echo ERRO: Python 3.12 nao encontrado em %PYTHON_PATH%
    echo Por favor, instale o Python ou ajuste o caminho no arquivo .bat
    pause
    exit /b 1
)

rem Verificar se estamos no diretório correto
if not exist run.py (
    echo.
    echo ERRO: Arquivo run.py nao encontrado no diretorio atual
    echo Certifique-se de executar este arquivo na pasta do projeto
    pause
    exit /b 1
)

rem Verificar se .env existe
if not exist .env (
    echo.
    echo Aviso: Arquivo .env nao encontrado
    echo O sistema pode ter problemas com as chaves API
    echo Copie .env.example para .env se necessario
)

rem Executar a IA
echo.
echo ==========================================
echo   Iniciando Rem IA...
echo ==========================================
echo.
%PYTHON_PATH% run.py
echo.
echo ==========================================
echo Rem IA finalizada.
echo ==========================================
pause