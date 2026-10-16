from seed_knowledge_base import load_documents


def test_synthetic_policies_are_the_seed_source() -> None:
    documents = load_documents()

    assert len(documents) == 6
    assert {document["source"] for document in documents} == {
        "builtin://account-policy",
        "builtin://coupon-policy",
        "builtin://logistics-policy",
        "builtin://order-payment-policy",
        "builtin://privacy-policy",
        "builtin://refund-policy",
    }
    assert all(document["title"] and document["content"] for document in documents)
