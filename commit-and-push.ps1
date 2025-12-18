param(
    [string]$Message = "Update local_markdown_viewer_app",
    # 可选：用于 git commit body 的多行文本；为空时只使用 Message 作为提交说明
    [string]$Body = "",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

Write-Host "[LAD] Git commit & push script" -ForegroundColor Cyan
Write-Host "Repository root: $PSScriptRoot" -ForegroundColor DarkCyan

# 切换到脚本所在目录（仓库根目录）
Set-Location -Path $PSScriptRoot

# 检查是否有需要提交的更改
$changes = git status --porcelain
if (-not $changes) {
    Write-Host "No changes to commit. Working tree clean." -ForegroundColor Yellow
    exit 0
}

Write-Host "Staging changes..." -ForegroundColor Cyan
# 这里采用 add .，如需更细粒度可以手动 git add
 git add .

Write-Host "Creating commit..." -ForegroundColor Cyan
if ([string]::IsNullOrWhiteSpace($Body)) {
    git commit -m $Message
}
else {
    git commit -m $Message -m $Body
}

Write-Host "Pushing to origin/$Branch ..." -ForegroundColor Cyan
 git push origin $Branch

Write-Host "Done." -ForegroundColor Green
