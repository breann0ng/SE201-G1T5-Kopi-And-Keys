"""Committed policy vectors (data/policy_index/<date>/) round-trip and are reused only for unchanged text."""
from kopi_keys.components import policy_index


def chunk(chunk_id, heading="Eligibility conditions", content="Be at least 35 years old."):
    return {"chunk_id": chunk_id, "section_heading": heading, "policy_name": "Grants", "content": content}


def test_vectors_round_trip_by_embedded_text(tmp_path):
    chunks = [chunk("CHUNK_A_01"), chunk("CHUNK_A_02", content="Income must not exceed $9,000.")]
    vectors = [[0.25, -1.5, 3.0], [1.0, 0.0, -0.125]]
    policy_index.save_vectors("2026-10-15", chunks, vectors, "sha256:abc", data_dir=tmp_path)
    stored, meta = policy_index.load_vectors("2026-10-15", data_dir=tmp_path)
    assert meta["model_digest"] == "sha256:abc" and meta["dim"] == 3
    assert meta["chunk_ids"] == ["CHUNK_A_01", "CHUNK_A_02"]
    assert [stored[policy_index.document_sha256(c)] for c in chunks] == vectors


def test_a_changed_heading_is_a_different_embedded_text():
    # The heading is embedded with the content, so a renamed PDF page heading is re-embedded.
    assert policy_index.document_sha256(chunk("X", heading="Page 3")) != policy_index.document_sha256(
        chunk("X", heading="EHG amount for two or more first-timer singles > Page 3"))


def test_missing_or_truncated_vectors_are_not_trusted(tmp_path):
    assert policy_index.load_vectors("2026-10-15", data_dir=tmp_path) == ({}, None)
    policy_index.save_vectors("2026-10-15", [chunk("CHUNK_A_01")], [[1.0, 2.0]], None, data_dir=tmp_path)
    path = tmp_path / "policy_index" / "2026-10-15" / "vectors.f32"
    path.write_bytes(path.read_bytes()[:4])
    assert policy_index.load_vectors("2026-10-15", data_dir=tmp_path) == ({}, None)
