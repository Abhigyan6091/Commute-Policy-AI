import hashlib
import io
import re
import zipfile
from pathlib import Path
from threading import Lock
from uuid import uuid4
from app.schemas import Chunk

class UploadError(ValueError):
    pass

def parse_document(name, data, settings):
    if not data or len(data) > settings.max_upload_bytes:
        raise UploadError('Empty or oversized file')
    suffix = Path(name).suffix.lower()
    pages = []
    try:
        if suffix == '.txt':
            text = data.decode('utf-8-sig')
            if '\x00' in text or text.startswith(('MZ', '%PDF', 'PK\x03\x04')):
                raise UploadError('Invalid text file')
            parts = text.split('\f')
            pages = [(i + 1 if len(parts) > 1 else None, part) for i, part in enumerate(parts)]
        elif suffix == '.pdf':
            import fitz
            if not data.startswith(b'%PDF-'):
                raise UploadError('PDF signature mismatch')
            with fitz.open(stream=data, filetype='pdf') as document:
                if document.needs_pass or document.page_count > settings.max_pages:
                    raise UploadError('Encrypted or oversized PDF')
                for i, page in enumerate(document):
                    pages.append((i + 1, page.get_text()))
                    if sum(len(t) for _, t in pages) > settings.max_text_chars:
                        raise UploadError('Extracted content too large')
        elif suffix == '.docx':
            from docx import Document
            if not data.startswith(b'PK\x03\x04'):
                raise UploadError('DOCX signature mismatch')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
                if '[Content_Types].xml' not in names or 'word/document.xml' not in names:
                    raise UploadError('Invalid DOCX structure')
                if sum(i.file_size for i in archive.infolist()) > 30_000_000:
                    raise UploadError('Expanded DOCX too large')
                if any('vbaproject' in n.lower() or '/embeddings/' in n.lower() for n in names):
                    raise UploadError('Embedded executable content is unsupported')
            document = Document(io.BytesIO(data))
            # XML order includes paragraph text inside tables. DOCX pagination is not stable.
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            paragraphs = [''.join(t.text or '' for t in p.iter('{'+ns['w']+'}t'))
                          for p in document.element.body.findall('.//{'+ns['w']+'}p')]
            pages = [(None, '\n'.join(paragraphs))]
        else:
            raise UploadError('Supported formats: TXT, PDF, DOCX')
    except UploadError:
        raise
    except Exception as exc:
        raise UploadError('Malformed or unreadable document') from exc
    if len(pages) > settings.max_pages or sum(len(t) for _, t in pages) > settings.max_text_chars:
        raise UploadError('Document exceeds content limits')
    if not any(t.strip() for _, t in pages):
        raise UploadError('No extractable text; scanned PDFs require OCR outside this application')
    return pages

HEADING = re.compile(r'^(\d+(?:\.\d+)*)(?:[.)])?\s+(.{2,100})$')
def make_chunks(pages, company, version, document, settings):
    chunks, number, title = [], '', 'Unnumbered section'
    # Word spans preserve exact source substrings; ~0.75 words/token is a documented estimate.
    width = max(30, int(settings.chunk_tokens * 0.75))
    overlap = int(settings.chunk_overlap * 0.75)
    def append(text, page, section, heading):
        spans = list(re.finditer(r'\S+', text))
        for start in range(0, len(spans), width - overlap):
            end = min(start + width, len(spans))
            body = text[spans[start].start():spans[end - 1].end()]
            chunks.append(Chunk(chunk_id=uuid4().hex, company_id=company, policy_id='transport',
                policy_version=version, document_name=document, section_number=section,
                section_title=heading, page_number=page, text=body,
                content_hash=hashlib.sha256(body.encode()).hexdigest()))
            if end == len(spans):
                break
    for page, text in pages:
        buffer = []
        for line in text.splitlines(keepends=True):
            match = HEADING.match(line.strip())
            if match:
                append(''.join(buffer), page, number, title)
                buffer = []
                number, title = match.groups()
            buffer.append(line)
        append(''.join(buffer), page, number, title)
    if not chunks:
        raise UploadError('No chunks extracted')
    return chunks

class Ingestor:
    def __init__(self, db, vectors, embedder, settings):
        self.db, self.vectors, self.embedder, self.settings = db, vectors, embedder, settings
        self.lock = Lock()
    def recover(self):
        # Safe because the process owns the application lifetime file lock.
        for row in self.db.staging():
            self.vectors.delete(row['company_id'], row['id'])
            if row['status'] == 'STAGING':
                self.db.fail(row['company_id'], row['id'], 'system', uuid4().hex, 'abandoned_on_restart')
    def ingest(self, p, name, data, request_id):
        name = Path(name.replace('\\', '/')).name
        if not name or len(name) > 160 or any(ord(c) < 32 for c in name):
            raise UploadError('Invalid document filename')
        with self.lock:
            version = self.db.stage(p.company_id, name)
            try:
                pages = parse_document(name, data, self.settings)
                chunks = make_chunks(pages, p.company_id, version, name, self.settings)
                embeddings = self.embedder.encode([c.text for c in chunks])
                self.vectors.add(chunks, embeddings)
                self.vectors.verify(p.company_id, version, chunks)
                return self.db.activate(p.company_id, version, chunks, p.user_id, request_id)
            except Exception as exc:
                # Never delete a version whose activation committed.
                if self.db.active(p.company_id) != version:
                    self.db.fail(p.company_id, version, p.user_id, request_id, 'ingestion_failed')
                    self.vectors.delete(p.company_id, version)
                raise UploadError('Policy upload failed; existing active policy is preserved') from exc
