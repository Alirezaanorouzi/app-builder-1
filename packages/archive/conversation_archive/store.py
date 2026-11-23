"""Tar.gz persistence_dir archives — local filesystem or S3-compatible."""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

try:
    import boto3
    from botocore.client import Config
except ImportError:  # pragma: no cover
    boto3 = None


class ArchiveBackend(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "application/gzip") -> None:
        ...

    @abstractmethod
    def get(self, key: str) -> bytes:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...


class LocalArchiveBackend(ArchiveBackend):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.replace("..", "").lstrip("/")
        return self.root / safe

    def put(self, key: str, data: bytes, content_type: str = "application/gzip") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()


class S3ArchiveBackend(ArchiveBackend):
    def __init__(
        self,
        bucket: str,
        endpoint: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        if boto3 is None:
            raise RuntimeError("boto3 required for S3 archive backend")
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
        )

    def put(self, key: str, data: bytes, content_type: str = "application/gzip") -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        resp = self.client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


class ConversationArchiveStore:
    """Pack / extract conversation directories."""

    def __init__(self, backend: ArchiveBackend) -> None:
        self.backend = backend

    @staticmethod
    def pack_directory(conversation_dir: Path) -> tuple[bytes, str]:
        if not conversation_dir.is_dir():
            raise FileNotFoundError(conversation_dir)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(conversation_dir, arcname=conversation_dir.name)
        data = buf.getvalue()
        digest = hashlib.sha256(data).hexdigest()
        return data, digest

    @staticmethod
    def extract_to(data: bytes, parent_dir: Path, conversation_id: str) -> Path:
        parent_dir.mkdir(parents=True, exist_ok=True)
        target = parent_dir / conversation_id
        if target.exists():
            import shutil

            shutil.rmtree(target)
        buf = io.BytesIO(data)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            tar.extractall(path=parent_dir)
        # Archive uses arcname=conversation_dir.name which should match conversation_id
        if not target.is_dir():
            # fallback: find single top-level dir
            children = [p for p in parent_dir.iterdir() if p.is_dir()]
            if len(children) == 1:
                children[0].rename(target)
        return target

    def save_conversation(
        self,
        project_id: str,
        run_id: str,
        conversation_dir: Path,
    ) -> tuple[str, str, int]:
        data, sha256 = self.pack_directory(conversation_dir)
        key = f"{project_id}/{run_id}/{uuid.uuid4().hex}.tar.gz"
        self.backend.put(key, data)
        return key, sha256, len(data)

    def load_conversation(self, storage_key: str, parent_dir: Path, conversation_id: str) -> Path:
        data = self.backend.get(storage_key)
        return self.extract_to(data, parent_dir, conversation_id)

    @classmethod
    def from_env(cls) -> "ConversationArchiveStore":
        backend_type = os.environ.get("ARCHIVE_BACKEND", "local").lower()
        if backend_type == "s3":
            return cls(
                S3ArchiveBackend(
                    bucket=os.environ["S3_BUCKET"],
                    endpoint=os.environ["S3_ENDPOINT"],
                    access_key=os.environ["S3_ACCESS_KEY"],
                    secret_key=os.environ["S3_SECRET_KEY"],
                    region=os.environ.get("S3_REGION", "us-east-1"),
                )
            )
        root = os.environ.get("ARCHIVE_LOCAL_DIR", "./data/archives")
        return cls(LocalArchiveBackend(root))