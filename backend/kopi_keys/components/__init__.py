"""One module per box on the architecture diagram (proposal Appendix C).

query_router      Query Router (LLM; rule-based baseline today)
topic_cards       Topic cards used by the Synthesiser for discovery (adapter to kopi_keys.topic_cards)
policy_retrieval  Policy Retrieval Tool (RAG)
price_query       Price Query Tool (SQL)
synthesiser       Synthesiser Agent (LLM; also covers discovery wording)
verifier          Verifier (deterministic checks)
abstention        Abstention Output
"""
