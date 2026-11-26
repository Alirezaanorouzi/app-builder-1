from worker.workspace_manifest import clip_manifest


def test_clip_manifest_caps_length() -> None:
    text = "\n".join(f"./src/file{i}.tsx" for i in range(500))
    clipped = clip_manifest(text, limit=100)
    assert len(clipped) <= 100
    assert clipped.endswith("…")
