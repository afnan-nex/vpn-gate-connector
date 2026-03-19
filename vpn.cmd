@echo off
set /p "vpn_address=Enter the VPN Server Address: "

echo.
echo Updating VPNGate-SSTP with address and security settings...
:: This line now forces the authentication to MSChapv2 and enables encryption
powershell -Command "Set-VpnConnection -Name 'VPNGate-SSTP' -ServerAddress '%vpn_address%' -AuthenticationMethod MSChapv2 -EncryptionLevel Required"

echo.
echo Attempting to connect...
:: We will re-add the "vpn vpn" here to ensure the CLI sends them fresh
rasdial "VPNGate-SSTP" vpn vpn

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Still getting Error 691? 
    echo 1. Go to 'Control Panel' > 'Network and Sharing Center'
    echo 2. Click 'Change adapter settings' > Right-click 'VPNGate-SSTP' > Properties
    echo 3. Go to 'Security' tab. Ensure 'Data encryption' is 'Require encryption' 
    echo    and 'MS-CHAP v2' is checked.
) else (
    echo.
    echo [SUCCESS] Connected! 
    pause >nul
    rasdial "VPNGate-SSTP" /disconnect
)
pause
