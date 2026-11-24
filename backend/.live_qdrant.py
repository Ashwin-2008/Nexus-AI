import uuid
from app.services.vector_index import get_vector_index

idx = get_vector_index(dimensions=256)
idx.ensure_collection()
print('collection exists:', idx.collection_exists())
print('health           :', idx.health())

org, doc, chunk = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
n = idx.upsert_chunks([{
    'chunk_id': chunk, 'organization_id': org, 'document_id': doc,
    'text': 'nexus connectivity probe', 'index': 0, 'metadata': {},
}], [[0.01] * 256])
print('upserted points  :', n)
hits = idx.search(vector=[0.01] * 256, organization_id=org, top_k=3)
print('search hits      :', len(hits))
print('count for doc    :', idx.count_for_document(org, doc))
print('deleted points   :', idx.delete_document(org, doc))
print('count after clean:', idx.count_for_document(org, doc))