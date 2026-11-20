$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv venv --python 3.12 .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
    } else {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or uv, then run again.' }
    }
}
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
} else {
    & .venv\Scripts\python.exe -m pip install -r requirements.txt
}
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
