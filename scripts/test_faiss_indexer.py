"""Smoke test for FAISS indexer."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.indexer import (
    index_chunks, search, index_stats, prune_source,
    delete_by_source, reset_store, get_chunks_by_source,
    update_section_title,
)
from app.pipeline.chunker import Chunk

# Clean start
reset_store()

# Create test chunks
chunks = [
    Chunk(id="test_0", text="Hello world", metadata={"source_file": "test.pdf", "page": 1, "section_title": "Intro"}),
    Chunk(id="test_1", text="Hello again", metadata={"source_file": "test.pdf", "page": 1, "section_title": "Intro"}),
    Chunk(id="test_2", text="Goodbye world", metadata={"source_file": "test.pdf", "page": 2, "section_title": "Outro"}),
]

# Index
n = index_chunks(chunks, course="tort")
print(f"1. Indexed {n} chunks")
assert n == 3, f"Expected 3, got {n}"

# Stats
stats = index_stats()
print(f"2. Stats: {stats}")
assert stats["chunks"] == 3
assert stats["available"] is True

# Search
hits = search("hello world", course="tort")
print(f"3. Search results: {len(hits)} hits")
for h in hits:
    print(f"   - {h['id']}: similarity={h['similarity']}, text={h['text'][:30]}")
assert len(hits) > 0

# Get by source
by_src = get_chunks_by_source("test.pdf")
print(f"4. By source: {len(by_src)} chunks")
assert len(by_src) == 3

# Update section title
ok = update_section_title("test_0", "New Intro")
print(f"5. Update section title: {ok}")
assert ok

by_src2 = get_chunks_by_source("test.pdf")
print(f"6. Updated title: {by_src2[0].get('section_title')}")
assert by_src2[0].get("section_title") == "New Intro"

# Prune
pruned = prune_source("test.pdf", keep_ids={"test_0", "test_1"})
print(f"7. Pruned {pruned} chunks")
assert pruned == 1

stats2 = index_stats()
print(f"8. After prune: {stats2['chunks']} chunks")
assert stats2["chunks"] == 2

# Delete
deleted = delete_by_source("test.pdf")
print(f"9. Deleted {deleted} chunks")
assert deleted == 2

stats3 = index_stats()
print(f"10. After delete: {stats3['chunks']} chunks")
assert stats3["chunks"] == 0

# Test dedup
from app.pipeline.indexer import index_question_stem, find_duplicate_question, delete_question_stem

index_question_stem(1, "什么是侵权责任", "tort")
index_question_stem(2, "什么是违约责任", "tort")

dup = find_duplicate_question("什么是侵权责任", course="tort")
print(f"11. Duplicate found: {dup}")
assert dup is not None
assert dup[0] == "1"

no_dup = find_duplicate_question("什么是无因管理", course="tort")
print(f"12. No duplicate: {no_dup}")
assert no_dup is None

delete_question_stem(1)
no_dup2 = find_duplicate_question("什么是侵权责任", course="tort")
print(f"13. After delete, no duplicate: {no_dup2}")

print()
print("ALL TESTS PASSED!")