from fastapi import FastAPI, UploadFile, Form, Request, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from rag_engine import process_pdf, ask_query, query_groq, list_documents, delete_document, delete_all_documents
import os
import time
import json
import shutil
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Validate required environment variables
if not os.getenv("GROQ_API_KEY"):
    print("WARNING: GROQ_API_KEY environment variable is not set. AI features will fail.")

app = FastAPI()

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Log request
    request_id = str(hash(time.time()))
    
    # Log request details
    print(f"\n{'='*50}")
    print(f"[{request_id}] {request.method} {request.url}")
    print(f"Headers: {dict(request.headers)}")
    
    # Log request body if present (only for JSON/text, skip for multiparts/binary)
    content_type = request.headers.get("content-type", "")
    if request.method not in ["GET", "HEAD"] and "multipart/form-data" not in content_type:
        try:
            # We must be careful about consuming the stream. 
            # For logging, we'll only try if it's likely to be small and purposeful.
            # However, in many FastAPI setups, reading body here breaks the route.
            # To stay safe and fulfill the "logging" without crashing, we skip large/binary bodies.
            pass # Skipping body logging in middleware to avoid breaking multipart streams
        except Exception as e:
            print(f"Error reading request body: {e}")
    
    start_time = time.time()
    
    # Process the request
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[{request_id}] UNHANDLED ERROR: {str(e)}")
        print(error_trace)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal Server Error",
                "message": str(e),
                "request_id": request_id
            }
        )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred on the server.",
            "message": str(exc)
        },
    )

# CORS configuration
origins = ["*"]  # Allow all origins for production (Vercel -> Railway)

# Add CORS middleware with explicit configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=[
        "*",  # Allow all headers
        "Authorization",
        "Content-Type",
        "X-Requested-With",
        "Accept",
        "Origin",
        "Access-Control-Allow-Origin",
    ],
    expose_headers=[
        "*",
        "Content-Disposition",
        "X-Request-ID",
        "Access-Control-Allow-Origin",
    ],
    max_age=600,  # Cache preflight request for 10 minutes
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "timestamp": time.time(),
        "environment": os.getenv("ENVIRONMENT", "development"),
    }

from typing import Dict, Any, Optional, List

# ... (existing code)

@app.post("/upload")
async def upload_pdf(files: List[UploadFile], x_session_id: str = Header(...)):
    """Handle multiple PDF file uploads for processing with session isolation."""
    # Create temp directory if it doesn't exist
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)
    
    results = []
    
    for file in files:
        # Sanitize filename and use a unique prefix to avoid collisions/encoding issues in filesystem
        clean_filename = "".join([c for c in file.filename if c.isalnum() or c in "._-"]).strip()
        if not clean_filename:
            clean_filename = "document.pdf"
        
        file_id = f"{int(time.time())}_{clean_filename}"
        file_path = temp_dir / file_id
        
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Process the PDF - pass original filename for display if needed
            # For now, process_pdf uses the filename from the path
            success = process_pdf(str(file_path), x_session_id)
            if success:
                results.append({"filename": file.filename, "status": "success"})
            else:
                results.append({"filename": file.filename, "status": "failed", "error": "AI processing failed to extract text."})
        except Exception as e:
            print(f"[ERROR] Upload failed for {file.filename}: {str(e)}")
            results.append({"filename": file.filename, "status": "error", "error": str(e)})
        finally:
            # Clean up the temporary file ALWAYS after processing (saved to ChromaDB anyway)
            if file_path.exists():
                file_path.unlink()
    
    # Check if all failed
    if all(r["status"] != "success" for r in results):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"All uploads failed: {results}"
        )
        
    return {"message": "Files processed", "details": results}


@app.post("/ask")
async def ask_question(query: str = Form(...), x_session_id: str = Header(...)):
    """Handle question-answering using the RAG system with session isolation."""
    if not query or not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty"
        )
    
    try:
        answer = ask_query(query, x_session_id)
        return {
            "answer": answer,
            "status": "success",
            "model": "meta-llama/Meta-Llama-3-8B-Instruct"
        }
    except Exception as e:
        print(f"Error in ask_question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing your question: {str(e)}"
        )

@app.get("/documents")
async def get_documents(x_session_id: str = Header(...)):
    """List all unique documents in the knowledge base for the session."""
    return {"documents": list_documents(x_session_id)}

@app.delete("/documents/{filename}")
async def remove_document(filename: str, x_session_id: str = Header(...)):
    """Delete a document and its chunks from the knowledge base for the session."""
    success = delete_document(filename, x_session_id)
    if success:
        return {"message": f"Successfully deleted {filename}"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {filename} not found or could not be deleted"
        )

@app.get("/test-groq")
async def test_groq():
    """Test endpoint to verify Groq API connectivity."""
    test_prompt = "Hello, how are you?"
    try:
        response = query_groq(test_prompt)
        return {
            "status": "success",
            "response": response,
            "model": "llama-3.3-70b-versatile"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to connect to Groq API. Please check your API key."
        }
