"""Sinyal.AI local web server and context-aware LLM revision proxy.

Secrets are read from environment variables and never sent to the browser.
"""
from __future__ import annotations

import json
import os
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HOST = os.environ.get("SINYAL_AI_HOST", "127.0.0.1")
PORT = int(os.environ.get("SINYAL_AI_PORT", "8765"))
BASE_URL = os.environ.get("SINYAL_AI_BASE_URL", "http://localhost:20128/v1").rstrip("/")
API_KEY = os.environ.get("SINYAL_AI_API_KEY", "")
MODEL = os.environ.get("SINYAL_AI_HUMANIZER_MODEL", "my-combo")
TIMEOUT = int(os.environ.get("SINYAL_AI_TIMEOUT", "120"))
MAX_BODY_BYTES = 12 * 1024 * 1024
CHUNK_WORDS = 900

STYLE_RULES = {
    "natural": "Gunakan bahasa Indonesia alami, lugas, hangat, dan tidak dibuat-buat.",
    "concise": "Padatkan tulisan, hapus pengulangan, dan pertahankan semua informasi penting.",
    "formal": "Gunakan bahasa Indonesia formal yang jernih, profesional, dan tidak kaku.",
}
INTENSITY_RULES = {
    1: "Lakukan edit ringan; pertahankan struktur dan pilihan kata penulis sebisa mungkin.",
    2: "Lakukan edit moderat pada alur, ritme, transisi, dan kejelasan.",
    3: "Lakukan penyuntingan mendalam, tetapi jangan mengubah fakta, posisi, atau maksud penulis.",
}


def words(text: str) -> list[str]:
    return re.findall(r"[^\s]+", text or "")


def chunk_text(text: str, limit: int = CHUNK_WORDS) -> list[str]:
    """Split on paragraphs first, then sentences, while preserving all input text."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks, current, count = [], [], 0
    for paragraph in paragraphs:
        paragraph_words = words(paragraph)
        if len(paragraph_words) > limit:
            if current:
                chunks.append("\n\n".join(current)); current, count = [], 0
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            section, section_count = [], 0
            for sentence in sentences:
                size = len(words(sentence))
                if section and section_count + size > limit:
                    chunks.append(" ".join(section)); section, section_count = [], 0
                section.append(sentence); section_count += size
            if section:
                chunks.append(" ".join(section))
            continue
        if current and count + len(paragraph_words) > limit:
            chunks.append("\n\n".join(current)); current, count = [], 0
        current.append(paragraph); count += len(paragraph_words)
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text]


def extract_content(response: dict) -> str:
    choices = response.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content") or choices[0].get("text")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
    output = response.get("output_text")
    return output.strip() if isinstance(output, str) else ""


def llm_request(messages: list[dict]) -> str:
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": 0.55,
        "max_tokens": 4096,
        "stream": False,
    }, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{BASE_URL}/chat/completions", data=payload, method="POST",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"LLM HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"LLM tidak dapat dihubungi: {error.reason}") from error
    content = extract_content(result)
    if not content:
        raise RuntimeError("LLM mengembalikan respons kosong.")
    return content


def revise_text(text: str, style: str, intensity: int, context: str) -> tuple[str, int]:
    chunks = chunk_text(text)
    revised = []
    system = (
        "Anda adalah editor bahasa Indonesia. Tugas Anda meningkatkan kejelasan, alur, "
        "kekhasan suara penulis, dan keterbacaan. Jangan menambah fakta, kutipan, pengalaman, "
        "atau sumber yang tidak ada. Jangan mengubah angka dan klaim. Jangan membahas detektor AI "
        "atau mengklaim teks akan lolos deteksi. Keluarkan hanya teks hasil revisi tanpa pengantar."
    )
    for index, chunk in enumerate(chunks):
        before = chunks[index - 1][-800:] if index else "(awal dokumen)"
        after = chunks[index + 1][:800] if index + 1 < len(chunks) else "(akhir dokumen)"
        prompt = f"""Sunting bagian {index + 1} dari {len(chunks)}.

Gaya: {STYLE_RULES.get(style, STYLE_RULES['natural'])}
Intensitas: {INTENSITY_RULES.get(intensity, INTENSITY_RULES[2])}
Konteks/tujuan dari pengguna: {context or '(tidak diberikan)'}

Konteks bagian sebelumnya (jangan ditulis ulang):
{before}

TEKS YANG HARUS DIREVISI:
{chunk}

Konteks bagian berikutnya (jangan ditulis ulang):
{after}

Pertahankan kesinambungan antarbagian dan keluarkan hanya revisi TEKS YANG HARUS DIREVISI."""
        revised.append(llm_request([{"role": "system", "content": system},
                                    {"role": "user", "content": prompt}]))
    return "\n\n".join(revised), len(chunks)


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, status: int, payload: dict) -> bool:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return True
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # The browser can close a tab or cancel navigation after the LLM
            # has finished. This is a client disconnect, not an API failure.
            return False

    def do_GET(self):
        if self.path == "/api/health":
            self.send_json(200, {"ok": True, "llmConfigured": bool(API_KEY), "model": MODEL})
            return
        super().do_GET()

    def do_POST(self):
        if self.path != "/api/humanize":
            self.send_json(404, {"error": "Endpoint tidak ditemukan."}); return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY_BYTES:
            self.send_json(413, {"error": "Ukuran permintaan tidak valid atau terlalu besar."}); return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            text = str(data.get("text", "")).strip()
            if len(words(text)) < 10:
                raise ValueError("Teks minimal 10 kata.")
            if not API_KEY:
                self.send_json(503, {"error": "LLM belum dikonfigurasi. Set SINYAL_AI_API_KEY di terminal server."}); return
            style = str(data.get("style", "natural"))
            intensity = max(1, min(3, int(data.get("intensity", 2))))
            result, chunks = revise_text(text, style, intensity, str(data.get("context", ""))[:2000])
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})
            return
        except Exception as error:
            self.send_json(502, {"error": str(error)})
            return
        # Keep socket-write errors outside the LLM exception block so a
        # disconnected client never triggers a misleading second 502 reply.
        self.send_json(200, {"text": result, "model": MODEL, "chunks": chunks})


if __name__ == "__main__":
    print(f"Sinyal.AI running at http://{HOST}:{PORT}")
    print(f"LLM: {'configured' if API_KEY else 'not configured'} | model={MODEL}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()