$excel = New-Object -ComObject Excel.Application
.Visible = $false
.DisplayAlerts = $false
$wb = $excel.Workbooks.Open('c:\\EMERSON\\projetos antigravity\\Planos PM13-PM11\\CARG A OFICIAL.xlsb')
foreach ($ws in $wb.Worksheets) {
    Write-Host "Sheet: $($ws.Name)"
    $r1 = @()
    for ($c=1; $c -le 40; $c++) {
        $v = $ws.Cells.Item(1, $c).Value2
        if ($v) { $r1 += "[$c] $v" }
    }
    Write-Host "Headers: $($r1 -join ' | ')"
    Write-Host '---'
}
$wb.Close($false)
$excel.Quit()