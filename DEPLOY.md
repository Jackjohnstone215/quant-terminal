# Deploying to Streamlit Community Cloud (free)

Your app is already committed to a local git repo and is one push away from being live
online — shareable by link and usable on your phone. Here's the whole path.

## What's already done for you
- ✅ `requirements.txt` (pinned to the exact versions we tested)
- ✅ `.gitignore` (keeps your real portfolio holdings and API keys OUT of the repo)
- ✅ Local git repo initialized + first commit made
- ✅ App verified working end to end

## Step 1 — Make a GitHub account (if you don't have one)
Go to https://github.com and sign up (free). Verify your email.

## Step 2 — Create an empty repository
On GitHub: click **+** (top right) → **New repository**.
- Name: `quant-terminal` (or anything)
- Visibility: **Private** is safest. (Streamlit Cloud can deploy from private repos.)
- Do **NOT** add a README/.gitignore (you already have them).
- Click **Create repository**.

## Step 3 — Push your code
GitHub will show a URL like `https://github.com/YOUR-NAME/quant-terminal.git`.
In a terminal, from the app folder, run:

```powershell
cd "C:\Users\jjohnstone\Desktop\investment website research"
git remote add origin https://github.com/YOUR-NAME/quant-terminal.git
git push -u origin main
```
(The first push will ask you to log in to GitHub — use the browser prompt.)

## Step 4 — Deploy on Streamlit Cloud
1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app** → **Deploy a public app from a repo** (works for private too).
3. Pick your repo, branch `main`, main file `dashboard.py`.
4. Click **Deploy**. First build takes ~2-3 minutes.

## Step 5 — Add your OpenAI key (for the AI Analyst tab)
In the deployed app: **Manage app** → **Settings** → **Secrets**, and paste:
```toml
OPENAI_API_KEY = "sk-your-key-here"
OPENAI_MODEL = "gpt-4o-mini"
```
Save. The app reboots and the 🤖 AI Analyst tab turns on.

## Notes / gotchas
- **Your portfolio holdings** are git-ignored, so the deployed app starts with an empty
  portfolio. Re-enter holdings in the app. (Streamlit Cloud storage resets on reboot, so
  for a permanent online portfolio you'd later add a small database — a future upgrade.)
- **Yahoo Finance** rate-limits harder from cloud IPs than from your home network. If scans
  feel slow online, scan fewer stocks at a time.
- To push future changes: `git add -A && git commit -m "..." && git push`. Streamlit Cloud
  redeploys automatically.
