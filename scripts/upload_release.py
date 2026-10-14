import os
import sys
import json
import urllib.request

REPO = "abishxavier/prayer-app-backend"
TAG = "v1.1.7"
NAME = "v1.1.7 - Strict Private Meetings & Cumulative Direct Update"
BODY = """### What's New in v1.1.7

- **Strict Private Meetings**: When scheduling a meeting for selected members, only the invited participants and the host can view and join the call. Non-invited users are strictly blocked.
- **Visual Privacy Badges**: Clear "Private (Invited Only)" badges on meeting cards and scheduler details.
- **Selective Auto-Ringer**: Both manual rings and automated scheduled rings notify only the invited participants.
- **Direct Cumulative Updates**: Any older app version instantly jumps directly to the latest release in one single update.
- **Instant Member Loading**: Optimized community directory with offline caching and instant search by registration name.
- **WebRTC & Call Stability**: High-performance audio/video rendering and Agora AccessToken2 credentials."""

APK_PATH = r"d:\prayer_app\releases\v1.1.7\prayer_app_v1.1.7.apk"
ASSET_NAME = "prayer_app.apk"

# Get token from git credential
def get_github_token():
    import subprocess
    proc = subprocess.Popen(["git", "credential", "fill"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    out, _ = proc.communicate(input="protocol=https\nhost=github.com\n")
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return None

token = get_github_token()
if not token:
    print("Could not obtain GitHub token from git credentials!")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {token}",
    "User-Agent": "PrayerAppDeployer",
    "Accept": "application/vnd.github.v3+json"
}

# 1. Check if release already exists
print(f"Checking existing release for {TAG}...")
req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}", headers=headers)
release = None
try:
    with urllib.request.urlopen(req) as resp:
        release = json.loads(resp.read().decode())
        print(f"Found existing release ID {release['id']}")
except urllib.error.HTTPError as e:
    if e.code == 404:
        print("Release does not exist yet. Creating...")
    else:
        raise

if not release:
    create_payload = json.dumps({
        "tag_name": TAG,
        "target_commitish": "master",
        "name": NAME,
        "body": BODY,
        "draft": False,
        "prerelease": False
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases",
        data=create_payload,
        headers={**headers, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        release = json.loads(resp.read().decode())
        print(f"Created release ID {release['id']}")

upload_url_template = release["upload_url"] # e.g. https://uploads.github.com/.../assets{?name,label}
upload_base = upload_url_template.split("{")[0]

# Check existing assets
for asset in release.get("assets", []):
    if asset["name"] == ASSET_NAME:
        print(f"Asset {ASSET_NAME} already exists (ID {asset['id']}). Deleting old asset first...")
        del_req = urllib.request.Request(
            asset["url"],
            headers=headers,
            method="DELETE"
        )
        with urllib.request.urlopen(del_req) as del_resp:
            print("Deleted old asset.")

# 2. Upload APK file
apk_size = os.path.getsize(APK_PATH)
print(f"Uploading {ASSET_NAME} ({apk_size / (1024*1024):.1f} MB) to {upload_base}...")

upload_url = f"{upload_base}?name={ASSET_NAME}"
with open(APK_PATH, "rb") as f:
    apk_data = f.read()

upload_req = urllib.request.Request(
    upload_url,
    data=apk_data,
    headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "PrayerAppDeployer",
        "Content-Type": "application/vnd.android.package-archive",
        "Content-Length": str(apk_size)
    }
)

with urllib.request.urlopen(upload_req) as resp:
    asset_data = json.loads(resp.read().decode())
    print("SUCCESS! Asset uploaded.")
    print("Download URL:", asset_data.get("browser_download_url"))
