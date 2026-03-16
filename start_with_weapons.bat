@echo off
set CYBERSHIELD_ENABLE_WEAPON_DETECT=true
set CYBERSHIELD_WEAPON_DETECT_CONFIDENCE=0.55
set CYBERSHIELD_WEAPON_SCAN_INTERVAL=1.0
set CYBERSHIELD_ENABLE_HELMET_DETECT=true
set CYBERSHIELD_HELMET_DETECT_CONFIDENCE=0.45
cd /d "%~dp0integrated-video-analytics"
"C:\Users\jaipr\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8080
