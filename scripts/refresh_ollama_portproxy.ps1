# Refresh Windows portproxy for Ollama in WSL (WSL IP changes after restart).
# Run on UIC-Server as the user with admin rights (SSH or RDP).
$Port = 11434
$WslIp = (wsl -d Ubuntu -u root -- hostname -I).Trim().Split(" ")[0]
if (-not $WslIp) { Write-Error "Could not resolve WSL IP"; exit 1 }
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$Port 2>$null
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$Port connectaddress=$WslIp connectport=$Port
Write-Host "Ollama portproxy: 0.0.0.0:$Port -> ${WslIp}:$Port"
netsh interface portproxy show all
