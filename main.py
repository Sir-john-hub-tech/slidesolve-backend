# main.py
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF
from pptx import Presentation
from docx import Document
import openai
import os
import sympy as sp
from sympy.parsing.sympy_parser import parse_expr
from typing import Dict, List, Tuple
import json
import io

app = FastAPI()

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# In-memory storage (replace with a database in production)
question_bank: Dict[str, List[Dict]] = {}
student_answers: Dict[str, Dict[str, str]] = {}

# --------------------- Helper Functions ---------------------
def extract_text(file_bytes: bytes, extension: str) -> str:
    try:
        if extension == "pdf":
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            return " ".join([page.get_text() for page in doc])
        elif extension in {"pptx", "ppt"}:
            prs = Presentation(io.BytesIO(file_bytes))
            return " ".join([shape.text for slide in prs.slides for shape in slide.shapes if hasattr(shape, "text")])
        elif extension == "docx":
            doc = Document(io.BytesIO(file_bytes))
            return " ".join([para.text for para in doc.paragraphs])
        else:
            raise ValueError("Unsupported file type")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def generate_questions(text: str) -> Dict:
    prompt = f"""Generate 50 exam questions from this text. Include multiple-choice, fill-in-the-blank, and short answers:
{text}

Format as JSON:
{{
    "multiple_choice": [
        {{"question": "...", "options": ["A", "B", "C", "D"], "answer": "A"}}
    ],
    "fill_in": [
        {{"question": "...", "answer": "..."}}
    ],
    "short_answer": [
        {{"question": "...", "answer": "..."}}
    ]
}}"""
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(response.choices[0].message.content)

def solve_math(problem: str) -> str:
    try:
        expr = parse_expr(problem)
        solution = sp.solve(expr)
        return str(solution)
    except Exception as e:
        return f"Error: {str(e)}"

# --------------------- Endpoints ---------------------
@app.get("/")
async def welcome():
    return {"message": "Hello student 😊, welcome to Sir John's learning tool. Enjoy!"}

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    file_bytes = await file.read()
    extension = file.filename.split(".")[-1].lower()
    text = extract_text(file_bytes, extension)
    questions = generate_questions(text)
    question_bank[file.filename] = questions
    return questions

@app.post("/solve-math/")
async def math_solver(problem: str = Form(...)):
    return {"solution": solve_math(problem)}

@app.post("/submit-answers/")
async def submit_answers(filename: str = Form(...), answers: str = Form(...)):
    try:
        student_answers[filename] = json.loads(answers)
        return {"status": "Answers submitted successfully"}
    except:
        raise HTTPException(status_code=400, detail="Invalid answer format")

@app.get("/results/{filename}")
async def get_results(filename: str):
    correct = 0
    total = 0
    feedback = []
    
    questions = question_bank.get(filename, {})
    answers = student_answers.get(filename, {})
    
    for q_type in ["multiple_choice", "fill_in", "short_answer"]:
        for q in questions.get(q_type, []):
            total += 1
            user_answer = answers.get(q["question"], "")
            if str(user_answer).strip().lower() == str(q["answer"]).strip().lower():
                correct += 1
            else:
                feedback.append(f"Question: {q['question']} → Correct: {q['answer']}")
    
    score = (correct / total) * 100 if total > 0 else 0
    suggestions = [
        "Focus on chapters with low scores",
        "Review key definitions and formulas",
        "Practice more fill-in-the-blank questions"
    ] if score < 70 else ["Excellent work! Keep it up!"]
    
    return {
        "score": f"{score:.2f}%",
        "feedback": feedback[:5],  # Top 5 errors
        "suggestions": suggestions
    }
