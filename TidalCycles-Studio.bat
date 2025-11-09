@echo off
echo Starting TidalCycles Studio...

REM SuperColliderを起動
echo Starting SuperCollider...
start "" "C:\Program Files\SuperCollider-3.14.0\scide.exe"


REM 少し待ってからVS Codeを起動
echo Waiting for SuperCollider to load...
timeout /t 5 /nobreak > nul

echo Starting VS Code with TidalCycles...
cd /d C:\Users\fox10\repo\kitakita
stack exec -- code .

echo TidalCycles Studio is ready!
echo Remember to run: SuperDirt.start; in SuperCollider
pause