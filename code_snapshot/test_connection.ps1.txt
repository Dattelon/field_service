$password = "owo?8x-YA@vRN*"
$server = "217.199.254.27"
$user = "root"

# Test connection
Write-Host "Testing connection to $server..." -ForegroundColor Yellow
Test-Connection -ComputerName $server -Count 2 -Quiet
