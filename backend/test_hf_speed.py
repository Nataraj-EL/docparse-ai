import os
import time
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("HUGGINGFACE_API_KEY")
print(f"API Key present: {bool(api_key)}")

if not api_key:
    print("Error: No API Key found.")
    exit(1)

client = InferenceClient(token=api_key)

# Mock Chunks (simulating a batch)
chunks = ["This is a test sentence for embedding." for _ in range(32)]

print("Sending 32 chunks to HF API...")
start = time.time()
try:
    embeddings = client.feature_extraction(chunks, model="sentence-transformers/all-MiniLM-L6-v2")
    end = time.time()
    print(f"Success! Time taken: {end - start:.2f} seconds")
    print(f"Output type: {type(embeddings)}")
    if hasattr(embeddings, 'shape'):
        print(f"Shape: {embeddings.shape}")
    elif isinstance(embeddings, list):
         print(f"List length: {len(embeddings)}")
except Exception as e:
    print(f"Error: {e}")
