<#
.SYNOPSIS
  MAKER-Rebuild — instalador para Windows (PowerShell 5.1+ ou PowerShell 7).

.DESCRIPTION
  Modos:
    auto    (padrão) tenta o executável pronto da última release; se não houver, instala via Python
    exe     baixa o executável autônomo (não precisa de Python)
    python  cria um ambiente virtual isolado e instala o pacote (precisa de Python 3.9+)

.EXAMPLE
  .\install.ps1
  .\install.ps1 -Mode exe
  .\install.ps1 -Mode python -FromLocal        # a partir do checkout do repositório
  .\install.ps1 -Uninstall
  # sem clonar o repositório:
  & ([scriptblock]::Create((irm https://raw.githubusercontent.com/KMC1525/MAKER-Rebuild/main/install.ps1))) -Mode auto

.PARAMETER Prefix   Pasta de instalação (padrão: %LOCALAPPDATA%\MAKER-Rebuild); o executável fica em <Prefix>\bin
.PARAMETER Version  Versão da release (padrão: latest)
.PARAMETER Ref      Branch/tag usada no modo python quando não há checkout local (padrão: main)
.PARAMETER NoPath   Não altera o PATH do usuário
.PARAMETER DryRun   Só mostra o que faria
#>
[CmdletBinding()]
param(
  [ValidateSet('auto', 'exe', 'python')][string]$Mode = $(if ($env:MAKER_REBUILD_MODE) { $env:MAKER_REBUILD_MODE } else { 'auto' }),
  [string]$Prefix = $(if ($env:MAKER_REBUILD_PREFIX) { $env:MAKER_REBUILD_PREFIX } else { Join-Path $env:LOCALAPPDATA 'MAKER-Rebuild' }),
  [string]$Version = $(if ($env:MAKER_REBUILD_VERSION) { $env:MAKER_REBUILD_VERSION } else { 'latest' }),
  [string]$Ref = $(if ($env:MAKER_REBUILD_REF) { $env:MAKER_REBUILD_REF } else { 'main' }),
  [switch]$FromLocal,
  [switch]$Uninstall,
  [switch]$DryRun,
  [switch]$NoPath
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest muito mais rápido no PS 5.1
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }

$Repo = if ($env:MAKER_REBUILD_REPO) { $env:MAKER_REBUILD_REPO } else { 'KMC1525/MAKER-Rebuild' }
$BinDir = Join-Path $Prefix 'bin'
$Venv = Join-Path $Prefix 'venv'

function Say($m)  { Write-Host "• $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "✔ $m" -ForegroundColor Green }
function Warn($m) { Write-Host "! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "✖ $m" -ForegroundColor Red; exit 1 }

function Get-UserPath { [Environment]::GetEnvironmentVariable('Path', 'User') }
function Add-ToPath($dir) {
  if ($NoPath) { Warn "PATH não alterado (-NoPath). Adicione manualmente: $dir"; return }
  $cur = Get-UserPath
  $parts = @(); if ($cur) { $parts = $cur -split ';' | Where-Object { $_ } }
  if ($parts -notcontains $dir) {
    [Environment]::SetEnvironmentVariable('Path', (($parts + $dir) -join ';'), 'User')
    Ok "adicionado ao PATH do usuário: $dir (abra um NOVO terminal para valer)"
  }
  if (($env:Path -split ';') -notcontains $dir) { $env:Path = "$env:Path;$dir" }
}
function Remove-FromPath($dir) {
  $cur = Get-UserPath
  if (-not $cur) { return }
  $parts = $cur -split ';' | Where-Object { $_ -and ($_ -ne $dir) }
  [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
}

# ------------------------------------------------------------------ desinstalar
if ($Uninstall) {
  Say "removendo $Prefix"
  if (-not $DryRun) {
    if (Test-Path $Prefix) { Remove-Item -Recurse -Force $Prefix }
    Remove-FromPath $BinDir
  }
  Ok 'MAKER-Rebuild removido (a configuração e o cache do usuário foram mantidos)'
  exit 0
}

# ------------------------------------------------------------------ plataforma
$arch = switch ($env:PROCESSOR_ARCHITECTURE) { 'AMD64' { 'x86_64' } 'ARM64' { 'arm64' } default { '' } }
if ($env:PROCESSOR_ARCHITEW6432 -eq 'AMD64') { $arch = 'x86_64' }

function Release-Url($file) {
  if ($env:MAKER_REBUILD_BASE_URL) { return "$($env:MAKER_REBUILD_BASE_URL)/$file" }
  if ($Version -eq 'latest') { return "https://github.com/$Repo/releases/latest/download/$file" }
  return "https://github.com/$Repo/releases/download/v$($Version.TrimStart('v'))/$file"
}

function Url-Exists($url) {
  try { Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing | Out-Null; return $true } catch { return $false }
}

# ------------------------------------------------------------------ modo exe
function Install-Exe {
  if ($arch -ne 'x86_64') { Warn "sem executável pronto para a arquitetura '$($env:PROCESSOR_ARCHITECTURE)' (só x86_64)"; return $false }
  $asset = "maker-rebuild-windows-$arch.zip"
  $url = Release-Url $asset
  Say "procurando executável: $asset"
  if ($DryRun) { Write-Host "  [dry-run] baixar $url e instalar em $BinDir"; return $true }
  if (-not (Url-Exists $url)) { Warn "nenhuma release com $asset"; return $false }
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("maker-rebuild-" + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  try {
    $zip = Join-Path $tmp $asset
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    try {
      $shaFile = Join-Path $tmp "$asset.sha256"
      Invoke-WebRequest -Uri "$url.sha256" -OutFile $shaFile -UseBasicParsing
      $want = ((Get-Content $shaFile -Raw).Trim() -split '\s+')[0].ToLower()
      $got = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
      if ($want -ne $got) { Die "checksum SHA-256 não confere (esperado $want, obtido $got)" }
      Ok 'checksum SHA-256 verificado'
    } catch { Warn 'sem arquivo .sha256 na release — checksum não verificado' }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    Copy-Item (Join-Path $tmp 'maker-rebuild.exe') (Join-Path $BinDir 'maker-rebuild.exe') -Force
    Unblock-File (Join-Path $BinDir 'maker-rebuild.exe') -ErrorAction SilentlyContinue
    Ok "executável instalado em $(Join-Path $BinDir 'maker-rebuild.exe')"
    return $true
  } finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
}

# ------------------------------------------------------------------ modo python
function Find-Python {
  $candidates = @(@('py', '-3'), @('python'), @('python3'))
  foreach ($c in $candidates) {
    if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
    try {
      $args2 = @(); if ($c.Count -gt 1) { $args2 += $c[1..($c.Count - 1)] }
      $out = & $c[0] @args2 -c "import sys; print(sys.version_info >= (3, 9))" 2>$null
      if ($out -eq 'True') { return ,$c }
    } catch { }
  }
  return $null
}

function Install-Python {
  $py = Find-Python
  if (-not $py) { Die 'Python 3.9+ não encontrado. Instale em https://www.python.org/downloads/ (marque "Add python.exe to PATH") ou use -Mode exe.' }
  $here = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
  $pyproject = Join-Path $here 'pyproject.toml'
  if ($FromLocal -or ((Test-Path $pyproject) -and (Select-String -Path $pyproject -Pattern 'name = "maker-rebuild"' -Quiet))) {
    $src = $here; Say "instalando do checkout local: $src"
  } else {
    $src = "https://github.com/$Repo/archive/$Ref.zip"; Say "instalando de $src"
  }
  Say "criando ambiente virtual em $Venv"
  if ($DryRun) { Write-Host "  [dry-run] python -m venv $Venv ; pip install $src ; criar $BinDir\maker-rebuild.cmd"; return }
  $pyArgs = @(); if ($py.Count -gt 1) { $pyArgs += $py[1..($py.Count - 1)] }
  New-Item -ItemType Directory -Force -Path $Prefix, $BinDir | Out-Null
  & $py[0] @pyArgs -m venv $Venv
  if ($LASTEXITCODE -ne 0) { Die 'não consegui criar o ambiente virtual' }
  $vpy = Join-Path $Venv 'Scripts\python.exe'
  & $vpy -m pip install --quiet --upgrade pip 2>$null
  & $vpy -m pip install --quiet --upgrade $src
  if ($LASTEXITCODE -ne 0) { Die 'falha no pip install' }
  $shim = Join-Path $BinDir 'maker-rebuild.cmd'
  Set-Content -Path $shim -Encoding ASCII -Value "@echo off`r`n`"%~dp0..\venv\Scripts\maker-rebuild.exe`" %*"
  Ok "instalado em $Venv (atalho: $shim)"
}

# ------------------------------------------------------------------ execução
Say "MAKER-Rebuild · windows/$(if ($arch) { $arch } else { $env:PROCESSOR_ARCHITECTURE }) · modo: $Mode · prefixo: $Prefix"
switch ($Mode) {
  'exe'    { if (-not (Install-Exe)) { Die 'não foi possível instalar o executável (tente -Mode python)' } }
  'python' { Install-Python }
  default  {
    if ($FromLocal) { Install-Python }
    elseif (-not (Install-Exe)) { Warn 'sem executável pronto; usando o modo Python'; Install-Python }
  }
}

if ($DryRun) { Ok 'dry-run concluído (nada foi alterado)'; exit 0 }
Add-ToPath $BinDir
$exe = if (Test-Path (Join-Path $BinDir 'maker-rebuild.exe')) { Join-Path $BinDir 'maker-rebuild.exe' } else { Join-Path $BinDir 'maker-rebuild.cmd' }
try {
  $v = & $exe --version
  Ok "pronto! $v — experimente:  maker-rebuild demo ; maker-rebuild doctor"
} catch { Warn "instalado, mas '$exe --version' falhou: $_" }
if ($exe.EndsWith('.exe')) { Write-Host "  Se o Windows SmartScreen avisar sobre um 'editor desconhecido', o executável ainda não é assinado digitalmente (veja o README)." -ForegroundColor DarkGray }
