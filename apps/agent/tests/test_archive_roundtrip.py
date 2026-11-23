"""Gate test: pack/extract conversation dir (SDK version label is metadata only)."""

from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "archive"))

from conversation_archive.store import ConversationArchiveStore, LocalArchiveBackend


def test_archive_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        conv_id = str(uuid.uuid4())
        conv_dir = Path(tmp) / "conversations" / conv_id
        conv_dir.mkdir(parents=True)
        (conv_dir / "base_state.json").write_text('{"version": 1}', encoding="utf-8")
        (conv_dir / "events").mkdir()
        (conv_dir / "events" / "event-00001-a.json").write_text("{}", encoding="utf-8")

        store = ConversationArchiveStore(LocalArchiveBackend(Path(tmp) / "archives"))
        data, sha = ConversationArchiveStore.pack_directory(conv_dir)
        key, digest, size = store.save_conversation("proj", "run", conv_dir)
        assert digest == sha
        assert size == len(data)

        wipe = Path(tmp) / "conversations"
        import shutil

        shutil.rmtree(wipe)
        parent = Path(tmp) / "conversations"
        restored = store.load_conversation(key, parent, conv_id)
        assert (restored / "base_state.json").is_file()
        assert (restored / "events" / "event-00001-a.json").is_file()


if __name__ == "__main__":
    test_archive_roundtrip()
    print("ok")