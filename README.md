# JobScout UK

Upload your CV → pick your LLM (Gemini / OpenAI / Claude) → tick the portals you want
(Reed / Adzuna / Indeed / LinkedIn) → press one of TWO buttons, watch the live progress bar,
and get your summary cards + Excel:

**Button 1 — Find my jobs:**
every matching UK job from the last week, ranked **High / Medium / Low** probability for YOUR CV,
with a tailored **email + cover letter draft** for the top matches, **CV improvement** advice,
and an automatic check of each employer against the official **GOV.UK sponsor register**.

Sources searched: **Reed (official API) + Adzuna (official API, aggregates most UK boards) +
Indeed and LinkedIn (public listings)** — each switchable with a checkbox.

**Button 2 — Sponsor companies scan:** licensed Skilled-Worker sponsor companies in YOUR
sectors (energy, retrofit, property...), **even if they have no advert today** — with licence
route and rating from the official GOV.UK register, an LLM fit-rating, a live-jobs-now check
(via Adzuna), verified company websites, public contact emails, a tailored speculative-application
draft per top company, a CV-improvements sheet, and one-click careers-page / LinkedIn links.
Second Excel: `JobScout_Sponsors_*.xlsx`. The finished report saves wherever you choose
(Save-As dialog on Chrome/Edge).

---

## Easiest way - no Python, for friends (Windows)

1. Download **`JobScoutUK.exe`** from the **Releases** page of this project (link supplied with the app)
2. Put it in its own folder (it creates `output/` and `config.json` next to itself)
3. Double-click it → your browser opens the dashboard → done
4. Windows SmartScreen may warn because the file is new and unsigned:
   click **More info → Run anyway** (the source code is fully open in this repository)

Inside the app, press **Test connection** after pasting each key — you get a green
"✓ Connected" the moment it works.

**About "logging in with my ChatGPT/Gemini username and password":** that is not possible —
OpenAI and Google do not allow programs to log in with consumer accounts, and a ChatGPT Plus
subscription does not include programmatic access. The equivalent of a password here is an
**API key**: a one-time copy-paste (2 minutes, links inside the app), saved on your computer,
then never touched again. Gemini's key is free.

---

## One-time setup from source (about 15 minutes, any OS)

### Step 1 - Install Python (if you don't have it)
1. Go to https://www.python.org/downloads/windows/
2. Download **Python 3.11 or newer** → run the installer
3. **IMPORTANT:** on the first installer screen, tick **"Add python.exe to PATH"** → Install Now

### Step 2 - Install JobScout
1. Unzip the `JobScoutUK` folder anywhere (e.g. `C:\JobScoutUK`)
2. Double-click **`setup.bat`** → wait for "Setup complete" (2–5 minutes)

### Step 3 - Get your free keys (copy each into the app later)
| Key | Where | Cost |
|---|---|---|
| **Gemini API key** (recommended LLM) | https://aistudio.google.com/apikey → "Create API key" | Free tier |
| **Reed API key** | https://www.reed.co.uk/developers/jobseeker → register → key is shown | Free |
| **Adzuna App ID + Key** | https://developer.adzuna.com/ → sign up → "Add app" | Free |
| OpenAI key (optional) | https://platform.openai.com/api-keys (needs billing set up — separate from ChatGPT Plus) | ~10–40p per run |
| Claude key (optional) | https://console.anthropic.com/ → API keys | ~10–40p per run |

### Step 4 - First run
1. Double-click **`run.bat`** → your browser opens the dashboard
2. Upload your CV (PDF/DOCX)
3. Pick provider **"Demo (offline)"** first → **Run** → confirms everything works with sample data, no keys needed
4. Then switch provider to **Gemini**, paste your keys (they save to `config.json` on your PC), open
   "Job-source keys" and paste Reed + Adzuna keys → **Run**
5. The Excel appears on the right and is also saved in the `output` folder

Every later use = double-click `run.bat`, upload CV, Run.

---

## What's in the Excel
- **Dashboard** – run summary and counts
- **Jobs** – every job, sorted High→Low: score, why it fits, CV gaps, salary, sponsor-register check, clickable link
- **Cover Letters** – email subject + body and a full cover letter for the top matches (drafts — personalise the first line!)
- **CV Improvements** – ordered list of concrete changes based on the gaps found this run
- **Read Me** – honest limitations

## Honest limitations (read once)
- **LinkedIn** has no public API; JobScout reads its public (logged-out) listings. Some runs will
  return few or no LinkedIn rows (rate limiting). Your LinkedIn account is never used or touched.
  This method is widely used but technically against LinkedIn's terms — if you prefer zero risk,
  it fails safe: the run simply continues with the other sources.
- **CWJobs / Totaljobs** block automated access; their inventory largely appears via Adzuna anyway.
- **Sponsor check** matches company names against the official register — "Not found" does not
  prove there is no licence (name variants are common). Always verify before applying:
  https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers
- **Scores are LLM judgements** to prioritise your time, not guarantees.
- **Nothing is auto-submitted.** The tool drafts; you review and send.

## Troubleshooting
- **"python is not recognised"** → reinstall Python and tick "Add to PATH" (Step 1.3)
- **Setup fails on python-jobspy** → your Python is older than 3.10; install 3.11+
- **No jobs found** → check Reed/Adzuna keys pasted correctly; widen "Posted within" to 14 days
- **Gemini error 429** → free-tier rate limit; wait a minute and re-run, or lower "Max jobs"
- **Firewall prompt on first run** → allow; the app only serves to your own browser (127.0.0.1)
- **A different LLM model** → edit the Model box (e.g. `gpt-4o`, `gemini-2.5-pro`, `claude-sonnet-4-5`)

## Costs per run (~60 jobs, 8 letters)
- Gemini free tier: **£0**
- OpenAI gpt-4o-mini or Claude Haiku: **~£0.10–£0.40**
- Reed, Adzuna, sponsor register: **free**
