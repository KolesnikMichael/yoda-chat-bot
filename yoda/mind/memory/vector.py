from dataclasses import dataclass
from pathlib import Path

import chromadb

from yoda.mind.memory.data.chroma_summary_record import ChromaSummaryRecord
from yoda.mind.memory.data.summary_store_settings import SummaryStoreSettings


@dataclass(frozen=True)
class StoredSummaryRecord:
    summary_id: str
    document: str
    embedding: list[float]


class VectorProvider:
    def __init__(self, settings: SummaryStoreSettings) -> None:
        self._settings = settings
        persist_path = Path(settings.persist_directory)
        persist_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_path))

    def collection_name(self, chat_id: int) -> str:
        return f"{self._settings.collection_prefix}{chat_id}"

    def encrypt(self, plaintext: str) -> str:
        return plaintext

    def decrypt(self, ciphertext: str) -> str:
        return ciphertext

    @staticmethod
    def _flatten_metadata(record: ChromaSummaryRecord) -> dict[str, str | float]:
        return {
            "compressed_at": record.compressed_at,
            "content_from_ts": record.content_from_ts,
            "content_to_ts": record.content_to_ts,
            "skills": ",".join(record.skills),
            "topics": ",".join(record.topics),
        }

    def _get_collection(self, chat_id: int):
        return self._client.get_or_create_collection(name=self.collection_name(chat_id))

    def _collection_exists(self, chat_id: int) -> bool:
        name = self.collection_name(chat_id)
        return any(collection.name == name for collection in self._client.list_collections())

    async def persist_summaries(
        self,
        chat_id: int,
        records: list[ChromaSummaryRecord],
    ) -> None:
        if not records:
            return
        collection = self._get_collection(chat_id)
        ids = [record.summary_id for record in records]
        embeddings = [record.embedding for record in records]
        documents = [self.encrypt(record.document) for record in records]
        metadatas = [self._flatten_metadata(record) for record in records]
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    async def list_stored_records(self, chat_id: int) -> list[StoredSummaryRecord]:
        if not self._collection_exists(chat_id):
            return []
        collection = self._get_collection(chat_id)
        result = collection.get(include=["embeddings", "documents"])
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        raw_embeddings = result.get("embeddings")
        embeddings = list(raw_embeddings) if raw_embeddings is not None else []
        records: list[StoredSummaryRecord] = []
        for summary_id, document, embedding in zip(ids, documents, embeddings, strict=True):
            records.append(
                StoredSummaryRecord(
                    summary_id=summary_id,
                    document=self.decrypt(document or ""),
                    embedding=[float(value) for value in embedding] if embedding is not None else [],
                )
            )
        return records

    async def delete_summary_ids(self, chat_id: int, ids: list[str]) -> None:
        if not ids or not self._collection_exists(chat_id):
            return
        collection = self._get_collection(chat_id)
        collection.delete(ids=ids)

    def list_chat_ids(self) -> list[int]:
        prefix = self._settings.collection_prefix
        chat_ids: list[int] = []
        for collection in self._client.list_collections():
            name = collection.name
            if not name.startswith(prefix):
                continue
            suffix = name[len(prefix):]
            try:
                chat_ids.append(int(suffix))
            except ValueError:
                continue
        return sorted(chat_ids)
