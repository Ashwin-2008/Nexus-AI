# NEXUS AI Backend

FastAPI backend for NEXUS AI – Enterprise Multi-Source Knowledge Intelligence and Agentic RAG Platform.

## Run (dev)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```
