# Google Cloud Run Deployment Guide

### Deployment Architecture

```
┌─────────────────────────────┐
│   Cloud Run Container       │
│                             │
│  ┌──────────┐  ┌─────────┐  │
│  │ FastAPI  │  │ ChromaDB│  │
│  │  server  │  │ (37 MB) │  │
│  └──────────┘  └─────────┘  │
└─────────────────────────────┘
```

**Highlights:**
- FastAPI server and ChromaDB are bundled into a single container
- ChromaDB is generated automatically at build time (1,130 chunks)
- Stateless container, autoscales on Cloud Run
- Stays within the free tier for typical traffic

### Deployment Flow

```
push code (main)
    ↓
GitHub Actions starts
    ↓
Docker build + ingestion runs automatically
    ↓
Image contains a fully populated ChromaDB
    ↓
Cloud Run deploy complete
```

---

## 🔧 Prerequisites

### What you need
- ✅ Google Cloud account
- ✅ Billing enabled (free tier is fine — $300 starter credit available)
- ✅ GitHub account
- ✅ OpenAI API key

### Local environment
- Docker Desktop installed
- Git installed

---

## ☁️ Google Cloud Setup

### 1. Open Google Cloud Console
👉 https://console.cloud.google.com

### 2. Create a new project
Example project ID: `bbumate-api-1`

### 3. Open Cloud Shell
Click the `>_` icon in the top-right (or hit `` Ctrl + ` ``)

### 4. Run the environment setup script

```bash
# Set project ID (replace with your real project ID)
export PROJECT_ID="your-project-id"
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com

# Create the Artifact Registry repository
gcloud artifacts repositories create bbumate-api \
  --repository-format=docker \
  --location=asia-northeast1 \
  --description="Docker repository for Bbumate API"

# Create a service account
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions Deployer"

# Grant required roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Create a service account key
gcloud iam service-accounts keys create key.json \
  --iam-account=github-actions@${PROJECT_ID}.iam.gserviceaccount.com

# Print the key contents
cat key.json
```

### 5. Save the service account key
- Copy the entire contents of `key.json`
- Store it somewhere safe (you'll paste it into a GitHub Secret)

---

## 🔐 GitHub Secrets & Variables

### Where to set them
Repository → Settings → Secrets and variables → Actions

### Required Secrets (sensitive)

Click **New repository secret** and add:

| Secret name | Example value | Description |
|-------------|---------------|-------------|
| `GCP_PROJECT_ID` | `bbumate-api-1` | Google Cloud project ID |
| `GCP_SA_KEY` | entire contents of `key.json` | Service account key (JSON) |
| `OPENAI_API_KEY` | `sk-xxxxxxxxxxxxx` | OpenAI API key |

### Required Variables (configuration)

Switch to the **Variables** tab, click **New repository variable**:

| Variable name | Value | Description |
|---------------|-------|-------------|
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `OPENAI_CHAT_MODEL` | `gpt-4` | Chat model |

### Optional Secrets

| Secret name | Required? | Description |
|-------------|-----------|-------------|
| `TAVILY_API_KEY` | ❌ Optional | Mock web search is used by default (`USE_MOCK_WEB_SEARCH=true`) |

---

## 🧪 Local Testing

Before deploying, smoke-test the Docker image locally.

### 1. Load environment variables
```bash
source .env
```

### 2. Build the Docker image
```bash
docker build \
  --build-arg OPENAI_API_KEY="$OPENAI_API_KEY" \
  --build-arg OPENAI_EMBEDDING_MODEL="$OPENAI_EMBEDDING_MODEL" \
  --build-arg OPENAI_CHAT_MODEL="$OPENAI_CHAT_MODEL" \
  -t bbumate-api:test .
```

**What runs during the build:**
- `run_ingestion.py` executes
- All 5 domains (d001–d005) are processed
- ChromaDB is created (~3 minutes)
- Total: 1,130 chunks generated

### 3. Run the container
```bash
docker run -p 8080:8080 --env-file .env bbumate-api:test
```

### 4. Test
```bash
# Health check
curl http://localhost:8080/api/health

# Query
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the newlywed jeonse loan?"}'
```

### 5. Cleanup
```bash
# Stop the container
docker stop $(docker ps -q --filter ancestor=bbumate-api:test)
```

---

## 🚀 Deploy

### Automatic deploy (recommended)

Push to `main` and GitHub Actions ships it.

**Verify the deploy:**
1. Watch progress in GitHub → **Actions** tab
2. Total time: about 5–10 minutes (build ~3 min + deploy ~2 min)
3. After it finishes, grab the service URL from the Cloud Run console

---

## 🛠️ Operations

### Check service status
```bash
gcloud run services describe bbumate-api --region asia-northeast1
```

### Get the deployed service URL
```bash
gcloud run services describe bbumate-api \
  --region asia-northeast1 \
  --format 'value(status.url)'
```

---

## 🆘 Troubleshooting

### 1. Build fails: API key error

**Symptom:**
```
ERROR: OPENAI_API_KEY not found
```

**Fix:**
- Confirm `OPENAI_API_KEY` is set in GitHub Secrets
- Double-check the exact secret name (it is case-sensitive)

### 2. Out of memory

**Symptom:**
```
Container failed to start. Failed to start and listen on the port
```

**Fix:**
```bash
gcloud run services update bbumate-api \
  --memory 1Gi \
  --region asia-northeast1
```

### 3. Slow cold start

**Symptom:**
- First request after idle takes 5–10 s

**Fix A (costs more):**
```bash
gcloud run services update bbumate-api \
  --min-instances 1 \
  --region asia-northeast1
```

**Fix B (free):**
- Configure Cloud Scheduler to ping `/api/health` every 5 minutes

### 4. Updating the ChromaDB corpus

**How:**
1. Edit the PDF/HTML files under `data/`
2. Push to GitHub
3. The workflow rebuilds and redeploys automatically

**Note:**
- A fresh ChromaDB is generated on every build
- Guarantees data consistency across deploys
- `chroma_storage/` does not need to be committed to git

### 5. `TAVILY_API_KEY` warning

**Symptom:**
```
TAVILY_API_KEY not found
```

**Fix:**
- The default config uses `USE_MOCK_WEB_SEARCH=true`, so this is safe to ignore
- If you want real web search, register a Tavily API key

---

## ✅ Deployment Verification

### 1. Cloud Run console
👉 https://console.cloud.google.com/run

### 2. Hit the service URL
```bash
# Fetch the URL
gcloud run services describe bbumate-api \
  --region asia-northeast1 \
  --format 'value(status.url)'

# Health check
curl https://your-service-url/api/health
```

### 3. Query the API
```bash
curl -X POST https://your-service-url/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the newlywed jeonse loan?"}'
```

**Expected response:**
```json
{
  "answer": "The newlywed jeonse loan is...",
  "answer_md": "# Answer\n...",
  "answer_html": "<h1>Answer</h1>...",
  "sources": [...]
}
```

---

## 📚 Further Reading

- [Cloud Run docs](https://cloud.google.com/run/docs)
- [OpenAI API docs](https://platform.openai.com/docs)

---

## 🎓 Appendix: Architecture Details

### How ChromaDB is generated at build time

**Dockerfile:**
```dockerfile
# Receive API key as a build arg
ARG OPENAI_API_KEY

# Run ingestion at build time
RUN OPENAI_API_KEY=${OPENAI_API_KEY} \
    python run_ingestion.py

# Verify the generated ChromaDB
RUN ls -la chroma_storage/
```

**Why this design:**
- ✅ Does not depend on the local environment
- ✅ Each build produces identical data
- ✅ Eliminates corpus-drift between teammates
- ✅ No need to commit ChromaDB to git

**Indexed data:**
- d001: 216 chunks (housing policy)
- d002: 184 chunks (loan policy)
- d003: 619 chunks (family / welfare)
- d004: 83 chunks (corporate benefits)
- d005: 28 chunks (subscription / special supply)
- **Total: 1,130 chunks (~37 MB)**

---

**Deployment complete! 🎉**
