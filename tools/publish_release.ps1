#!/usr/bin/env pwsh
<#
.SYNOPSIS
  把 MEIZU21GKI 的 run 22 产物推成正式版 release "0.0.1-fly"，
  并把触控修复版保持为 prerelease。

.DESCRIPTION
  为什么需要 PAT：
    - 创建/改名 release、改 prerelease 标志、迁移 assets —— 这些是 GitHub REST API 操作，
      `git push` 做不到（git 只能推 commits/tags）。
    - 本脚本用 HTTPS API，因此不受本机"直连 github.com:443 被墙"的影响
      （实测 api.github.com 可达）。

  所需的 PAT 权限：经典 token 勾 `repo`（或 fine-grained token 勾
  Contents: Read and write + Metadata: Read）。

  运行方式：
    $env:GH_TOKEN = 'ghp_xxx'      # 或 setx GH_TOKEN ...
    pwsh -File tools/publish_release.ps1

  不传 token 时脚本只做 dry-run，打印将要执行的动作，不修改远端。
#>
[CmdletBinding()]
param(
    [string]$Repo     = 'FengFaQ/MEIZU21GKI',
    [string]$Token    = $env:GH_TOKEN,
    [string]$OfficialTag  = '0.0.1-fly',
    [string]$OfficialName = '0.0.1-fly — MEIZU21GKI (run 22, ReSukiSU + SUSFS, android14-6.1.25)',
    [string]$SourceTag    = 'meizu21-sukisu-22',
    [string]$OfficialNotesFile = "$PSScriptRoot/../docs/release-notes-0.0.1-fly.md",
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$ApiBase = "https://api.github.com/repos/$Repo"

function Get-Headers {
    $h = @{
        'Accept'               = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
        'User-Agent'           = 'MEIZU21GKI-release-publisher'
    }
    if ($Token) { $h['Authorization'] = "Bearer $Token" }
    return $h
}

function Invoke-Gh {
    param([string]$Method, [string]$Uri, $Body)
    $args = @{ Method = $Method; Uri = $Uri; Headers = (Get-Headers); TimeoutSec = 60 }
    if ($null -ne $Body) {
        $args['Body']        = ($Body | ConvertTo-Json -Depth 10)
        $args['ContentType'] = 'application/json'
    }
    return Invoke-RestMethod @args
}

Write-Host "=== publish_release.ps1 ==="
Write-Host "  repo        : $Repo"
Write-Host "  token       : $(if($Token){'present'}else{'MISSING (dry-run only)'})"
Write-Host "  official tag: $OfficialTag   <- from $SourceTag"
Write-Host "  execute     : $($Execute.IsPresent)"
Write-Host ""

if (-not $Execute) {
    Write-Host "DRY-RUN。将执行的动作："
    Write-Host "  1) GET  $ApiBase/releases/tags/$SourceTag"
    Write-Host "     -> 校验它是 success 构建的 run22 产物（含 boot.img / AnyKernel3 / apk）"
    Write-Host "  2) POST $ApiBase/releases"
    Write-Host "     { tag_name: '$OfficialTag', name: '...', prerelease: false, draft: false,"
    Write-Host "       body: <docs/release-notes-0.0.1-fly.md> }"
    Write-Host "  3) 逐 asset: POST /releases/{id}/assets?name=<name>  (从源 release 下载后重新上传)"
    Write-Host "     —— 已知 objects.githubusercontent.com 在本机被墙，所以先尝试直连下载；"
    Write-Host "        失败则改用 dist 分支的副本作为数据来源。"
    Write-Host "  4) 触控修复版（最新的 meizu21-sukisu-N 预览版，当前为 26）：保持 prerelease=true，"
    Write-Host "     仅确保 release notes 写明「内核侧改动未经验证」。"
    Write-Host ""
    Write-Host "要真正执行： pwsh -File tools/publish_release.ps1 -Execute   （需 GH_TOKEN）"
    exit 0
}

if (-not $Token) { throw "需要 GH_TOKEN（或 -Token）才能执行；API 写操作必须鉴权。" }

# ---- 1) 取源 release ------------------------------------------------------
Write-Host "[1/4] 取源 release $SourceTag ..."
$src = Invoke-Gh GET "$ApiBase/releases/tags/$SourceTag"
Write-Host "      id=$($src.id)  prerelease=$($src.prerelease)  assets=$($src.assets.Count)"
foreach ($a in $src.assets) { Write-Host ("      - {0} ({1:N0} B)" -f $a.name, $a.size) }

# ---- 2) 建正式版 release --------------------------------------------------
Write-Host "[2/4] 创建正式版 release $OfficialTag ..."
$notes = if (Test-Path $OfficialNotesFile) { Get-Content $OfficialNotesFile -Raw } else { "run 22 产物，标记为正式版 0.0.1-fly。" }
$body = @{
    tag_name         = $OfficialTag
    target_commitish = 'main'
    name             = $OfficialName
    body             = $notes
    draft            = $false
    prerelease       = $false
}
try {
    $new = Invoke-Gh POST "$ApiBase/releases" $body
    Write-Host "      创建成功 id=$($new.id)  url=$($new.html_url)"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 422) {
        Write-Host "      已存在同名 tag/release，改为复用"
        $new = Invoke-Gh GET "$ApiBase/releases/tags/$OfficialTag"
        $new = Invoke-Gh PATCH "$ApiBase/releases/$($new.id)" @{ prerelease = $false; name = $OfficialName; body = $notes }
        Write-Host "      已强制 prerelease=false  id=$($new.id)"
    } else { throw }
}

# ---- 3) 迁移 assets -------------------------------------------------------
# 数据来源有两条路，按可靠性排序：
#   (a) release asset 直链 (browser_download_url) —— 权威，但要经
#       objects.githubusercontent.com，本机实测被墙；
#   (b) dist 分支的文件 —— 本机可达 (走 git over ssh)，且内容与 release 资产同源
#       （CI 会把同一批产物 force-push 到 dist）。
# 先试 (a)，失败自动回退 (b)。
$DistDir = $null
function Get-DistDir {
    if ($script:DistDir) { return $script:DistDir }
    $tmp = Join-Path $env:TEMP 'meizu21gki-dist'
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "      (回退) 从 dist 分支取产物 ..."
    git -C $PSScriptRoot/.. fetch --depth 1 origin dist | Out-Null
    git -C $PSScriptRoot/.. worktree add --detach $tmp FETCH_HEAD | Out-Null
    $script:DistDir = $tmp
    return $tmp
}

Write-Host "[3/4] 迁移 assets ..."
foreach ($a in $src.assets) {
    $already = (Invoke-Gh GET "$ApiBase/releases/$($new.id)/assets") | Where-Object { $_.name -eq $a.name }
    if ($already) { Write-Host "      - $($a.name) 已存在，跳过"; continue }

    $tmp = Join-Path $env:TEMP ("rel-" + $a.name)
    Write-Host "      - 取 $($a.name) ..."
    $got = $false
    try {
        Invoke-WebRequest -Uri $a.browser_download_url -OutFile $tmp -Headers (Get-Headers) -TimeoutSec 900
        $got = $true
    } catch {
        Write-Host "        直链失败 ($($_.Exception.Message))，改用 dist 分支"
    }
    if (-not $got) {
        $d = Get-DistDir
        $cand = Join-Path $d $a.name
        if (-not (Test-Path $cand)) { throw "dist 分支里也找不到 $($a.name)，无法迁移" }
        Copy-Item $cand $tmp -Force
    }

    Write-Host "      - 上传 $($a.name) ..."
    $up = "$($new.upload_url -replace '\{.*$','')?name=$([uri]::EscapeDataString($a.name))"
    Invoke-RestMethod -Method Post -Uri $up -Headers (Get-Headers) `
        -ContentType 'application/octet-stream' -InFile $tmp -TimeoutSec 900
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    Write-Host "        完成"
}

# ---- 4) 确认触控版仍是 prerelease ----------------------------------------
Write-Host "[4/4] 核对触控修复版（最新 meizu21-sukisu-N）仍为 prerelease ..."
$all = Invoke-Gh GET "$ApiBase/releases?per_page=20"
foreach ($r in $all) {
    $flag = if ($r.prerelease) { 'prerelease' } else { 'OFFICIAL ' }
    Write-Host ("      {0,-24} {1}" -f $r.tag_name, $flag)
}

Write-Host ""
Write-Host "完成。正式版: $($new.html_url)"
