@echo off
title Code-Distiller Build

py -3.12 -m PyInstaller build.spec --noconfirm

echo.
echo Done! Output: dist\Code-Distiller\
pause
