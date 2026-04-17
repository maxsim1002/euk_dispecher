@echo off
cd C:\dispatch_app
start "Dispatch Server" cmd /k uvicorn main:app --host 0.0.0.0 --port 8000