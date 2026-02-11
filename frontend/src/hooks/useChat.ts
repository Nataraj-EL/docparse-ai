import { useState, useCallback } from 'react';
import { askQuestion, uploadPdf, ApiResponse } from '@/lib/api';

interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date;
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addMessage = useCallback((content: string, role: 'user' | 'assistant' = 'user') => {
    const newMessage: Message = {
      id: Date.now().toString(),
      content,
      role,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, newMessage]);
    return newMessage;
  }, []);

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim()) return;
    
    setIsLoading(true);
    setError(null);
    
    // Add user message
    addMessage(content, 'user');
    
    try {
      const response = await askQuestion(content);
      
      if (response.error) {
        throw new Error(response.error);
      }
      
      if (response.data?.answer) {
        addMessage(response.data.answer, 'assistant');
      }
    } catch (err) {
      console.error('Error sending message:', err);
      setError(err instanceof Error ? err.message : 'Failed to send message');
    } finally {
      setIsLoading(false);
    }
  }, [addMessage]);

  const handleFileUpload = useCallback(async (file: File) => {
    if (!file) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await uploadPdf(file);
      
      if (response.error) {
        throw new Error(response.error);
      }
      
      return response.data;
    } catch (err) {
      console.error('Error uploading file:', err);
      setError(err instanceof Error ? err.message : 'Failed to upload file');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    messages,
    isLoading,
    error,
    sendMessage,
    handleFileUpload,
    clearError: () => setError(null),
  };
}
