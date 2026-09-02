$ErrorActionPreference = "Continue"
$ports = @(8001, 5173)
$stopped = @()

foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        if ($connection.OwningProcess -and $stopped -notcontains $connection.OwningProcess) {
            Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
            $stopped += $connection.OwningProcess
            Write-Host "Stopped PID $($connection.OwningProcess) on port $port"
        }
    }
}

if ($stopped.Count -eq 0) {
    Write-Host "No Content Automation Studio dev services were listening on ports 8001 or 5173."
} else {
    Write-Host "Content Automation Studio development services stopped."
}
