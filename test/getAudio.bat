@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Batch MP4 Audio Extractor

:: Check if ffmpeg is available
where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: ffmpeg not found
    echo Please install ffmpeg and add it to system PATH first
    pause
    exit /b
)

echo ======================================
echo   Batch Lossless Audio Extraction
echo   Output format: m4a (same filename)
echo ======================================
echo.
echo Scanning current directory for MP4 files...
echo.

set /a success=0
set /a fail=0

:: Iterate all .mp4 files in current directory
for %%f in (*.mp4) do (
    echo Processing: %%~nxf
    ffmpeg -i "%%f" -vn -acodec copy -y -hide_banner -loglevel error "%%~nf.m4a"
    
    if !errorlevel! equ 0 (
        echo Done: %%~nf.m4a
        set /a success+=1
    ) else (
        echo Failed: %%~nxf
        set /a fail+=1
    )
    echo.
)

echo ======================================
echo  Process finished
echo  Success: %success%
echo  Failed: %fail%
echo  Audio files saved in current folder
echo ======================================
pause
endlocal
