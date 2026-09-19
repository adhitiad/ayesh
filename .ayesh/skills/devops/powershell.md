---
name: powershell
description: "Scripting & administrasi PowerShell Windows. Trigger: /powershell"
---

# PowerShell Scripting

## Best Practices
```powershell
#Requires -Version 5.1
#Requires -Modules ActiveDirectory

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$Param1,
    
    [Parameter(Mandatory=$false)]
    [ValidateSet("Option1","Option2")]
    [string]$Choice = "Option1",
    
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
```

## Error Handling
```powershell
try {
    Get-ChildItem -Path "C:\NonExistent" -ErrorAction Stop
} catch [System.IO.DirectoryNotFoundException] {
    Write-Warning "Directory not found"
} catch {
    Write-Error "Unexpected error: $_"
} finally {
    Write-Host "Cleanup"
}

# Retry pattern
function Invoke-WithRetry {
    param([scriptblock]$ScriptBlock, [int]$MaxRetries = 3)
    
    for ($i = 0; $i -lt $MaxRetries; $i++) {
        try {
            return & $ScriptBlock
        } catch {
            if ($i -eq $MaxRetries - 1) { throw }
            Start-Sleep -Seconds ([math]::Pow(2, $i))
        }
    }
}
```

## Module Management
```powershell
Find-Module -Name "ActiveDirectory"
Install-Module -Name "ActiveDirectory" -Force
Get-InstalledModule
Update-Module -Name "ActiveDirectory"
Import-Module -Name "ActiveDirectory"
Get-Command -Module ActiveDirectory
```

## PowerShell Gallery
```powershell
Register-PSRepository -Default -ErrorAction SilentlyContinue
Find-Script -Name "ScriptName"
Install-Script -Name "ScriptName" -Scope CurrentUser
Get-PSRepository
```

## Data Structures
```powershell
# Array
$items = @("item1", "item2", "item3")

# Hashtable
$config = @{
    Server = "localhost"
    Port = 8080
    Debug = $false
}

# Object
$server = [PSCustomObject]@{
    Name = "Server01"
    IP = "192.168.1.10"
    Status = "Running"
}

# Pipeline processing
$items | Where-Object { $_.Status -eq "Running" } | 
    Select-Object Name, IP | 
    Sort-Object Name |
    Format-Table -AutoSize
```

## Common Commands
```powershell
# Files
Get-ChildItem -Path "C:\" -Recurse -Filter "*.log"
Copy-Item -Path "source" -Destination "dest" -Recurse
Remove-Item -Path "file" -Force

# Services
Get-Service -Name "wuauserv"
Start-Service -Name "wuauserv"
Stop-Service -Name "wuauserv"
Restart-Service -Name "wuauserv"

# Processes
Get-Process | Where-Object { $_.CPU -gt 100 }
Stop-Process -Name "notepad" -Force

# Users
Get-ADUser -Filter {Enabled -eq $true}
New-ADUser -Name "John" -SamAccountName "john"

# Network
Test-NetConnection -ComputerName "server" -Port 443
Resolve-DnsName -Name "example.com"

# Events
Get-EventLog -LogName System -Newest 100 |
    Where-Object { $_.EntryType -eq "Error" }
```

## Script Template
```powershell
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$ServerName,
    
    [Parameter(Mandatory=$false)]
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    Write-Host $logMessage
}

try {
    Write-Log "Starting script for $ServerName"
    
    # Main logic here
    
    Write-Log "Script completed in $($stopwatch.Elapsed.TotalSeconds)s"
} catch {
    Write-Log "Script failed: $_" -Level "ERROR"
    throw
} finally {
    $stopwatch.Stop()
}
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Module tidak ada | `Install-Module -Name "ModuleName"` |
| Error handling | `try/catch/finally`, `$ErrorActionPreference` |
| Permission denied | Jalankan sebagai Administrator |
| Variable scope | Gunakan `$script:` atau `param()` |
