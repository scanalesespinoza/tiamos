$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$ae = [System.Windows.Automation.AutomationElement]
$scope = [System.Windows.Automation.TreeScope]::Descendants
$selectPattern = [System.Windows.Automation.SelectionItemPattern]::Pattern

function Find-Terminal($window) {
    $condition = New-Object System.Windows.Automation.PropertyCondition($ae::ClassNameProperty, 'TermControl')
    return $window.FindFirst($scope, $condition)
}

while ($null -ne ($line = [Console]::ReadLine())) {
    try {
        $request = $line | ConvertFrom-Json
        $result = @()
        foreach ($handle in $request.windows) {
            $window = $ae::FromHandle([IntPtr][long]$handle)
            $condition = New-Object System.Windows.Automation.PropertyCondition($ae::ControlTypeProperty, [System.Windows.Automation.ControlType]::TabItem)
            $tabs = $window.FindAll($scope, $condition)
            $original = $null
            foreach ($tab in $tabs) {
                if ($tab.GetCurrentPattern($selectPattern).Current.IsSelected) { $original = $tab }
            }
            try {
                foreach ($tab in $tabs) {
                    $id = $tab.GetRuntimeId() -join ','
                    $pattern = $tab.GetCurrentPattern($selectPattern)
                    $selected = $original -and (($original.GetRuntimeId() -join ',') -eq $id)
                    if ($request.mode -eq 'select') {
                        if ($id -eq $request.tab_id) {
                            $pattern.Select()
                            $terminal = Find-Terminal $window
                            if ($terminal) { $terminal.SetFocus() }
                            $result += @{ hwnd = [long]$handle; tab_id = $id; selected = $true }
                        }
                        continue
                    }
                    $workspace = $null
                    $title = $null
                    # Inspect inactive tabs only once, then restore the user's tab.
                    if ($selected -or $request.inspect_all) {
                        if (-not $selected) {
                            $pattern.Select()
                            Start-Sleep -Milliseconds 100
                        }
                        $terminal = Find-Terminal $window
                        if ($terminal) {
                            $text = $terminal.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern).DocumentRange.GetText(-1)
                            # Return only the CLI footer's metadata, never transcript text.
                            foreach ($candidate in ($text -split '\r?\n' | Select-Object -Last 15)) {
                                $parts = $candidate -split ([char]0x00b7)
                                if ($parts.Count -ge 3 -and $parts[1].Trim() -match '^(~|[a-zA-Z]:\\|/)') {
                                    $workspace = $parts[1].Trim()
                                    $title = $parts[-1].Trim()
                                }
                            }
                            $text = $null
                        }
                    }
                    $result += @{ hwnd = [long]$handle; tab_id = $id; selected = $selected; workspace = $workspace; title = $title }
                }
            } finally {
                if ($request.mode -ne 'select' -and $original -and $request.inspect_all) {
                    $original.GetCurrentPattern($selectPattern).Select()
                }
            }
        }
        [Console]::WriteLine((@{ tabs = @($result) } | ConvertTo-Json -Compress -Depth 5))
    } catch {
        [Console]::WriteLine((@{ tabs = @(); error = $_.Exception.GetType().Name } | ConvertTo-Json -Compress))
    }
}
