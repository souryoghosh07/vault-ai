import httpx
import asyncio
import io

# Docling Imports
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat, DocumentStream
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
CHUNK_SIZE = 12
OVERLAP = 1

def get_page_chunks(pdf_bytes: bytes, filename: str) -> list:
    """Extracts text and tables using Docling, forcing RapidOCR for scanned images."""
    print("Initializing air-gapped Docling engine...")
    
    # 1. Force Docling to use RapidOCR (bypassing the host system completely)
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True 
    pipeline_options.ocr_options = RapidOcrOptions() 

    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    print(f"Parsing {filename} with Docling (OCR enabled)...")
    
    # 2. Convert raw bytes stream into a DoclingDocument
    stream = DocumentStream(name=filename, stream=io.BytesIO(pdf_bytes))
    result = converter.convert(stream)
    
    # 3. Iterate through all document elements and group them by page number
    pages_content = {}
    for item, _ in result.document.iterate_items():
        if not item.prov:
            continue
            
        page_no = item.prov[0].page_no
        if page_no not in pages_content:
            pages_content[page_no] = ""
        
        # Export tables nicely formatted, fallback to raw text for paragraphs
        try:
            pages_content[page_no] += item.export_to_markdown(result.document) + "\n\n"
        except AttributeError:
            if hasattr(item, "text"):
                pages_content[page_no] += item.text + "\n\n"
                
    # 4. Format into the page dictionary array your chunker expects
    pages = [{"page": p, "content": text.strip()} for p, text in sorted(pages_content.items())]

    # 5. Execute your strict Chunking & Overlap map logic
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

async def analyze_chunk(
    client: httpx.AsyncClient, 
    chunk_text: str, 
    filename: str, 
    model_name: str, 
    system_prompt: str
) -> str:
    """Runs the strict extraction prompt against a single chunk with infinite-loop guardrails."""
    user_prompt = f"DOCUMENT FILENAME: {filename}\n\nINGESTED TEXT WITH PAGE MARKERS:\n---\n{chunk_text}\n---\n\nPerform the audit now."
    
    payload = {
        "model": model_name,
        "system": system_prompt,
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

async def process_document(
    file_bytes: bytes, 
    filename: str, 
    system_prompt: str,
    synthesis_rules: str,
    default_report: str,
    model_name: str = "granite4.1:8b"
) -> str:
    """The Map-Reduce pipeline: Chunks text, extracts sequentially, and synthesizes the final report."""
    
    # Pass filename down to the Docling processor
    chunks = get_page_chunks(file_bytes, filename)
    
    if not chunks:
        print("Document resulted in 0 readable chunks. Returning clean report.")
        return default_report

    raw_findings = []

    async with httpx.AsyncClient(timeout=None) as client:
        # MAP PHASE: Process sequentially
        for idx, chunk in enumerate(chunks):
            print(f"Engine Processing Chunk {idx+1} of {len(chunks)}...")
            finding = await analyze_chunk(client, chunk, filename, model_name, system_prompt)
            raw_findings.append(finding)

        # REDUCE PHASE: Synthesize raw findings into master report
        print("Synthesizing master report...")
        synthesis_prompt = f"""You are a deterministic Master Report Synthesizer.
        Compile the provided raw findings into a SINGLE master report using the EXACT Markdown format required.
        
        SYNTHESIS RULES:
        {synthesis_rules}

        RAW FINDINGS TO SYNTHESIZE:
        {chr(10).join(raw_findings)}
        """

        payload = {
            "model": model_name,
            "system": system_prompt,
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
            final_report = response.json().get("response", default_report)
            print(f"\n--- [DEBUG] FINAL SYNTHESIZED REPORT ---\n{final_report}\n-----------------------------------\n")
            return final_report
        except httpx.TimeoutException:
            return "Error: Synthesis timed out. Try processing a smaller document."