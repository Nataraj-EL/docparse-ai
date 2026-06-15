"use client";

import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import React, { useState, useEffect, useRef } from "react";
import { API_CONFIG } from "../config/api";

export default function Home() {
  const [messages, setMessages] = useState<{ sender: string; text: string }[]>([]);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [darkMode, setDarkMode] = useState(false); // Default to Light Mode
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [availableDocuments, setAvailableDocuments] = useState<{ filename: string }[]>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // Check backend health with retry mechanism
  const checkBackendHealth = async (retries = 20, delay = 3000) => {
    try {
      const response = await fetch(`${API_CONFIG.baseURL}/health`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store'
      });
      if (response.ok) {
        setBackendStatus('online');
        return;
      }
    } catch (error) {
      // Sielntly fail during retries
    }

    if (retries > 0) {
      setTimeout(() => checkBackendHealth(retries - 1, delay), delay);
    } else {
      setBackendStatus('offline');
    }
  };

  const fetchDocuments = async () => {
    const sid = localStorage.getItem("docparse_session_id") || "";
    try {
      const response = await fetch(`${API_CONFIG.baseURL}/documents`, {
        headers: {
          'X-Session-ID': sid
        }
      });
      if (response.ok) {
        const data = await response.json();
        setAvailableDocuments(data.documents);
      }
    } catch (error) {
      console.error('Error fetching documents:', error);
    }
  };

  useEffect(() => {
    let isMounted = true;

    // Generate or retrieve Session ID
    let sid = localStorage.getItem("docparse_session_id");
    if (!sid) {
      sid = typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : Math.random().toString(36).substring(2) + Date.now().toString(36);
      localStorage.setItem("docparse_session_id", sid);
    }

    // Initial fetch
    if (isMounted) {
      checkBackendHealth();
      fetchDocuments();
    }

    // Cleanup function to prevent state updates after unmount
    return () => {
      isMounted = false;
    };
  }, []);

  const handleDeleteDocument = async (filename: string) => {
    if (!confirm(`Are you sure you want to remove ${filename} from your library?`)) return;

    try {
      const sid = localStorage.getItem("docparse_session_id") || "";
      const response = await fetch(`${API_CONFIG.baseURL}/documents/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
        headers: {
          'X-Session-ID': sid
        }
      });
      if (response.ok) {
        fetchDocuments(); // Refresh list
      }
    } catch (error) {
      console.error('Error deleting document:', error);
    }
  };

  const handleUpload = async (filesToUpload: File[]) => {
    if (filesToUpload.length === 0) {
      alert('Please select at least one file first');
      return;
    }

    try {
      setLoading(true);
      const formData = new FormData();
      filesToUpload.forEach(file => {
        formData.append("files", file);
      });

      const sid = localStorage.getItem("docparse_session_id") || "";
      const response = await fetch(`${API_CONFIG.baseURL}${API_CONFIG.endpoints.upload}`, {
        method: 'POST',
        headers: {
          'X-Session-ID': sid
        },
        body: formData,
      });

      if (!response.ok) {
        const text = await response.text();
        let errorMessage = 'Failed to upload files';
        try {
          const errorJson = JSON.parse(text);
          console.error("Full Upload Error JSON:", errorJson);

          const rawError = errorJson.detail || errorJson.message || errorJson.error;

          if (typeof rawError === 'string') {
            errorMessage = rawError;
          } else if (typeof rawError === 'object') {
            errorMessage = JSON.stringify(rawError, null, 2);
          } else {
            errorMessage = JSON.stringify(errorJson);
          }
        } catch (e) {
          errorMessage = `Server Error (${response.status}): ${text.slice(0, 100)}`;
        }
        throw new Error(errorMessage);
      }

      const result = await response.json();
      console.log(`Successfully uploaded ${filesToUpload.length} file(s)!`);
      alert(`✅ ${filesToUpload.length} File(s) successfully uploaded and processed!`);
      await fetchDocuments();
    } catch (error) {
      console.error('Upload error:', error);
      alert(`Upload failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setFiles([]);
    } finally {
      setLoading(false);
    }
  };

  const handleAsk = async () => {
    const query = input.trim();
    if (!query) return;

    // Clear input IMMEDIATELY as per requirement
    setInput("");
    setLoading(true);

    try {
      const userMessage = { sender: "user" as const, text: query };
      setMessages(prev => [...prev, userMessage]);

      const formData = new FormData();
      formData.append("query", query);

      const sid = localStorage.getItem("docparse_session_id") || "";
      const response = await fetch(`${API_CONFIG.baseURL}${API_CONFIG.endpoints.ask}`, {
        method: 'POST',
        headers: {
          'X-Session-ID': sid
        },
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to get response');
      }

      const data = await response.json();
      setMessages(prev => [...prev, { sender: "bot" as const, text: data.answer }]);
    } catch (error) {
      console.error('Error asking question:', error);
      setMessages(prev => [...prev, {
        sender: "bot" as const,
        text: `Sorry, I encountered an error: ${error instanceof Error ? error.message : 'Unknown error'}`
      }]);
    } finally {
      setLoading(false);
    }
  };

  // Render error state if backend is offline
  if (backendStatus === 'offline') {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="max-w-md p-6 bg-red-50 border border-red-200 rounded-lg text-center">
          <h2 className="text-xl font-semibold text-red-700 mb-2">Backend Unavailable</h2>
          <p className="text-red-600 mb-4">
            Unable to connect to the backend service. Please ensure the backend server is running.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }  return (
    <div className={`${darkMode ? 'dark' : ''} h-screen flex flex-col overflow-hidden selection:bg-primary/20`}>
      <main className="flex flex-1 bg-background text-foreground relative h-full overflow-hidden">

        {/* Mobile Backdrop Overlay */}
        {isSidebarOpen && (
          <div
            className="fixed inset-0 bg-background/80 backdrop-blur-sm z-[105] transition-opacity"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}

        {/* Document Dashboard Sidebar */}
        <aside
          className={`fixed inset-y-0 left-0 z-[110] w-[80%] md:w-80 bg-card/95 backdrop-blur-xl border-r border-border transition-transform duration-300 ease-in-out ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full shadow-none'} shadow-xl`}
        >
          <div className="flex flex-col h-full">
            <div className="p-6 border-b border-border flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-primary">Library</h2>
              <button
                onClick={() => setIsSidebarOpen(false)}
                className="p-2 hover:bg-muted rounded-full transition-colors flex items-center justify-center text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                aria-label="Close Sidebar"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              <div className="space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground px-2">Active Knowledge Base</p>
                {availableDocuments.length === 0 ? (
                  <div className="p-8 text-center border-2 border-dashed border-border rounded-2xl">
                    <p className="text-xs text-muted-foreground">No documents processed yet.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {availableDocuments.map((doc, idx) => (
                      <div
                        key={idx}
                        className="group flex items-center justify-between p-3 bg-card rounded-xl border border-border hover:border-primary transition-all"
                      >
                        <div className="flex items-center gap-3 overflow-hidden">
                          <svg className="w-4 h-4 text-primary shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          <span className="text-xs font-semibold truncate max-w-[140px] font-sans">{doc.filename}</span>
                        </div>
                        <button
                          onClick={() => handleDeleteDocument(doc.filename)}
                          className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-destructive/10 text-destructive rounded-lg transition-all flex items-center justify-center"
                          title="Remove from library"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="p-6 border-t border-border">
              <label
                htmlFor="file-upload"
                className="w-full py-3 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-xs font-bold tracking-wider uppercase flex items-center justify-center gap-2 cursor-pointer transition-all active:scale-95"
              >
                <svg className="w-4 h-4 text-primary-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
                </svg>
                Add New Knowledge
              </label>
            </div>
          </div>
        </aside>

        {/* Main Chat Interface */}
        <div className="flex-1 relative h-screen overflow-hidden bg-background">
          {/* Header - Truly Rigid Fixed at Top */}
          <header className="fixed top-0 left-0 right-0 z-[100] px-4 pt-4 flex justify-center pointer-events-none">
            <div className="w-full max-w-5xl bg-card/90 backdrop-blur-md border border-border shadow-md rounded-2xl md:rounded-3xl p-3 md:p-4 flex items-center justify-between transition-all duration-300 pointer-events-auto">
              <div className="flex items-center gap-4">
                <button
                  onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                  className="p-3 bg-card hover:bg-muted rounded-xl border border-border hover:scale-105 active:scale-95 transition-all flex items-center justify-center"
                  aria-label="Toggle Sidebar"
                >
                  <svg className="w-5 h-5 text-slate-700 dark:text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                </button>
                <div className="min-w-0 flex-1 pr-4 cursor-default">
                  <h1 className="text-xl md:text-2xl font-normal tracking-tight text-primary font-serif truncate pr-2">
                    DocParse <span className="font-light text-muted-foreground">AI</span>
                  </h1>
                  <div className="flex items-center gap-2">
                    <span className={`h-1.5 w-1.5 rounded-full animate-pulse ${backendStatus === 'online' ? 'bg-primary' : 'bg-destructive'}`}></span>
                    <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground font-sans truncate">{backendStatus === 'online' ? 'Active' : 'Offline'}</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {/* Upload Button */}
                <button
                  onClick={() => document.getElementById('file-upload')?.click()}
                  className="p-3 bg-card hover:bg-muted rounded-xl border border-border hover:scale-105 active:scale-95 transition-all flex items-center justify-center"
                  title="Upload PDF"
                >
                  <svg className="w-5 h-5 text-slate-700 dark:text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
                  </svg>
                </button>

                {/* Theme Toggle Button */}
                <button
                  onClick={() => setDarkMode(!darkMode)}
                  className="p-3 bg-card hover:bg-muted rounded-xl border border-border hover:scale-105 active:scale-95 transition-all flex items-center justify-center"
                  title={darkMode ? "Switch to Light Mode" : "Switch to Dark Mode"}
                >
                  {darkMode ? (
                    <svg className="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m0-12.728l.707.707m12.728 12.728l.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          </header>

          {/* Background Decorative Elements (Blobs) */}
          <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-primary/5 rounded-full blur-[100px] pointer-events-none" />
          <div className="absolute bottom-[-10%] left-[-10%] w-[40%] h-[40%] bg-muted/10 rounded-full blur-[100px] pointer-events-none" />

          {/* Chat History Container - Scrollable with rigid padding */}
          <div
            ref={chatContainerRef}
            className="h-full overflow-y-auto px-4 md:px-8 pt-48 pb-48 custom-scrollbar scroll-smooth w-full max-w-5xl mx-auto"
          >
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-8 max-w-2xl mx-auto">
                <h2 className="text-3xl md:text-4xl font-normal text-foreground mb-4 tracking-tight font-serif">
                  Universal Document Intelligence
                </h2>
                <p className="text-sm md:text-base text-muted-foreground max-w-lg mx-auto leading-relaxed px-4 mb-8">
                  Upload research papers, books, or study materials. I'll provide structured insights, summaries, and answers with professional clarity.
                </p>
                <label
                  htmlFor="file-upload"
                  className="px-8 py-3 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-xs font-bold tracking-wider uppercase flex items-center gap-2 cursor-pointer transition-all active:scale-95"
                >
                  <svg className="w-4 h-4 text-primary-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                  Upload PDF Documents
                </label>
              </div>
            ) : (
              messages.map((m, idx) => (
                <div
                  key={idx}
                  className={`flex ${m.sender === "user" ? "justify-end" : "justify-start"} animate-in fade-in slide-in-from-bottom-2 duration-300 w-full mb-8`}
                >
                  <div
                    className={`max-w-[85%] p-5 rounded-2xl border ${m.sender === "user"
                      ? "bg-primary text-primary-foreground border-primary rounded-tr-none"
                      : "bg-card text-foreground border-border rounded-tl-none"
                      }`}
                  >
                    <div className="prose prose-sm dark:prose-invert max-w-none font-sans overflow-hidden">
                      <ReactMarkdown
                        remarkPlugins={[remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                        components={{
                          h1: ({ children }) => <h1 className="border-b border-border pb-2 mb-4 text-xl font-semibold font-serif">{children}</h1>,
                          h2: ({ children }) => <h2 className="text-lg font-semibold mt-6 mb-3 flex items-center gap-2 text-primary">
                            <span className="w-1.5 h-5 bg-primary rounded-full"></span>
                            {children}
                          </h2>,
                          ul: ({ children }) => <ul className="list-none space-y-3 mb-6">{children}</ul>,
                          li: ({ children }) => (
                            <li className="flex gap-2 leading-relaxed">
                              <span className="text-primary font-bold">•</span>
                              <span>{children}</span>
                            </li>
                          ),
                          strong: ({ children }) => <strong className="font-semibold text-primary px-1">{children}</strong>,
                          p: ({ children }) => {
                            return (
                              <p className="mb-4 last:mb-0 leading-relaxed font-sans">
                                {React.Children.map(children, (child) => {
                                  if (typeof child === 'string') {
                                    const parts = child.split(/(\[Source:.*?\])/g);
                                    return parts.map((part, i) => {
                                      if (part.startsWith("[Source:")) {
                                        return (
                                          <span key={i} className="inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 bg-muted text-primary text-[10px] font-semibold rounded border border-border transition-all hover:scale-105">
                                            <svg className="w-3 h-3 text-primary mr-0.5 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                            </svg>
                                            {part.replace("[Source: ", "").replace("]", "")}
                                          </span>
                                        );
                                      }
                                      return part;
                                    });
                                  }
                                  return child;
                                })}
                              </p>
                            );
                          },
                          em: ({ children }) => {
                            return <em className="italic text-muted-foreground bg-muted px-1 rounded">{children}</em>;
                          }
                        }}
                      >
                        {m.text}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              ))
            )}
            {loading && (
              <div className="flex justify-start animate-in fade-in duration-300">
                <div className="bg-card p-4 rounded-xl border border-border shadow-sm flex items-center gap-4">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:0.2s]"></div>
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:0.4s]"></div>
                  </div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-primary">Synthesis...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Footer & Input Overlay - Truly Rigid Fixed at Bottom */}
          <footer className="fixed bottom-0 left-0 right-0 z-[100] p-4 md:p-6 flex justify-center pointer-events-none">
            <div className="w-full max-w-5xl bg-background/95 backdrop-blur-md border-t border-border/30 pointer-events-auto">
              <div className="max-w-3xl mx-auto py-4">
                <form onSubmit={(e) => { e.preventDefault(); handleAsk(); }} className="flex gap-2 md:gap-3 relative">
                  <div className="flex-1 relative group">
                    <input
                      type="text"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      placeholder="Analyze your research notes..."
                      className="w-full pl-6 pr-14 py-4 md:py-5 bg-card backdrop-blur-xl rounded-2xl md:rounded-3xl border border-border focus:outline-none focus:ring-4 focus:ring-primary/10 transition-all duration-300 text-sm md:text-base font-medium placeholder:text-muted-foreground group-hover:shadow-primary/5"
                    />
                    <button
                      type="submit"
                      disabled={!input.trim() || loading}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-3 md:p-4 aspect-square bg-primary hover:bg-primary/90 disabled:opacity-45 disabled:pointer-events-none text-primary-foreground rounded-full transition-all hover:scale-105 active:scale-95 flex items-center justify-center group"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 md:h-6 md:w-6 group-hover:translate-x-0.5 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                      </svg>
                    </button>
                  </div>
                </form>

                {/* Copyright Footer */}
                <div className="mt-4 text-center">
                  <p className="text-[9px] md:text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground font-sans">
                    © 2026 NATARAJ EL. ALL RIGHTS RESERVED.
                  </p>
                </div>
              </div>
            </div>
          </footer>
        </div>

        {/* Hidden File Input */}
        <input
          type="file"
          id="file-upload"
          className="hidden"
          accept=".pdf"
          multiple
          onChange={async (e) => {
            if (e.target.files && e.target.files.length > 0) {
              const selectedFiles = Array.from(e.target.files);
              setFiles(selectedFiles);
              await handleUpload(selectedFiles);
            }
          }}
        />
      </main >
    </div>
  );
}
