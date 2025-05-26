# main.py
import os, io, subprocess, json
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz                        # PyMuPDF for PDFs
from pptx import Presentation
from docx import Document
import openai

app = FastAPI()
app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
openai.api_key = os.getenv("OPENAI_API_KEY")


@app.get("/")
def read_root():
    return {
        "message": "Welcome, student 😊. This is Sir John's learning tool to enhance smooth studying. Enjoy!"
    }


def convert_ppt_to_pptx(input_path: str, output_dir: str) -> str:
    """Convert .ppt → .pptx using headless LibreOffice."""
    try:
        subprocess.run([
            "libreoffice", "--headless",
            "--convert-to", "pptx",
            "--outdir", output_dir,
            input_path
        ], check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Conversion failed: {e}")
    base = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(output_dir, f"{base}.pptx")


def extract_text(path: str, raw_bytes: bytes) -> str:
    ext = path.lower().rsplit('.', 1)[-1]
    if ext == "pdf":
        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    if ext in ("ppt", "pptx"):
        prs = Presentation(path)
        lines = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    lines.append(shape.text.strip())
        return "\n".join(lines)
    if ext == "docx":
        doc = Document(io.BytesIO(raw_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    raise ValueError("Unsupported file type")


def ask_for_questions(text: str) -> list:
    """Ask OpenAI to generate 50 mixed‐type questions from given text."""
    prompt = f"""You are an expert exam‐question writer.
Generate exactly 50 questions from the following material:
 - 30 multiple-choice (4 options each; indicate the correct one)
 - 15 fill-in-the-blank
 - 5 short-answer theoretical

Return a JSON array named "questions", where each entry is:
{{
  "id": integer,
  "type": "multiple_choice"|"fill_in_blank"|"theoretical",
  "question": string,
  "options": [string,string,string,string],    # only for MCQs
  "answer": string
}}
Do not include any extra text—only valid JSON."""
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content": prompt + "\n\n" + text}],
        temperature=0.7,
    )
    try:
        return json.loads(resp.choices[0].message.content)["questions"]
    except Exception as e:
        raise HTTPException(500, detail=f"Invalid JSON from OpenAI: {e}")


@app.post("/upload-and-generate/")
async def upload_and_generate(file: UploadFile = File(...)):
    contents = await file.read()
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    orig_path = os.path.join(temp_dir, file.filename)
    with open(orig_path, "wb") as f:
        f.write(contents)

    name = file.filename.lower()
    if name.endswith(".ppt"):
        try:
            orig_path = convert_ppt_to_pptx(orig_path, temp_dir)
        except RuntimeError as e:
            raise HTTPException(400, detail=str(e))

    try:
        text = extract_text(orig_path, contents)
    except Exception as e:
        raise HTTPException(400, detail=f"Extraction error: {e}")

    questions = ask_for_questions(text)

    # cleanup
    try:
        os.remove(orig_path)
    except:
        pass

    return {"questions": questions, "text": text}


@app.post("/generate-from-text/")
async def generate_from_text(text: str = Form(...)):
    """
    Submit raw slide text and get a fresh set of 50 questions
    without re-uploading the file.
    """
    questions = ask_for_questions(text)
    return {"questions": questions}


@app.post("/grade/")
async def grade(payload: dict):
    """
    Expects:
    {
      "questions": [ {id, type, question, options?, answer}, … ],
      "responses": [ {id, user_answer}, … ]
    }
    Returns:
    {
      "results": [ {id, user_answer, correct_answer, is_correct}, … ],
      "score": number_correct
    }
    """
    body = json.dumps(payload)
    prompt = (
        "You are a precise grader. Given these questions with correct answers\n"
        "and these user answers, produce JSON:\n"
        "- 'results': [ {id, user_answer, correct_answer, is_correct} ]\n"
        "- 'score': total correct count\n"
        "Return only JSON.\n\n"
        + body
    )
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content": prompt}],
        temperature=0.0,
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        raise HTTPException(500, detail="Invalid grading JSON from OpenAI")
