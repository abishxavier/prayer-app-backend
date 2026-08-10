# PowerShell helper to move sensitive files out of the repository and replace .env with a placeholder.
# Run this from D:\prayer_app\prayer_app_backend

$cwd = Get-Location
Write-Output "Running secrets cleanup in $cwd"

$envFile = Join-Path $cwd '.env'
$envLocal = Join-Path $cwd '.env.local'
$firebaseJson = Join-Path $cwd 'app\core\firebase-service-account.json'
$firebaseSecret = Join-Path $cwd 'app\core\firebase-service-account.json.secret'

if (Test-Path $envFile) {
    Write-Output "Moving .env -> .env.local"
    Move-Item -Path $envFile -Destination $envLocal -Force
} else {
    Write-Output ".env not found; nothing to move."
}

# Create a placeholder .env so the project still has a sample to edit
$placeholder = @"
# Placeholder .env created by secrets_cleanup.ps1
DATABASE_URL=postgresql://<db_user>:<db_password>@<db_host>:5432/<db_name>
JWT_SECRET=<your_jwt_secret_here>
FIREBASE_CREDENTIALS_PATH=app/core/firebase-service-account.json
"@

$placeholderPath = Join-Path $cwd '.env'
Set-Content -Path $placeholderPath -Value $placeholder -Encoding UTF8
Write-Output "Wrote placeholder .env. Update .env.local manually and keep it secure."

if (Test-Path $firebaseJson) {
    Write-Output "Renaming firebase service account JSON to hide it"
    Move-Item -Path $firebaseJson -Destination $firebaseSecret -Force
    Write-Output "Moved to $firebaseSecret"
} else {
    Write-Output "Firebase service account JSON not found at $firebaseJson"
}

Write-Output "Secrets cleanup complete. Verify .env.local contains your real secrets and store it securely."