import os
import io
import subprocess
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz            # PyMuPDF for PDF
from pptx import Presentation
from docx import Document
import openai

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

openai.api_key = os.getenv("OPENAI_API_KEY")

def convert_ppt_to_pptx(input_path: str, output_dir: str) -> str:
    """Use headless LibreOffice to convert .ppt → .pptx."""
    try:
        subprocess.run([
            "libreoffice",
            "--headless",
            "--convert-to", "pptx",
            "--outdir", output_dir,
            input_path
        ], check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"LibreOffice conversion failed: {e}")
    base = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(output_dir, f"{base}.pptx")

def extract_text_from_pdf(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)

def extract_text_from_pptx_file(path: str) -> str:
    prs = Presentation(path)
    text = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text.append(shape.text)
    return "\n".join(text)

def extract_text_from_docx_bytes(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(para.text for para in doc.paragraphs)

@app.post("/upload-slide/")
async def upload_slide(file: UploadFile = File(...)):
    # 1) Read upload into memory & write to temp file
    contents = await file.read()
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    original_path = os.path.join(temp_dir, file.filename)
    with open(original_path, "wb") as f:
        f.write(contents)

    # 2) If .ppt, convert to .pptx
    filename = file.filename.lower()
    if filename.endswith(".ppt"):
        try:
            converted_path = convert_ppt_to_pptx(original_path, temp_dir)
        except RuntimeError as e:
            raise HTTPException(400, detail=str(e))
        target_path = converted_path
    else:
        target_path = original_path

    # 3) Dispatch based on now-supported extensions
    if target_path.endswith(".pdf"):
        text = extract_text_from_pdf(contents)
    elif target_path.endswith(".pptx"):
        text = extract_text_from_pptx_file(target_path)
    elif target_path.endswith(".docx"):
        text = extract_text_from_docx_bytes(contents)
    else:
        raise HTTPException(400, detail="Unsupported file type. Please use .pdf, .ppt, .pptx or .docx.")

    # 4) Cleanup temp files
    try:
        os.remove(original_path)
        if target_path != original_path:
            os.remove(target_path)
    except OSError:
        pass

    return {"text": text}
