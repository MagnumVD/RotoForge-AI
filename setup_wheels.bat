@echo off
setlocal enabledelayedexpansion

:: Define the path to the TOML file and wheels directory
set "manifest_file=blender_manifest.toml"
set "wheels_dir=.\wheels"
set "requirements_file=.\functions\deps_requirements.txt"

set "temp_file=blender_manifest_temp.toml"

:: Download missing wheels specified
::pip download -r %requirements_file% --only-binary :all: -d %wheels_dir% --no-deps

echo All wheels have been downloaded successfully.

:: Create a new temporary file
type nul > "%temp_file%"

:: Initialize skip flag
set "skip_lines="

:: Process the manifest file until we hit the wheels section
setlocal DisableDelayedExpansion
FOR /F "delims=" %%L in ('findstr /N "^" "%manifest_file%"') DO (
    set "line=%%L"
    setlocal EnableDelayedExpansion
    set "line=!line:*:=!" & rem Remove all characters to the first colon
    
    if "!line!"=="wheels = [" (
        :: Write the wheels section header
        echo.!line!>>"%temp_file%"
        
        :: Add all wheel files from the directory
        for %%f in ("%wheels_dir%\*.whl") do (
            echo.  "./wheels/%%~nxf",>>"%temp_file%"
        )
        
        :: Add the closing bracket
        echo ]>>"%temp_file%"
        
        :: Skip lines until we're past the wheels section
        call set "skip_lines=1"
        endlocal & set "skip_lines=1"
    ) else if defined skip_lines (
        if "!line!"=="]" (
            :: End skipping — clear the flag in parent scope
            endlocal & set "skip_lines="
        ) else (
            :: Still skipping — just endlocal silently
            endlocal
        )
    ) else (
        :: Not skipping — keep line
        echo.!line!>>"%temp_file%"
        endlocal
    )
)

:: Replace the original manifest file with the updated one
move /Y "%temp_file%" "%manifest_file%"

echo Wheels list updated in %manifest_file%.


pause
