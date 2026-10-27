<#
Sends one month of BBM reports to the local API the way Darwinbox does: one call a week with about 200 reports.
Pick the weeks to send with -Week, and send the others another time.

  week 1  EREP_51001 .. EREP_51200  items EXP_61001 onwards
  week 2  EREP_52001 .. EREP_52200  items EXP_62001 onwards
  week 3  EREP_53001 .. EREP_53200  items EXP_63001 onwards
  week 4  EREP_54001 .. EREP_54200  items EXP_64001 onwards
(codes EREP_5<week><number>, 200 a week unless -ReportsPerWeek says otherwise; the item ids are numbered across the
week, like Darwinbox's expense ids)

The employees are 06300101 .. 06300400 (the same as the month seed). Each report copies one of the 68 sample reports
of curl-1..4.txt (month-reports.json): its items with their receipt files, and its grand total. So the OCR results mix like theirs:
mostly approved, some needing review.

COST: while the OCR worker runs, every new report is one Claude OCR run (about 25 seconds each, on your Claude
usage or the ANTHROPIC_API_KEY). One week of 200 reports is 200 runs, about an hour and a half of reading; the whole
month is 800. Stop the worker first if you only want the reports (they then stay "Processing").
Sending a week again stores nothing new ("unchanged") and costs nothing.

The API stamps the time it receives the reports, so they belong to the current month (WIB). For a finished month
with OCR results that costs nothing, use the seed backend/database/seeds/dummy_month.sql (September 2026).

Run it from the repository root while the API is running:
  powershell -ExecutionPolicy Bypass -File curl-testing\send_month.ps1 -Week 1
  powershell -ExecutionPolicy Bypass -File curl-testing\send_month.ps1 -Week 2,3,4 -Yes
#>
param(
    [string[]] $Week = @('1'),                          # the weeks to send: 1, 2, 3 or 4, several separated by commas
    [ValidateRange(1, 250)] [int] $ReportsPerWeek = 200,
    [string] $Api = 'http://127.0.0.1:5000',          # the API; the receipt files are downloaded from it too
    [switch] $Yes                                       # send without asking first
)
$ErrorActionPreference = 'Stop'
$BatchSize = 300  # reports per request (the API takes any number; a week fits in one)

# (ForEach-Object: Windows PowerShell's ConvertFrom-Json passes the whole array on as one object)
$templates = @(Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'month-reports.json') | ConvertFrom-Json |
    ForEach-Object { $_ })
$Api = $Api.TrimEnd('/')
# (split here: powershell -File passes "-Week 2,3,4" as the one text "2,3,4")
$weeks = @($Week -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Sort-Object -Unique)
foreach ($w in $weeks) {
    if ($w -notmatch '^[1-4]$') { Write-Host "-Week takes 1, 2, 3 or 4 (several: -Week 2,3,4), not '$w'." -ForegroundColor Red; exit 1 }
}
$weeks = @($weeks | ForEach-Object { [int]$_ })
$total = $weeks.Count * $ReportsPerWeek

"Week(s) $($weeks -join ', '): $total reports to $Api, in requests of $BatchSize."
"While the OCR worker runs, every new report is one Claude OCR run: up to $total runs, about $([math]::Ceiling($total * 25 / 60)) minutes."
if (-not $Yes -and (Read-Host 'Send them? (y/N)') -notmatch '^(y|yes)$') {
    'Nothing sent.'
    return
}

foreach ($w in $weeks) {
    $itemNo = 60000 + $w * 1000  # the week's last item number so far (fewer than 400 items a week)
    $reports = @(foreach ($i in 1..$ReportsPerWeek) {
        $n = ($w - 1) * $ReportsPerWeek + $i  # the report's number in the month
        $template = $templates[($n - 1) % $templates.Count]
        $code = 'EREP_5{0}{1:D3}' -f $w, $i
        $employee = 101 + ($n - 1) % 300
        $items = @(foreach ($source in @($template.items)) {
            $itemNo++
            $item = [ordered]@{ item_id = "EXP_$itemNo" }
            foreach ($field in $source.PSObject.Properties) {
                if ($field.Name -ne 'file') { $item[$field.Name] = $field.Value }
            }
            $item['attachments'] = @([ordered]@{ name = $source.file; url = "$Api/api/dummy-receipts/$($source.file)" })
            $item
        })
        [ordered]@{
            reimbursement_code = $code
            employee           = [ordered]@{ employee_no = '0630{0:D4}' -f $employee; name = "Employee $employee" }
            grand_total        = $template.grand_total
            items              = $items
        }
    })

    $requests = [math]::Ceiling($reports.Count / $BatchSize)
    for ($r = 0; $r -lt $requests; $r++) {
        $first = $r * $BatchSize
        $last = [math]::Min($first + $BatchSize, $reports.Count) - 1
        $body = ConvertTo-Json @{ reimbursements = @($reports[$first..$last]) } -Depth 10 -Compress
        $watch = [Diagnostics.Stopwatch]::StartNew()
        try {
            $response = Invoke-RestMethod -Method Post -Uri "$Api/api/reimbursements" -TimeoutSec 900 `
                -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
        } catch {
            $detail = if ($_.ErrorDetails) { $_.ErrorDetails.Message } else { $_.Exception.Message }
            Write-Host "Week $w, request $($r + 1) of $requests failed: $detail" -ForegroundColor Red
            exit 1
        }
        $counts = ($response.results | Group-Object status | ForEach-Object { "$($_.Name) $($_.Count)" }) -join ', '
        "Week $w, request $($r + 1) of ${requests}: $($reports[$first].reimbursement_code) .. " +
            "$($reports[$last].reimbursement_code): $counts ($([math]::Round($watch.Elapsed.TotalSeconds, 1)) s)"
        $rejected = @($response.results | Where-Object status -eq 'rejected')
        foreach ($result in ($rejected | Select-Object -First 5)) {
            $why = ($result.errors | ForEach-Object { "$($_.field) $($_.message)" }) -join '; '
            Write-Host "  $($result.reimbursement_code) rejected: $why" -ForegroundColor Yellow
        }
        if ($rejected.Count -gt 5) { Write-Host "  ... and $($rejected.Count - 5) more rejected" -ForegroundColor Yellow }
    }
}
