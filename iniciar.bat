@echo off
REM Launcher do servidor BIG-BANG (backend + jogo)
cd /d "%~dp0"
echo Iniciando servidor BIG-BANG...
echo Acesse no navegador: http://localhost:9000
python server.py 9000
pause
