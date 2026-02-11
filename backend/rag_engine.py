from sentence_transformers import SentenceTransformer
from chromadb import PersistentClient
import fitz  # PyMuPDF
import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
chroma_client = PersistentClient(path="chroma_db")
collection = chroma_client.get_or_create_collection("pdf_collection")

def process_pdf(pdf_path: str) -> bool:
    """Process a PDF file and store its chunks in ChromaDB."""
    filename = os.path.basename(pdf_path)
    try:
        # Use a localized print or a safe approach for Tamil filenames
        try:
            print(f"[DEBUG] Processing PDF: {filename}")
        except UnicodeEncodeError:
            print(f"[DEBUG] Processing PDF: (Contains non-ASCII characters)")

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
            batch_embeddings = embedding_model.encode(batch_chunks)
            
            # Generate unique IDs for each chunk
            # Using chunk index and file stats to ensure uniqueness
            base_id = f"{filename}_{os.path.getmtime(pdf_path)}"
            batch_ids = [f"{base_id}_chunk_{i+j}" for j in range(len(batch_chunks))]
            
            collection.add(
                documents=batch_chunks, 
                embeddings=[emb.tolist() for emb in batch_embeddings],
                ids=batch_ids
            )
            print(f"[DEBUG] Processed batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")
        
        print(f"[DEBUG] PDF processing complete for {filename}.")
        return True
        
    except Exception as e:
        print(f"[ERROR] process_pdf failed: {e}")
        import traceback
        traceback.print_exc()
        raise e

def list_documents() -> List[Dict[str, Any]]:
    """List all unique documents stored in ChromaDB."""
    try:
        # Get all IDs and metadatas
        # ChromaDB query with no filter returns everything if parameters are set right
        results = collection.get(include=["metadatas"])
        
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

def delete_document(filename: str) -> bool:
    """Delete all chunks associated with a specific filename."""
    try:
        # Get all IDs to find matches
        results = collection.get()
        if not results or not results["ids"]:
            return False
            
        ids_to_delete = [doc_id for doc_id in results["ids"] if doc_id.startswith(filename + "_chunk_") or doc_id == filename]
        
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            print(f"[DEBUG] Deleted {len(ids_to_delete)} chunks for {filename}.")
            return True
        return False
    except Exception as e:
        print(f"[ERROR] delete_document failed: {e}")
        return False

from huggingface_hub import InferenceClient

# Initialize the client at module level
# CRITICAL FIX: Strip newline characters that might be present in the env var
client = InferenceClient(token=os.getenv("HUGGINGFACE_API_KEY", "").strip())

def query_huggingface(prompt: str, system_prompt: str = None) -> str:
    """
    Query the Hugging Face API with the given prompt using the Llama 3 model via InferenceClient.
    
    Args:
        prompt (str): The prompt to send to the model (user message)
        system_prompt (str, optional): The system prompt to use. Defaults to a generic helpful assistant prompt.
        
    Returns:
        str: The generated response from the model
    """
    try:
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
        
        # Make the API request using InferenceClient
        response = client.chat_completion(
            messages=messages,
            model="meta-llama/Meta-Llama-3-8B-Instruct",
            max_tokens=1024,
            temperature=0.7,
            top_p=0.9,
            frequency_penalty=1.1,
            presence_penalty=1.0
        )
        
        # Parse the response
        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content.strip()
        return "Error: Empty response from model."
        
    except Exception as e:
        print(f"Error querying Hugging Face API: {str(e)}")
        return f"Error: Failed to get response from the AI model. {str(e)}"

def ask_query(query: str) -> str:
    """
    Process a query using RAG with Hugging Face's Llama 3 model.
    
    Args:
        query (str): The user's question
        
    Returns:
        str: The generated answer with context from the knowledge base
    """
    try:
        # Encode the query to get embeddings
        query_embedding = embedding_model.encode([query])[0]
        
        # Query ChromaDB for relevant context
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=5,
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
4. MATH: Render all technical formulas in LaTeX: `$math$` for inline, `$$math$$` for blocks.

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

        # Get response from Hugging Face
        response = query_huggingface(user_message, system_prompt=system_prompt)
        
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
