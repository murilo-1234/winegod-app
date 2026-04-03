Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Norm([string]$s) {
  if ($null -eq $s) { return "" }
  $s = $s.ToLowerInvariant().Trim()
  $s = $s -replace "[áàâãä]", "a"
  $s = $s -replace "[éèêë]", "e"
  $s = $s -replace "[íìîï]", "i"
  $s = $s -replace "[óòôõö]", "o"
  $s = $s -replace "[úùûü]", "u"
  $s = $s -replace "ñ", "n"
  $s = $s -replace "ç", "c"
  # Remove apostrofos e variantes. Em PowerShell, use aspas simples para o backtick entrar literal.
  $s = $s -replace '[''’‘`]', ""
  $s = $s -replace "-", ""
  $s = $s -replace "[^a-z0-9 ]", ""
  $s = $s -replace "\s+", " "
  return $s.Trim()
}

function Get-TokenScore([string]$inputNorm, [string[]]$tokens) {
  if ([string]::IsNullOrWhiteSpace($inputNorm)) { return 0.0 }
  if ($tokens.Count -eq 0) { return 0.0 }
  $inTokens = [System.Collections.Generic.HashSet[string]]::new()
  foreach ($t in ($inputNorm -split " ")) {
    if ($t.Length -ge 2) { $null = $inTokens.Add($t) }
  }
  $hit = 0
  $tot = 0
  foreach ($t in $tokens) {
    if ($t.Length -lt 3) { continue } # ignora tokens muito curtos
    $tot++
    if ($inTokens.Contains($t)) { $hit++ }
  }
  if ($tot -eq 0) { return 0.0 }
  return [double]$hit / [double]$tot
}

function Guess-Fallback([string]$orig) {
  $n = Norm $orig

  # Destilados (S)
  $spirit = @(
    "whisky","whiskey","vodka","gin","rum","tequila","mezcal","cognac","brandy","armagnac","calvados",
    "grappa","pisco","schnapps","liqueur","liqueurs","liqueor","amarone","vermouth","bitters","absinthe",
    "bourbon","scotch"
  )
  foreach ($w in $spirit) {
    if ($n -match "\b$([regex]::Escape($w))\b") { return "S" }
  }

  # Nao-vinho (X) (bem conservador)
  $notWine = @("beer","cerveja","cider","kombucha","soda","agua","water","juice","suco")
  foreach ($w in $notWine) {
    if ($n -match "\b$([regex]::Escape($w))\b") { return "X" }
  }

  # Caso padrao: vinho, mas sem inventar detalhes.
  $pais = "??"
  if ($n -match "\busa\b" -or $n -match "\bcalifornia\b") { $pais = "estados unidos" }
  elseif ($n -match "\bfrance\b") { $pais = "franca" }
  elseif ($n -match "\bitaly\b") { $pais = "italia" }
  elseif ($n -match "\bspain\b") { $pais = "espanha" }
  elseif ($n -match "\bchile\b") { $pais = "chile" }
  elseif ($n -match "\bargentina\b") { $pais = "argentina" }
  elseif ($n -match "\baustralia\b") { $pais = "australia" }
  elseif ($n -match "\bnew zealand\b" -or $n -match "\bnz\b") { $pais = "nova zelandia" }

  $cor = "??"
  if ($n -match "\brose\b" -or $n -match "\brosado\b" -or $n -match "\brosato\b") { $cor = "rose" }
  elseif ($n -match "\bwhite\b" -or $n -match "\bblanc\b" -or $n -match "\bbianco\b" -or $n -match "\bbranco\b") { $cor = "branco" }
  elseif ($n -match "\bred\b" -or $n -match "\brouge\b" -or $n -match "\brosso\b" -or $n -match "\btinto\b" -or $n -match "\bvermelh\b") { $cor = "vermelho" }

  return "W|??|??|$pais|$cor"
}

$root = Split-Path -Parent $PSScriptRoot
$inPath = Join-Path $PSScriptRoot "lote_1000.txt"
$grokPath = Join-Path $PSScriptRoot "lotegrok.txt"
$outPath = Join-Path $PSScriptRoot "lote_1000_final.txt"

if (-not (Test-Path $inPath)) { throw "Input nao encontrado: $inPath" }
if (-not (Test-Path $grokPath)) { throw "Resposta Grok nao encontrada: $grokPath" }

$inputs = Get-Content $inPath | Where-Object { $_.Trim() -ne "" }
if ($inputs.Count -ne 1000) { throw "Esperado 1000 itens em lote_1000.txt, achei $($inputs.Count)" }
$inputsNorm = $inputs | ForEach-Object { Norm $_ }

# Parse do Grok: guarda so o "conteudo" (X / S / W|...)
$raw = Get-Content $grokPath | Where-Object { $_.Trim() -ne "" }
$outEntries = New-Object System.Collections.Generic.List[object]
foreach ($ln in $raw) {
  if ($ln -match '^\s*(\d+)\.\s+(.+?)\s*$') {
    $outEntries.Add([pscustomobject]@{
      raw = $ln
      content = $matches[2].Trim()
    })
  }
}

if ($outEntries.Count -lt 900) {
  Write-Warning "Poucas linhas parseadas do Grok: $($outEntries.Count). Verifique o arquivo: $grokPath"
}

$LOOKAHEAD = 60
$THRESH = 0.60
$assigned = New-Object 'object[]' 1000
$i = 0
$k = 0
$skippedTemplates = 0
$missingFromGrok = 0

while ($i -lt 1000 -and $k -lt $outEntries.Count) {
  $c = $outEntries[$k].content

  # Tenta interpretar tokens do W|... para alinhar com o item correto.
  $tokens = @()
  $isWine = $false
  if ($c.StartsWith("W|")) {
    $isWine = $true
    # Remove possivel "|=N" no final antes de tokenizar
    $base = ($c -replace '\|=\d+\s*$', '') -replace '\|=M\s*$', ''
    $parts = $base.Split("|")
    if ($parts.Length -ge 3) {
      $prod = Norm $parts[1]
      $vin = Norm $parts[2]
      $tokens = @((((@($prod, $vin) -join " ") -split " ") | Where-Object { $_ -ne "" }))
    }
  }

  $matchedIndex = $null
  if ($isWine -and $tokens.Count -gt 0) {
    $bestScore = 0.0
    $bestJ = $null
    for ($j = $i; $j -le [Math]::Min(999, $i + $LOOKAHEAD); $j++) {
      $score = Get-TokenScore $inputsNorm[$j] $tokens
      if ($score -gt $bestScore) {
        $bestScore = $score
        $bestJ = $j
        if ($bestScore -ge 1.0) { break }
      }
    }

    if ($bestJ -ne $null -and $bestScore -ge $THRESH) {
      $matchedIndex = $bestJ
    }
  }

  # Se nao casou, pode ser uma linha "template" (ex.: "X", "S", ou exemplos do prompt).
  if ($matchedIndex -eq $null) {
    # Heuristica simples: se for X/S e o item atual nao parece X/S, assume template e pula.
    if ($c -eq "X" -or $c -eq "S") {
      $skippedTemplates++
      $k++
      continue
    }

    # Se for W|... mas nao casa com nenhum item proximo, provavelmente e exemplo do prompt.
    if ($c.StartsWith("W|")) {
      $skippedTemplates++
      $k++
      continue
    }

    # Qualquer outra coisa: pula.
    $skippedTemplates++
    $k++
    continue
  }

  # Preenche itens sem saida ate o match encontrado.
  while ($i -lt $matchedIndex) {
    $assigned[$i] = Guess-Fallback $inputs[$i]
    $missingFromGrok++
    $i++
  }

  # Atribui o conteudo ao item matchedIndex.
  # Remove referencia de duplicata antiga (vamos recalcular duplicatas depois).
  $assigned[$matchedIndex] = ($c -replace '\|=\d+\s*$', '') -replace '\|=M\s*$', ''
  $i = $matchedIndex + 1
  $k++
}

# Se sobrou input sem classificacao (fim do Grok), fallback.
while ($i -lt 1000) {
  $assigned[$i] = Guess-Fallback $inputs[$i]
  $missingFromGrok++
  $i++
}

# Recalcular duplicatas por igualdade exata do item de entrada.
$firstSeen = @{}
for ($idx = 0; $idx -lt 1000; $idx++) {
  $key = $inputsNorm[$idx]
  if (-not $firstSeen.ContainsKey($key)) {
    $firstSeen[$key] = $idx
    continue
  }
  $origIdx = [int]$firstSeen[$key]
  $base = [string]$assigned[$origIdx]
  if ($base -eq "X" -or $base -eq "S") {
    $assigned[$idx] = $base
  } else {
    $assigned[$idx] = "$base|=$($origIdx + 1)"
  }
}

# Escreve saida final (1000 linhas numeradas)
$outLines = New-Object System.Collections.Generic.List[string]
for ($idx = 0; $idx -lt 1000; $idx++) {
  $outLines.Add("$($idx + 1). $($assigned[$idx])")
}
$outLines | Set-Content -Encoding utf8 $outPath

Write-Host "OK: gerado $outPath"
Write-Host "  inputs=1000 grok_parsed=$($outEntries.Count)"
Write-Host "  skipped_templates=$skippedTemplates"
Write-Host "  missing_filled=$missingFromGrok"
