Param(
  [string]$RepoPath = "C:\ProjectF\field-service",
  [string]$Branch = "feature/referral_rewards",
  [ValidateSet('safe','force','stash')]
  [string]$UpdateMode = 'safe',
  [string]$LogFile = "C:\ProjectF\.local\logs\auto_pull_field_service.log"
)
$ErrorActionPreference = 'Stop'
function Write-Log([string]$msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  $dir = Split-Path -Parent $LogFile
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  Add-Content -Path $LogFile -Value "[$ts] $msg"
}
try {
  if (-not (Test-Path $RepoPath)) { Write-Log "Repo not found: $RepoPath"; exit 1 }
  $git = "git"
  # Ensure branch exists and is checked out
  $current = & $git -C $RepoPath rev-parse --abbrev-ref HEAD
  if ($current -ne $Branch) {
    & $git -C $RepoPath fetch origin $Branch --prune | Out-Null
    & $git -C $RepoPath show-ref --verify --quiet ("refs/heads/" + $Branch)
    if ($LASTEXITCODE -ne 0) {
      & $git -C $RepoPath checkout -B $Branch --track ("origin/" + $Branch) | Out-Null
      Write-Log "Checked out new local branch $Branch tracking origin/$Branch"
    } else {
      & $git -C $RepoPath checkout $Branch | Out-Null
      Write-Log "Switched to branch $Branch"
    }
  }
  # Ensure upstream
  & $git -C $RepoPath branch --set-upstream-to ("origin/" + $Branch) $Branch 2>$null | Out-Null
  # Fetch
  & $git -C $RepoPath fetch origin $Branch --prune | Out-Null
  # If dirty
  $dirty = & $git -C $RepoPath status --porcelain
  if ($dirty) {
    switch ($UpdateMode) {
      'force' {
        & $git -C $RepoPath reset --hard ("origin/" + $Branch) | Out-Null
        Write-Log "Forced reset to origin/$Branch (dirty tree discarded)"; exit 0
      }
      'stash' {
        & $git -C $RepoPath stash push -u -m 'auto_pull stash' | Out-Null
        $pull = & $git -C $RepoPath pull --ff-only 2>&1
        & $git -C $RepoPath stash pop | Out-Null
        Write-Log "Pulled with stash. Output: $pull"; exit 0
      }
      Default {
        Write-Log "Skipped: working tree not clean"; exit 0
      }
    }
  }
  # Compare ahead/behind
  $cmp = & $git -C $RepoPath rev-list --left-right --count ("HEAD...origin/" + $Branch)
  $parts = $cmp -split "\s+" | Where-Object { $_ -ne '' }
  $ahead = 0; $behind = 0
  if ($parts.Count -ge 2) { $ahead = [int]$parts[0]; $behind = [int]$parts[1] }
  if ($behind -gt 0) {
    $pull = & $git -C $RepoPath pull --ff-only 2>&1
    Write-Log "Pulled ($behind behind, $ahead ahead). Output: $pull"
  } else {
    Write-Log "Up to date ($ahead ahead, $behind behind)"
  }
  exit 0
}
catch {
  Write-Log ("Error: " + $_.Exception.Message)
  exit 1
}
