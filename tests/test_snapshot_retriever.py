"""SnapshotPolicyRetriever serves real policy chunks from the ACTIVE snapshot."""
import json
from pathlib import Path

import pytest

from kopi_keys.components.policy_retrieval import TOP_K, SnapshotPolicyRetriever

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def retriever():
    return SnapshotPolicyRetriever()


def test_returns_dated_passages_from_the_active_snapshot(retriever):
    active = (DATA / "policy_snapshots" / "ACTIVE").read_text(encoding="utf-8").strip()
    passages = retriever.search("Enhanced CPF Housing Grant income ceiling")
    assert 0 < len(passages) <= TOP_K
    for p in passages:
        assert p.id.startswith("CHUNK_") and p.snapshot_id == active
        assert p.source_url.startswith("https://www.") and p.verified_on is not None
        assert not p.superseded
    assert any(p.id.startswith("CHUNK_EHG_") for p in passages)


def test_unrelated_query_returns_nothing(retriever):
    assert retriever.search("zzqx flibbertigibbet") == []


def test_superseded_chunks_are_never_returned(tmp_path):
    (tmp_path / "policy_snapshots").mkdir()
    (tmp_path / "policy_snapshots" / "ACTIVE").write_text("2026-01-01", encoding="utf-8")
    chunk_dir = tmp_path / "policy_chunks" / "2026-01-01"
    chunk_dir.mkdir(parents=True)
    base = {"source_url": "https://www.hdb.gov.sg/x", "policy_name": "Test", "section_heading": "",
            "snapshot_date": "2026-01-01", "verified_on": "2026-01-01", "page_last_updated": None,
            "effective_date": None}
    rows = [{**base, "chunk_id": "CHUNK_T_01", "content": "grant ceiling old", "superseded": True},
            {**base, "chunk_id": "CHUNK_T_02", "content": "grant ceiling new", "superseded": False}]
    (chunk_dir / "chunks.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert [p.id for p in SnapshotPolicyRetriever(data_dir=tmp_path).search("grant ceiling")] == ["CHUNK_T_02"]


def test_responses_report_which_evidence_was_used(retriever):
    # The UI shows "fictional sample evidence" only for mode "demo".
    from fastapi.testclient import TestClient

    from kopi_keys.components.policy_retrieval import DemoPolicyRetriever
    from kopi_keys.components.synthesiser import Synthesiser
    from kopi_keys.graph import build_graph
    from kopi_keys.main import create_app

    def app(r):
        return TestClient(create_app(build_graph(retriever=r, synthesiser=Synthesiser(engine=None), cards=[])))

    with app(retriever) as c:
        assert c.get("/health").json()["mode"] == "snapshot"
        body = c.post("/chat", json={"message": "How long is an HFE letter valid?"}).json()
        assert body["mode"] == "snapshot"
        assert all(cite["id"].startswith("CHUNK_") for cite in body["citations"])
    with app(DemoPolicyRetriever()) as c:
        assert c.get("/health").json()["mode"] == "demo"
        assert c.post("/chat", json={"message": "What is the demo grant policy?"}).json()["mode"] == "demo"
