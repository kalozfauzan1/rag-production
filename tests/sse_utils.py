"""Helper test: memecah body SSE mentah menjadi frame."""

import json


def parse_frames(raw: str) -> list[tuple[str, str]]:
    """Kembalikan daftar (nama_event, data). Heartbeat dilaporkan sebagai ("ping", "")."""
    frames: list[tuple[str, str]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        if block.lstrip().startswith(":"):
            frames.append(("ping", ""))
            continue
        event = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data = line.removeprefix("data:").strip()
        frames.append((event, data))
    return frames


def tokens_text(frames: list[tuple[str, str]]) -> str:
    """Gabungkan payload semua event `token` menjadi teks jawaban."""
    return "".join(json.loads(data)["text"] for event, data in frames if event == "token")
