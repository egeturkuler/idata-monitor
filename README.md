# iDATA Duyurular Monitor

Automatically checks [iDATA İtalya Duyurular](https://www.idata.com.tr/ita/tr/p/duyurular) every 2 hours and sends an email notification when new announcements are posted.

## How it works

1. GitHub Actions runs `monitor.py` on a schedule
2. The script scrapes the announcements page
3. New announcements (not seen before) trigger an HTML email to all configured recipients
4. The list of seen announcement IDs is saved back to `state.json` in the repo

---

## Setup

### 1. Create a GitHub repository

```bash
git init idata-monitor
cd idata-monitor
# copy all files here
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/idata-monitor.git
git push -u origin main
```

### 2. Set up Gmail App Password (recommended)

1. Go to your Google Account → **Security** → **2-Step Verification** (must be ON)
2. Search for **App Passwords**
3. Create a new app password for "Mail"
4. Copy the 16-character password — this is your `SMTP_PASS`

> ⚠️ Do NOT use your real Gmail password. App Passwords are separate and revocable.

### 3. Add GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret Name     | Value                                          |
|-----------------|------------------------------------------------|
| `SMTP_USER`     | Your Gmail address, e.g. `you@gmail.com`       |
| `SMTP_PASS`     | The 16-char App Password from step 2           |
| `NOTIFY_EMAILS` | Comma-separated recipients: `a@x.com,b@y.com` |
| `SMTP_HOST`     | *(optional)* Defaults to `smtp.gmail.com`      |
| `SMTP_PORT`     | *(optional)* Defaults to `587`                 |

### 4. Enable GitHub Actions

Go to **Actions** tab in your repo → click **"I understand my workflows, go ahead and enable them"**

### 5. Test it manually

Go to **Actions** → **iDATA Announcement Monitor** → **Run workflow** → **Run workflow**

Check the logs to confirm it runs successfully.

---

## Configuration

### Change check frequency

Edit `.github/workflows/monitor.yml`, the `cron` line:

```yaml
- cron: "0 */2 * * *"   # every 2 hours (default)
- cron: "0 * * * *"     # every 1 hour
- cron: "*/30 * * * *"  # every 30 minutes
- cron: "0 8,12,18 * * *"  # at 8am, 12pm, 6pm UTC
```

> ⚠️ GitHub Actions free tier allows up to ~2000 minutes/month. Every 2 hours = ~360 runs/month (~6 min each), well within limits.

### Add or remove recipients

Update the `NOTIFY_EMAILS` secret in GitHub:
```
email1@example.com,email2@example.com,email3@example.com
```

---

## Running locally

```bash
pip install -r requirements.txt

export SMTP_USER="you@gmail.com"
export SMTP_PASS="your-app-password"
export NOTIFY_EMAILS="you@gmail.com,friend@example.com"

python monitor.py
```

---

## Files

```
idata-monitor/
├── monitor.py                    # Main scraper + emailer
├── state.json                    # Tracks seen announcement IDs (auto-updated)
├── requirements.txt
├── README.md
└── .github/
    └── workflows/
        └── monitor.yml           # GitHub Actions schedule
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Email not sent | Check GitHub Actions logs for errors. Verify secrets are set correctly. |
| "Less secure app" error | Use App Passwords, not your real password |
| No announcements found | The site may have changed its HTML structure. Open an issue or re-run `monitor.py` locally with `print(soup.prettify())` to inspect. |
| State not committed | Make sure the repo has `contents: write` permission in Actions settings |
