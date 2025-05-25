from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF
import io
from pptx import Presentation
from docx import Document
import openai

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

openai.api_key = os.getenv("OPENAI_API_KEY")

def extract_text_from_pdf(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = "".join([page.get_text() for page in doc])
    return text

def extract_text_from_pptx(file_bytes):
    prs = Presentation(io.BytesIO(file_bytes))
    text = "".join([shape.text for slide in prs.slides for shape in slide.shapes if hasattr(shape, "text")])
    return text

def extract_text_from_docx(file_bytes):
    doc = Document(io.BytesIO(file_bytes))
    text = "".join([para.text for para in doc.paragraphs])
    return text

@app.post("/upload-slide/")
async def upload_slide(file: UploadFile = File(...)):
    file_bytes = await file.read()
    if file.filename.endswith(".pdf"):
        text = extract_text_from_pdf(file_bytes)
    elif file.filename.endswith(".pptx"):
        text = extract_text_from_pptx(file_bytes)
    elif file.filename.endswith(".docx"):
        text = extract_text_from_docx(file_bytes)
    else:
        return {"error": "Unsupported file type"}
    return {"text": text}

@app.post("/generate-questions/")
async def generate_questions(text: str = Form(...)):
    prompt = f"Generate 5 study questions from the following text:
{text}"
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    questions = response['choices'][0]['message']['content']
    return {"questions": questions}