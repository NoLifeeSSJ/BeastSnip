#Requires -Version 5.1
[CmdletBinding()]
param([string]$InstallDir = 'C:\SnipV1', [switch]$CloseRunningApp, [switch]$Launch)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Install.ps1') -InstallDir $InstallDir -InstallOCR -CloseRunningApp:$CloseRunningApp -Launch:$Launch
