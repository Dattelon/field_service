Param(
  [string]$RepoPath = "C:\ProjectF\field-service",
  [string]$Branch = "feature/referral_rewards",
  [string]$CommitMessage = "",
  [ValidateSet('safe','rebase','force')]
  [string]$Mode = 'safe',
  [string]$LogFile = "C:\ProjectF\\.local\\logs\\auto_push_field_service.log"
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
      # Try to track remote branch if it exists; otherwise create new
      & $git -C $RepoPath ls-remote --exit-code --heads origin ("refs/heads/" + $Branch) 2>$null | Out-Null
      if ($LASTEXITCODE -eq 0) {
        & $git -C $RepoPath checkout -B $Branch --track ("origin/" + $Branch) | Out-Null
        Write-Log "Checked out new local branch $Branch tracking origin/$Branch"
      } else {
        & $git -C $RepoPath checkout -B $Branch | Out-Null
        Write-Log "Created and switched to new local branch $Branch"
      }
    } else {
      & $git -C $RepoPath checkout $Branch | Out-Null
      Write-Log "Switched to branch $Branch"
    }
  }
  # Stage all changes
  & $git -C $RepoPath add -A
  $staged = & $git -C $RepoPath diff --cached --name-only
  if ($staged) {
    if (-not $CommitMessage -or [string]::IsNullOrWhiteSpace($CommitMessage)) {
      try {
        Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction Stop
        $defaultMsg = 'WIP: sync ' + (Get-Date -Format 'yyyy-MM-dd HH:mm')
        $CommitMessage = [Microsoft.VisualBasic.Interaction]::InputBox('Введите сообщение коммита', 'Публикация изменений на GitHub', $defaultMsg)
        if (-not $CommitMessage -or [string]::IsNullOrWhiteSpace($CommitMessage)) { $CommitMessage = $defaultMsg }
      } catch {
        $CommitMessage = 'WIP: sync ' + (Get-Date -Format 'yyyy-MM-dd HH:mm')
      }
    }
    & $git -C $RepoPath commit -m $CommitMessage | Out-Null
    Write-Log ("Committed: " + $CommitMessage)
  } else {
    Write-Log "Nothing to commit (index clean)"
  }
  # Fetch remote state
  & $git -C $RepoPath fetch origin $Branch --prune | Out-Null
  $cmp = & $git -C $RepoPath rev-list --left-right --count ("origin/" + $Branch + "...HEAD")
  $parts = $cmp -split "\s+" | Where-Object { $_ -ne '' }
  $behind = 0; $ahead = 0
  if ($parts.Count -ge 2) { $behind = [int]$parts[0]; $ahead = [int]$parts[1] }
  if ($behind -gt 0) {
    switch ($Mode) {
      'rebase' {
        $out = & $git -C $RepoPath pull --rebase 2>&1
        Write-Log ("Pulled with rebase. Output: " + $out)
      }
      'force' {
        Write-Log "Remote is ahead by $behind; will force-push with lease"
      }
      Default {
        Write-Log "Abort push: remote ahead by $behind. Run pull first or rerun with -Mode rebase/force"
        Write-Output "Remote ahead by $behind. Pull first (safe mode)."
        exit 0
      }
    }
  }
  # Push
  if ($Mode -eq 'force') {
    $out = & $git -C $RepoPath push --force-with-lease -u origin $Branch 2>&1
    Write-Log ("Pushed (force-with-lease). Output: " + $out)
  } else {
    $out = & $git -C $RepoPath push -u origin $Branch 2>&1
    Write-Log ("Pushed. Output: " + $out)
  }
  Write-Output "PUSH_OK"
  exit 0
}
catch {
  Write-Log ("Error: " + $_.Exception.Message)
  Write-Output ("PUSH_ERROR: " + $_.Exception.Message)
  exit 1
}
