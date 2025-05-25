# Slidesolve Backend

A FastAPI backend that accepts PDF, PPTX, or DOCX files, extracts text, and generates questions using OpenAI.

## How to Run Locally
```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Deployment
Deploy to Render with:
- Build Command: pip install -r requirements.txt
- Start Command: uvicorn main:app --host 0.0.0.0 --port 10000
- Add OPENAI_API_KEY in Environment Variables

## Endpoints
- POST /upload-slide/
- POST /generate-questions/