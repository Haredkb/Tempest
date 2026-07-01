@echo off
call C:\Users\dhare\AppData\Local\miniforge3\Scripts\activate.bat C:\Users\dhare\AppData\Local\miniforge3
python -c "import sys, ssl; print(sys.version); print(ssl.OPENSSL_VERSION)"
