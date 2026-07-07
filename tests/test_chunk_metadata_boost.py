from src.retrieval.contracts import RetrievedCandidate
from src.retrieval.metadata_boost import boost_chunk_results, score_candidate_with_metadata
from src.retrieval.query_normalization import normalize_query


def test_metadata_boost_prioritizes_active_ingredient_and_drug_class():
    normalized = normalize_query("Differin thuộc nhóm gì?")
    matching = RetrievedCandidate(
        candidate_id="chunk:match",
        source="chunk",
        collection="acne_knowledge",
        text="Differin contains adapalene.",
        score=0.1,
        payload={
            "chunk_id": "chunk:match",
            "active_ingredient": ["adapalene"],
            "drug_class": ["topical_retinoid"],
        },
    )
    boosted = score_candidate_with_metadata(matching, normalized)

    assert boosted.fused_score is not None
    assert boosted.fused_score > matching.score
    assert boosted.matched_metadata["active_ingredient"] == ["adapalene"]
    assert boosted.matched_metadata["drug_class"] == ["topical_retinoid"]


def test_acne_type_boost_uses_concern_and_condition_metadata():
    normalized = normalize_query("Mụn đầu đen là gì?")
    chunks = [
        {
            "id": "drug",
            "text": "Drug-only chunk",
            "score": 0.2,
            "active_ingredient": ["clindamycin"],
        },
        {
            "id": "blackhead",
            "text": "Blackheads are comedonal acne.",
            "score": 0.1,
            "condition": ["acne_vulgaris"],
            "concern": ["blackheads"],
            "content_type": ["acne_type"],
        },
    ]
    boosted = boost_chunk_results(chunks, normalized)

    assert boosted[0].candidate_id == "blackhead"
    assert "concern" in boosted[0].matched_metadata
    assert boosted[0].payload["text"] == "Blackheads are comedonal acne."
