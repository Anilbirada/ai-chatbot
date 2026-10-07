# Question Paper Maker - DSATM Premium IAT-2

A complete Flask + plain HTML/CSS/JS web app for turning a photographed, uploaded, spoken, or typed question paper into a premium Dayananda Sagar Academy of Technology and Management style IAT-2 PDF.

The visual template is based on the supplied sample PDF: DSATM header, Information Science and Engineering department, Second Internal Assessment Test (IAT-2), subject metadata, RBT levels, instructions, paired OR questions, course outcomes, and per-page footer. The supplied crest and NAAC A+ seal are used directly from `public/logo-left.png` and `public/logo-right.png`.

## 1. Important: create your own Anthropic API key

I do **not** create or include an Anthropic API key in this project. You create your own key and put it in `.env`.

1. Open **https://console.anthropic.com/**
2. Go to **Plans & Billing** and add credits if your account needs them.
3. Open **Settings > API Keys**.
4. Click **Create Key**.
5. Copy the key once and keep it private.
6. In the project folder, make a file named `.env` from `.env.example` and set:

```env
ANTHROPIC_API_KEY=your_real_key_here
```

You can also set `APP_PASSWORD` and `RATE_LIMIT_PER_HOUR` there.

## 2. Project structure

```text
question-paper-maker/
├─ app.py
├─ requirements.txt
├─ Procfile
├─ .env.example
├─ .gitignore
├─ start-windows.bat
├─ start-mac-linux.sh
├─ README.md
└─ public/
   ├─ index.html
   ├─ logo-left.png
   └─ logo-right.png
```

## 3. Run locally in VS Code - Windows

Open the project folder in VS Code.

### Option A: one-click script

Double-click `start-windows.bat`.

The script will:

- create `.venv`
- install the three Python dependencies
- create `.env` from `.env.example` if needed
- start Flask on port 3000

Then open:

**http://localhost:3000**

### Option B: terminal commands

Open the VS Code terminal and run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Then open **http://localhost:3000**.

## 4. Run on macOS / Linux

```bash
chmod +x start-mac-linux.sh
./start-mac-linux.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open **http://localhost:3000**.

## 5. How the app works

### Add a source

- **Take photo** uses the browser camera with `getUserMedia`.
- **Upload image** accepts a JPG/PNG image.
- Drag and drop also works.
- The browser shrinks the image to a maximum dimension of **1800 px** and sends a JPEG base64 image block.
- A thumbnail is shown with a **Remove** button.

### Speak questions

Click **Speak questions**. Chrome's `SpeechRecognition` / `webkitSpeechRecognition` is used with the `en-IN` locale. The transcript is appended into the editable notes box, which also supports normal typing.

### Make / Update

The first run calls:

`POST /api/extract`

with the optional image plus a text prompt. The backend calls Anthropic's Messages API with:

- `x-api-key`
- `anthropic-version: 2023-06-01`
- model from `MODEL`
- default model: `claude-sonnet-5-5`
- `max_tokens: 8000`

The app expects JSON and extracts the first `{ ... }` object from the AI response.

After a paper exists, the main button becomes **Update paper**. New photos, speech, or typed notes are sent together with the current JSON and an update instruction so unrelated questions remain untouched.

## 6. Security built into the backend

### Optional HTTP Basic Auth

Set:

```env
APP_PASSWORD=your_private_password
```

Any username is accepted as long as the password matches. Leave it blank to disable auth.

### Per-IP rate limit

Default:

```env
RATE_LIMIT_PER_HOUR=40
```

The backend uses an in-memory rolling window and reads `X-Forwarded-For` when present (useful behind Railway's proxy).

### Missing API key / AI errors

The API returns clear JSON errors for:

- missing `ANTHROPIC_API_KEY`
- rate limits
- malformed requests
- provider errors
- invalid AI JSON

### Static file safety

The public file route resolves the requested path and refuses traversal outside the `public/` directory.

## 7. Premium template features

The generated preview uses:

- navy `#0B1F3A`
- gold `#C9A24B`
- cream `#FBF8F1`
- soft blue `#EEF2F8`
- line `#C9D1DF`

The layout contains:

- DSATM crest on the left
- NAAC A+ seal on the right
- autonomous institute text
- accreditation panel
- Department of Information Science and Engineering
- IAT-2 title bar
- 2-column question-paper metadata grid
- RBT levels row
- instruction row
- premium question table with Question-1 / OR / Question-2 pattern
- navy numbered circles
- marks / CO / RBT columns
- network/graph figure SVGs when the model returns a figure
- Course Outcomes section
- footer on every page
- A4 page size at exactly **794 x 1123 px**

## 8. Live editing

Click directly on:

- department text
- subject
- subject code
- semester
- max marks
- batch
- duration
- date
- teaching department
- RBT levels
- instructions
- every question
- marks
- CO
- RBT
- course outcome code and description

Edits are written back into the in-memory JSON object. **Re-fit pages** rebuilds pagination without changing your content.

## 9. Pagination

Question pairs are kept together. Each `.q-group` is measured after being added to the A4 page. If adding a complete pair would exceed the content limit, the whole pair moves to the next page. Course Outcomes are treated as one block and are moved to a new page when necessary.

## 10. PDF export

Click **Download PDF**.

The browser first rebuilds pagination, then renders each `.page` with:

- `html2canvas` at scale 2
- `jsPDF`
- one A4 page per `.page` element

The output filename is:

`Question_Paper_IAT2.pdf`

## 11. GitHub

Create a new repository, then from the project folder:

```bash
git init
git add .
git commit -m "Build premium question paper maker"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/question-paper-maker.git
git push -u origin main
```

**Never commit `.env`.** It is ignored by `.gitignore`.

## 12. Deploy on Render

The repository includes `render.yaml` with the Python web service build command,
Gunicorn start command, and `/health` health check.

For a new deployment, create a **Blueprint** in Render from this repository and
apply the `render.yaml` settings. Adding `render.yaml` does not by itself update
an existing service unless that service is managed as a Blueprint. For an
existing Web Service, open **Settings > Build & Deploy** and set:

- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120`
- **Health Check Path:** `/health`

The Start Command must be the Gunicorn command above, not your GitHub username or
repository name. Under **Environment**, add `ANTHROPIC_API_KEY` and any optional
variables described below. Then save the changes and trigger a deploy.

## 13. Deploy on Railway

1. Create a Railway project.
2. Deploy from your GitHub repository.
3. Railway will use the included `Procfile`:

```text
web: gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120
```

4. Add these Variables in Railway:

```text
ANTHROPIC_API_KEY = your_real_key
APP_PASSWORD = your_optional_password
MODEL = claude-sonnet-5-5
RATE_LIMIT_PER_HOUR = 40
```

You do **not** need to create an Anthropic key inside Railway; create it in the Anthropic Console and paste it into the Railway variable.

5. Open **Settings > Networking > Generate Domain**.
6. Open the generated Railway domain.

## 14. Health check

Open:

`https://YOUR_DOMAIN/health`

or locally:

`http://localhost:3000/health`

The response tells you whether the AI key is configured, whether password protection is enabled, the rate limit, and the selected model.

## 15. Recommended first test

Use the supplied sample paper image or a clear photo of one. You can also paste text such as:

```text
question 1: Illustrate and infer data link layer design issues with suitable examples, 10 marks, CO2, L2.
question 2: Infer short notes on the HDLC protocol and Point-to-Point Protocol, 10 marks, CO2, L2.
```

The app should produce the same two-choice grouping pattern used by the supplied sample IAT-2 paper.

## 16. Notes on browser permissions

- Camera access normally requires **localhost** or **HTTPS**.
- Speech recognition is browser-dependent; current Chrome builds are recommended.
- PDF export runs in the browser, so the CDN libraries must load. An internet connection is recommended for export.

## 17. No API key is included

There is deliberately **no real Anthropic secret** anywhere in these files. You must create your own Anthropic API key and add it locally in `.env` or in your hosting provider's environment variables.
