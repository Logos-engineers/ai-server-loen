import pdfplumber
import io
from services.r2_client import download_file


def extract_text_from_r2(r2_key: str) -> str:
    pdf_bytes = download_file(r2_key)
    return extract_text_from_bytes(pdf_bytes)


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    return "\n".join(text_parts)
