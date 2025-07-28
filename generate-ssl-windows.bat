@echo off
REM SSL Certificate Generator for Windows
REM This script generates self-signed SSL certificates for development

echo ========================================
echo   SSL Certificate Generator for Windows
echo   Odoo Multi-Tenant System
echo ========================================
echo.

REM Check if OpenSSL is available
openssl version >nul 2>&1
if errorlevel 1 (
    echo ERROR: OpenSSL is not installed or not in PATH
    echo.
    echo Please install OpenSSL:
    echo 1. Download from: https://slproweb.com/products/Win32OpenSSL.html
    echo 2. Install and add to PATH
    echo 3. Run this script again
    pause
    exit /b 1
)

echo OpenSSL found. Generating SSL certificates...
echo.

REM Create SSL directory
if not exist "ssl" mkdir ssl

REM Generate khudroo.com certificate configuration
echo [req] > ssl\khudroo.conf
echo default_bits = 2048 >> ssl\khudroo.conf
echo prompt = no >> ssl\khudroo.conf
echo default_md = sha256 >> ssl\khudroo.conf
echo distinguished_name = dn >> ssl\khudroo.conf
echo req_extensions = v3_req >> ssl\khudroo.conf
echo. >> ssl\khudroo.conf
echo [dn] >> ssl\khudroo.conf
echo C=BD >> ssl\khudroo.conf
echo ST=Dhaka >> ssl\khudroo.conf
echo L=Dhaka >> ssl\khudroo.conf
echo O=Khudroo >> ssl\khudroo.conf
echo OU=IT Department >> ssl\khudroo.conf
echo CN=khudroo.com >> ssl\khudroo.conf
echo. >> ssl\khudroo.conf
echo [v3_req] >> ssl\khudroo.conf
echo basicConstraints = CA:FALSE >> ssl\khudroo.conf
echo keyUsage = nonRepudiation, digitalSignature, keyEncipherment >> ssl\khudroo.conf
echo subjectAltName = @alt_names >> ssl\khudroo.conf
echo. >> ssl\khudroo.conf
echo [alt_names] >> ssl\khudroo.conf
echo DNS.1 = khudroo.com >> ssl\khudroo.conf
echo DNS.2 = *.khudroo.com >> ssl\khudroo.conf
echo DNS.3 = www.khudroo.com >> ssl\khudroo.conf

REM Generate localhost certificate configuration
echo [req] > ssl\localhost.conf
echo default_bits = 2048 >> ssl\localhost.conf
echo prompt = no >> ssl\localhost.conf
echo default_md = sha256 >> ssl\localhost.conf
echo distinguished_name = dn >> ssl\localhost.conf
echo req_extensions = v3_req >> ssl\localhost.conf
echo. >> ssl\localhost.conf
echo [dn] >> ssl\localhost.conf
echo C=BD >> ssl\localhost.conf
echo ST=Dhaka >> ssl\localhost.conf
echo L=Dhaka >> ssl\localhost.conf
echo O=Khudroo Dev >> ssl\localhost.conf
echo OU=Development >> ssl\localhost.conf
echo CN=localhost >> ssl\localhost.conf
echo. >> ssl\localhost.conf
echo [v3_req] >> ssl\localhost.conf
echo basicConstraints = CA:FALSE >> ssl\localhost.conf
echo keyUsage = nonRepudiation, digitalSignature, keyEncipherment >> ssl\localhost.conf
echo subjectAltName = @alt_names >> ssl\localhost.conf
echo. >> ssl\localhost.conf
echo [alt_names] >> ssl\localhost.conf
echo DNS.1 = localhost >> ssl\localhost.conf
echo DNS.2 = *.localhost >> ssl\localhost.conf
echo IP.1 = 127.0.0.1 >> ssl\localhost.conf
echo IP.2 = ::1 >> ssl\localhost.conf

echo Generating khudroo.com certificate...
openssl genrsa -out ssl\khudroo.com.key 2048
openssl req -new -x509 -key ssl\khudroo.com.key -out ssl\khudroo.com.crt -days 365 -config ssl\khudroo.conf -extensions v3_req

echo.
echo Generating localhost certificate...
openssl genrsa -out ssl\localhost.key 2048
openssl req -new -x509 -key ssl\localhost.key -out ssl\localhost.crt -days 365 -config ssl\localhost.conf -extensions v3_req

echo.
echo ========================================
echo   SSL Certificates Generated Successfully!
echo ========================================
echo.
echo Files created:
echo   ssl\khudroo.com.crt  - Certificate for *.khudroo.com
echo   ssl\khudroo.com.key  - Private key for khudroo.com
echo   ssl\localhost.crt    - Certificate for localhost
echo   ssl\localhost.key    - Private key for localhost
echo.
echo Certificate Information:
openssl x509 -in ssl\khudroo.com.crt -text -noout | findstr "Subject:\|DNS:\|Not Before\|Not After"
echo.
echo Next steps:
echo 1. Start your Docker containers: docker-compose up -d
echo 2. Access your site at: https://khudroo.com
echo 3. Add DNS entries to your hosts file for testing
echo.
echo Note: Browsers will show security warnings for self-signed certificates.
echo Click "Advanced" and "Proceed to site" to continue.
echo.
pause
