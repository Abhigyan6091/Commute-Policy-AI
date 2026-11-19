import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import docx
import fitz  # PyMuPDF

def make_pdf(txt_path: Path, pdf_path: Path):
    text = txt_path.read_text(encoding='utf-8')
    # In synthetic policies, pages are separated by form-feed \x0c
    pages = text.split('\x0c')
    
    doc = fitz.open()
    for page_text in pages:
        page = doc.new_page(width=595, height=842)  # A4 size
        # Insert text with margin
        rect = fitz.Rect(50, 50, 545, 792)
        page.insert_textbox(rect, page_text.strip(), fontsize=10, fontname="helv")
    
    doc.save(str(pdf_path))
    doc.close()
    print(f"Created: {pdf_path}")

def make_docx(txt_path: Path, docx_path: Path):
    text = txt_path.read_text(encoding='utf-8')
    doc = docx.Document()
    
    # Split by form-feed \x0c for page breaks
    pages = text.split('\x0c')
    for i, page_text in enumerate(pages):
        if i > 0:
            doc.add_page_break()
        lines = page_text.strip().split('\n')
        for line in lines:
            line_str = line.strip()
            if line_str.startswith('SECTION ') or line_str.startswith('Apex Technologies') or line_str.startswith('Nova Digital') or line_str.startswith('Vertex Systems'):
                p = doc.add_paragraph()
                run = p.add_run(line_str)
                run.bold = True
            elif line_str:
                doc.add_paragraph(line_str)
                
    doc.save(str(docx_path))
    print(f"Created: {docx_path}")

def main():
    policies_dir = Path(__file__).resolve().parent.parent / 'data' / 'policies'
    txt_files = list(policies_dir.glob('*.txt'))
    print(f"Found {len(txt_files)} txt policy files.")
    
    for txt in txt_files:
        pdf_path = txt.with_suffix('.pdf')
        docx_path = txt.with_suffix('.docx')
        make_pdf(txt, pdf_path)
        make_docx(txt, docx_path)

if __name__ == '__main__':
    main()
