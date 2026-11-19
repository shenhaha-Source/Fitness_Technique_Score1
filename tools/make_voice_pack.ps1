param([string]$OutDir = "")

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path (Split-Path $PSScriptRoot -Parent) "assets\audio"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$zh = $synth.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh-*' } | Select-Object -First 1
if ($null -eq $zh) {
    $synth.Dispose()
    throw "No enabled zh-* SAPI voice found."
}
$synth.SelectVoice($zh.VoiceInfo.Name)
$synth.Rate = 0
$synth.Volume = 100

$phrases = [ordered]@{
    "start"    = "开始测试"
    "count_05" = "已经做了五个了"
    "count_10" = "已经做了十个了"
    "count_15" = "已经做了十五个了"
    "count_20" = "已经做了二十个了"
    "count_25" = "已经做了二十五个了"
    "count_30" = "已经做了三十个了"
}

foreach ($key in $phrases.Keys) {
    $path = Join-Path $OutDir ($key + ".wav")
    if (Test-Path $path) { Remove-Item $path -Force }
    $synth.SetOutputToWaveFile($path)
    $synth.Speak($phrases[$key])
    $synth.SetOutputToNull()
    Write-Host ("{0}  {1}" -f $key, (Get-Item $path).Length)
}
$synth.Dispose()
Write-Host ("voice: " + $zh.VoiceInfo.Name)
