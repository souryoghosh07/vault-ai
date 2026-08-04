import fitz  # PyMuPDF
import httpx
import asyncio
import re
import pytesseract
from PIL import Image
from app.prompts.ma_prompts import MA_SYSTEM_PROMPT

# Point directly to your Windows Tesseract installation
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
CHUNK_SIZE = 12
OVERLAP = 1

DEFAULT_CLEAN_REPORT = """# M&A TARGET AUDIT: RED FLAG REPORT

## CONTRACT & LEGAL RISKS
* **Change of Control:** Not found in document | **Citation:** Not found in document
* **Termination & Notice:** Not found in document | **Citation:** Not found in document
* **Assignability Restrictions:** Not found in document | **Citation:** Not found in document

## CIM NARRATIVE RISKS
* **Customer Concentration:** Not found in document | **Citation:** Not found in document
* **Management Turnover:** Not found in document | **Citation:** Not found in document
* **Regulatory/Compliance Liabilities:** Not found in document | **Citation:** Not found in document"""

def clean_ocr_text(text: str) -> str:
    """Sanitizes raw OCR output to improve LLM comprehension."""
    # Rejoin words split across line breaks (e.g., "Agre-\ne-ment" -> "Agreement")
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    # Replace multiple spaces or tabs with a single space
    text = re.sub(r'[ \t]+', ' ', text)
    # Collapse 3 or more consecutive newlines into double newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def get_page_chunks(pdf_bytes: bytes) -> list:
    """Extracts text, falling back to OCR for scanned images with text sanitization."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()
        
        # FALLBACK: If text layer is missing/short, execute OCR
        if len(text) < 50:
            print(f"Page {page_num + 1} appears to be a scan. Running OCR...")
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img).strip()
        
        # Clean up any OCR noise before passing to the chunker
        text = clean_ocr_text(text)
        
        if len(text) > 50:
            pages.append({"page": page_num + 1, "content": text})

    chunks = []
    for i in range(0, len(pages), max(1, CHUNK_SIZE - OVERLAP)):
        chunk_pages = pages[i:i + CHUNK_SIZE]
        chunk_text = ""
        for item in chunk_pages:
            chunk_text += f"\n--- [PAGE {item['page']}] ---\n{item['content']}"
        chunks.append(chunk_text)
        
        if i + CHUNK_SIZE >= len(pages):
            break
            
    return chunks

async def analyze_chunk(client: httpx.AsyncClient, chunk_text: str, filename: str, model_name: str) -> str:
    """Runs the strict extraction prompt against a single chunk with infinite-loop guardrails."""
    user_prompt = f"DOCUMENT FILENAME: {filename}\n\nINGESTED TEXT WITH PAGE MARKERS:\n---\n{chunk_text}\n---\n\nPerform the M&A Red Flag Audit now."
    
    payload = {
        "model": model_name,
        "system": MA_SYSTEM_PROMPT,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": 8192,
            "num_predict": 1024,
            "repeat_penalty": 1.15
        }
    }
    
    try:
        response = await client.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        res_text = response.json().get("response", "")
        # LOGGING: Print raw output to terminal for verification
        print(f"\n--- [DEBUG] RAW LLM EXTRACTION (CHUNK) ---\n{res_text}\n-----------------------------------\n")
        return res_text
    except httpx.TimeoutException:
        return "[ERROR]: Chunk processing timed out. Skipping."

async def process_ma_document(file_bytes: bytes, filename: str, model_name: str = "granite4.1:8b") -> str:
    """The Map-Reduce pipeline: Chunks text, extracts sequentially, and synthesizes the final report."""
    chunks = get_page_chunks(file_bytes)
    
    if not chunks:
        print("Document resulted in 0 readable chunks. Returning clean report.")
        return DEFAULT_CLEAN_REPORT

    raw_findings = []

    async with httpx.AsyncClient(timeout=None) as client:
        # MAP PHASE: Process sequentially
        for idx, chunk in enumerate(chunks):
            print(f"Engine Processing Chunk {idx+1} of {len(chunks)}...")
            finding = await analyze_chunk(client, chunk, filename, model_name)
            raw_findings.append(finding)

        # REDUCE PHASE: Synthesize raw findings into master report
        print("Synthesizing master report...")
        synthesis_prompt = f"""You are a deterministic Master Report Synthesizer.
        Compile the provided raw findings into a SINGLE master report using the EXACT Markdown format required.
        
        SYNTHESIS RULES:
        1. If a category has a specific risk identified in ANY chunk, include it and drop the "Not found" entry.
        2. Combine duplicate findings into a single bullet point.
        3. If a category has no findings across ALL chunks, output EXACTLY: `* **[Category Name]:** Not found in document | **Citation:** Not found`
        4. If a page number is missing from the raw text, cite the Section number only. Do NOT output placeholders like "Page Y" or "assuming page reference".
        5. CRITICAL: Output ONLY the Markdown report. Do NOT output any introductory text, concluding remarks, or "Notes" of any kind.

        RAW FINDINGS TO SYNTHESIZE:
        {chr(10).join(raw_findings)}
        """

        payload = {
            "model": model_name,
            "system": MA_SYSTEM_PROMPT,
            "prompt": synthesis_prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": 8192,
                "num_predict": 2048, 
                "repeat_penalty": 1.15
            }
        }

        try:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            final_report = response.json().get("response", DEFAULT_CLEAN_REPORT)
            print(f"\n--- [DEBUG] FINAL SYNTHESIZED REPORT ---\n{final_report}\n-----------------------------------\n")
            return final_report
        except httpx.TimeoutException:
            return "Error: Synthesis timed out. Try processing a smaller document."