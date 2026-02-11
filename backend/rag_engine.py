from sentence_transformers import SentenceTransformer
from chromadb import PersistentClient
import fitz  # PyMuPDF
import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# Lazy loading globals
_embedding_model = None
_chroma_client = None
_collection = None

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        print("[INFO] Loading SentenceTransformer model...")
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model

def get_collection():
    global _chroma_client, _collection
    if _collection is None:
        print("[INFO] Connecting to ChromaDB...")
        _chroma_client = PersistentClient(path="chroma_db")
        _collection = _chroma_client.get_or_create_collection("pdf_collection")
    return _collection

def process_pdf(pdf_path: str, session_id: str) -> bool:
    """Process a PDF file and store its chunks in ChromaDB with session isolation."""
    filename = os.path.basename(pdf_path)
    try:
        # Use a localized print or a safe approach for Tamil filenames
        try:
            print(f"[DEBUG] Processing PDF: {filename} for Session: {session_id}")
        except UnicodeEncodeError:
            print(f"[DEBUG] Processing PDF: (Contains non-ASCII characters) for Session: {session_id}")

        text = ""
        # Use PyMuPDF (fitz) for much more robust extraction
        with fitz.open(pdf_path) as doc:
            num_pages = len(doc)
            print(f"[DEBUG] PDF has {num_pages} pages.")
            for i, page in enumerate(doc):
                try:
                    page_text = page.get_text()
                    if page_text:
                        text += page_text + "\n"
                except Exception as e:
                    print(f"[WARNING] Could not extract text from page {i}: {e}")
        
        if not text.strip():
            print("[DEBUG] Extracted text is empty. PDF might be scanned or encrypted.")
            return False 

        print(f"[DEBUG] Extracted text length: {len(text)}")

        # Improved chunking with overlap
        chunk_size = 1000
        overlap = 200
        chunks = []
        for i in range(0, len(text), chunk_size - overlap):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chunks.append(chunk)
                
        print(f"[DEBUG] Created {len(chunks)} chunks.")
        
        if not chunks:
            print("[DEBUG] No chunks to encode.")
            return True 

        # Batch processing for embeddings and ChromaDB storage
        # Reduced batch size to 32 for better performance on Railway CPU tiers
        batch_size = 32
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            
            # EMBEDDING STRATEGY:
            try:
                # feature_extraction returns a list of arrays
                if hf_client:
                    print(f"[DEBUG] Attempting HF API Embedding for batch {i//batch_size + 1}...")
                    api_embeddings = hf_client.feature_extraction(batch_chunks, model="sentence-transformers/all-MiniLM-L6-v2")
                    
                    # Ensure it's a list of lists/arrays. API might return different formats.
                    if isinstance(api_embeddings, list) or (hasattr(api_embeddings, 'shape') and len(api_embeddings.shape) > 0):
                       batch_embeddings = api_embeddings
                       print(f"[SUCCESS] Used HF API for batch {i//batch_size + 1}")
                    else:
                       print(f"[ERROR] Invalid API response format: {type(api_embeddings)}")
                       raise ValueError("Invalid API response format")
                else:
                    print("[WARNING] No HF Client available (Check HUGGINGFACE_API_KEY)")
                    raise ValueError("No HF Client available")
            except Exception as e:
                print(f"[WARNING] HF API Embedding failed: {e}. Falling back to Local CPU.")
                # Fallback to Local CPU
                try:
                    print(f"[INFO] Using Local CPU Embedding for batch {i//batch_size + 1}...")
                try:
                    batch_embeddings = get_embedding_model().encode(batch_chunks)
                except Exception as ex:
                    print(f"[ERROR] Local embedding failed: {ex}")
                    raise ex
            try:
                batch_embeddings = get_embedding_model().encode(batch_chunks)
            except Exception as e:
                print(f"[ERROR] Local embedding failed: {e}")
                raise e
            
            # Generate unique IDs for each chunk
            base_id = f"{filename}_{os.path.getmtime(pdf_path)}"
            batch_ids = [f"{base_id}_chunk_{i+j}" for j in range(len(batch_chunks))]
            
            # Add session_id to metadata for EVERY chunk
            batch_metadatas = [{"session_id": session_id, "source": filename} for _ in batch_chunks]
            
            get_collection().add(
                documents=batch_chunks, 
                embeddings=[emb.tolist() if hasattr(emb, 'tolist') else emb for emb in batch_embeddings],
                ids=batch_ids,
                metadatas=batch_metadatas
            )
            print(f"[DEBUG] Processed batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")
        
        print(f"[DEBUG] PDF processing complete for {filename}.")
        return True
        
    except Exception as e:
        print(f"[ERROR] process_pdf failed: {e}")
        import traceback
        traceback.print_exc()
        raise e

def list_documents(session_id: str) -> List[Dict[str, Any]]:
    """List all unique documents stored in ChromaDB for a specific session."""
    try:
        # Get all IDs and metadatas, filtered by session_id
        results = get_collection().get(
            where={"session_id": session_id},
            include=["metadatas"]
        )
        
        if not results or not results["ids"]:
            return []
            
        # Extract unique filenames from IDs (using our naming convention: filename_chunk_...)
        # Naming convention: f"{filename}_chunk_{i}_{hash(chunk)}"
        filenames = set()
        for doc_id in results["ids"]:
            if "_chunk_" in doc_id:
                filenames.add(doc_id.split("_chunk_")[0])
            else:
                # Fallback if naming convention differs (older versions)
                filenames.add(doc_id)
                
        return [{"filename": name} for name in sorted(list(filenames))]
    except Exception as e:
        print(f"[ERROR] list_documents failed: {e}")
        return []

def delete_document(filename: str, session_id: str) -> bool:
    """Delete all chunks associated with a specific filename and session."""
    try:
        # Get all IDs to find matches ensuring they belong to the session
        results = get_collection().get(
            where={"session_id": session_id}
        )
        if not results or not results["ids"]:
            return False
            
        ids_to_delete = [doc_id for doc_id in results["ids"] if doc_id.startswith(filename + "_chunk_") or doc_id == filename]
        
        if ids_to_delete:
            get_collection().delete(ids=ids_to_delete)
            print(f"[DEBUG] Deleted {len(ids_to_delete)} chunks for {filename}.")
            return True
        return False
    except Exception as e:
        print(f"[ERROR] delete_document failed: {e}")
        return False

from groq import Groq
from huggingface_hub import InferenceClient

# Initialize clients
# CRITICAL FIX: Strip newline characters that might be present in the env var
groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
client = Groq(api_key=groq_api_key) if groq_api_key else None

hf_api_key = os.getenv("HUGGINGFACE_API_KEY", "").strip()
hf_client = InferenceClient(token=hf_api_key) if hf_api_key else None

def query_groq(prompt: str, system_prompt: str = None) -> str:
    """
    Query the Groq API with the given prompt using the Llama 3 model.
    """
    try:
        if not client:
             return "Error: GROQ_API_KEY not found. Please set it in your environment."

        if system_prompt is None:
            system_prompt = ("You are a helpful research assistant. "
                           "Answer the question based on the provided context. "
                           "If the context doesn't contain enough information, "
                           "say that you don't have enough information to answer.")

        # Format the messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        # Make the API request using Groq
        response = client.chat.completions.create(
            messages=messages,
            model="llama3-8b-8192",
            temperature=0.3,
            max_tokens=1024,
            top_p=0.85,
            stop=None,
            stream=False
        )
        
        # Parse the response
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"Error querying Groq API: {str(e)}")
        return f"Error: Failed to get response from Groq. {str(e)}"

def ask_query(query: str, session_id: str) -> str:
    """
    Process a query using RAG with Hugging Face's Llama 3 model, isolated to session.
    
    Args:
        query (str): The user's question
        session_id (str): The session ID to restrict context to
        
    Returns:
        str: The generated answer with context from the knowledge base
    """
    try:
        # Encode the query to get embeddings
        query_embedding = get_embedding_model().encode([query])[0]
        
        # Query ChromaDB for relevant context, filtered by session_id
        results = get_collection().query(
            query_embeddings=[query_embedding.tolist()],
            n_results=5,
            where={"session_id": session_id},
            include=["documents", "distances", "metadatas"]
        )
        
        # Extract and format the context
        context_chunks = []
        if results and "documents" in results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                # Relax threshold to ensure content retrieval
                threshold = 3.0
                if "summarize" in query.lower() or "summary" in query.lower():
                    threshold = 10.0
                
                # Only include documents with high enough similarity
                if "distances" in results and results["distances"][0][i] < threshold:
                    # Get filename from IDs convention: filename_chunk_...
                    doc_id = results["ids"][0][i]
                    filename = doc_id.split("_chunk_")[0] if "_chunk_" in doc_id else "Unknown"
                    context_chunks.append(f"SOURCE: {filename}\nCONTENT: {doc.strip()}")
        
        # Fallback: If no context passed the threshold but we have results, include the top 1 result
        if not context_chunks and results and "documents" in results and results["documents"]:
             if results["documents"][0]:
                 doc_id = results["ids"][0][0]
                 filename = doc_id.split("_chunk_")[0] if "_chunk_" in doc_id else "Unknown"
                 context_chunks.append(f"SOURCE: {filename}\nCONTENT: {results['documents'][0][0].strip()}")
        
        # If no relevant context found, let the model know
        if not context_chunks:
            context = "No relevant context found in the knowledge base."
        else:
            context = "\n\n---\n\n".join(context_chunks)
        
        # Create the comprehensive system prompt based on user requirements
        system_prompt = """You are DocParse AI, an advanced academic research assistant.
You must behave like a professional exam assistant and subject matter expert.

====================
CORE DIRECTIVES:
====================
1. IDENTITY: You are a helpful, harmless, and honest academic assistant.
2. STRICT DEDUPLICATION: Do NOT repeat the same fact or phrase. Synthesize info.
3. CITATIONS: Attribute every claim using [Source: filename.pdf].
4. MATH: Use standard LaTeX for formulas. Inline: `$E=mc^2$`. Block: `$$E=mc^2$$`. Do NOT use "mathmath" or other prefixes.
5. NO FILLER: Start directly with the answer. Do not say "Here is the summary" or "Based on the document".

====================
MULTILINGUAL INTELLIGENCE (CRITICAL):
====================
**DEFAULT LANGUAGE**: English. Always respond in English unless the user explicitly uses Tamil/Tanglish.

**LANGUAGE TRIGGER RULES (Tanglish Priority)**:
- **Default**: English for general queries.
- **Tanglish (Preferred for Local users)**: If user uses Tamil script OR Tanglish phrases for *technical/general* topics, output **Tanglish**.
- **Pure Tamil (Senthamil)**: Use ONLY if the user explicitly asks "In pure Tamil" or "Senthamil-la sollu".

**NEGATIVE CONSTRAINTS (CRITICAL)**:
- **NO DUAL LANGUAGE OUTPUT**: Never provide an English answer followed by a Tamil translation. Choose ONE language based on the trigger rules.
- **NO UNPROMPTED TRANSLATIONS**: If the user asks in English, the output must be 100% English. Do not add "In pure Tamil: ..." at the end.

**TANGLISH GUIDELINES (Conversational & Technical)**:
- **Style**: "Spoken Tamil" grammar with English technical vocabulary.
- **Rule**: NEVER translate technical terms (e.g., Data, AI, Machine Learning).
- **Structure**: Subject-Object-Verb (Tamil syntax) but with English nouns.
- **Tone**: Friendly, clear, and natural (like a professor explaining to a student in a canteen).
- **Example**:
  - "Machine Learning enna pannum-na, data-va use panni patterns-a kandupidikkum."
  - "Oru simple example: Spam emails-a filter panrathu."

**FORMAL TAMIL GUIDELINES (Deprioritized)**:
- Use this ONLY upon explicit request for "Pure Tamil".
- Strict grammatical correctness required.

====================
[PROTOCOL - REFUSAL]
====================
If the context is insufficient:
- English: "The provided document does not contain sufficient information to answer this question."
- Tamil: "மன்னிக்கவும், கொடுக்கப்பட்ட ஆவணத்தில் இதற்கான தகவல் இல்லை."
- Tanglish: "Sorry, kudukkapatta document-la intha kelvikku answer illa."

====================
FORMATTING:
====================
- Use bullet points (•) for lists.
- **No mixed scripts in headers**: If answering in Tamil, headers must be in Tamil.
- Keep paragraphs short and readable.
"""
        
        # Create the user message with context and question
        base_instruction = "Answer based on the content below 'Uploaded Document Content' only."
        if "summarize" in query.lower() or "summary" in query.lower():
            base_instruction = "Summarize the content under 'Uploaded Document Content'. Do not summarize these instructions."

        user_message = f"""Uploaded Document Content:
{context}

Question: {query}
{base_instruction}"""

        # Get response from Groq
        response = query_groq(user_message, system_prompt=system_prompt)
        
        # Post-process the response if needed
        if not response or response.strip() == "":
            return "I'm sorry, I couldn't generate a response. Please try again or rephrase your question."
            
        final_response = response.strip()
        
        # Enforce strict Missing Information Rule ONLY for the specific phrase
        missing_info_phrase = "The provided document does not contain sufficient information to answer this question."
        if missing_info_phrase in final_response:
            # If the phrase is present, we assume it's a refusal and strip other text.
            # However, user says "Do NOT use this response for summaries...".
            # The prompt instructs the model when to use it.
            # We trust the model slightly, but enforce the *format* if it decides to refuse.
            final_response = missing_info_phrase

        # Footer enforcement REMOVED as per user request.
            
        return final_response
        
    except Exception as e:
        error_msg = f"Error processing your query: {str(e)}"
        print(f"Error in ask_query: {error_msg}")
        return error_msg
