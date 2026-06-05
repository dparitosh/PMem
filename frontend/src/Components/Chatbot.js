import React, { useState, useRef, useEffect } from 'react';
import DOMPurify from 'dompurify';
import '../CSS/chat.css';
import config from '../config';
import { validateChatInput, ValidationError } from '../utils/validation';
import { logger } from '../utils/logger';

const API_BASE = config.apiUrl;

const Chatbot = ({ setChatResults }) => {
    const [chatMessages, setChatMessages] = useState([]);
    const [question, setQuestion] = useState('');
    const [showSpinner, setShowSpinner] = useState(false);
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [error, setError] = useState(null);
    const abortRef = useRef(null);
    const sessionIdRef = useRef(crypto.randomUUID());

    // ✅ SECURE: Markdown parser with DOMPurify sanitization
    const parseMarkdown = (text) => {
        if (!text) return text;
        
        let html = text
            // Headers
            .replace(/^### (.*$)/gim, '<h3 style="color: white; font-size: 1.1em; margin: 8px 0 4px 0; font-weight: bold;">$1</h3>')
            .replace(/^## (.*$)/gim, '<h2 style="color: white; font-size: 1.2em; margin: 10px 0 6px 0; font-weight: bold;">$1</h2>')
            .replace(/^# (.*$)/gim, '<h1 style="color: white; font-size: 1.4em; margin: 12px 0 8px 0; font-weight: bold;">$1</h1>')
            
            // Bold text
            .replace(/\*\*(.*?)\*\*/g, '<strong style="font-weight: bold; color: white;">$1</strong>')
            
            // Italic text
            .replace(/\*(.*?)\*/g, '<em style="font-style: italic; color: white;">$1</em>')
            
            // Inline code
            .replace(/`(.*?)`/g, '<code style="background-color: rgba(255,255,255,0.2); padding: 2px 4px; border-radius: 4px; font-family: monospace; font-size: 0.9em;">$1</code>')
            
            // Horizontal rules
            .replace(/^---$/gim, '<hr style="border: none; border-top: 1px solid rgba(255,255,255,0.3); margin: 16px 0;" />')
            
            // Line breaks
            .replace(/\n\n/g, '</p><p style="margin: 8px 0; line-height: 1.6;">')
            
            // LaTeX-style math (safe)
            .replace(/\\\((.*?)\\\)/g, '<span style="font-style: italic; color: white;">$1</span>')
            .replace(/\\\[(.*?)\\\]/g, '<div style="text-align: center; margin: 12px 0; font-style: italic; color: white;">$1</div>')
            
            // Subscripts and superscripts
            .replace(/([A-Za-z0-9])_{([^}]+)}/g, '$1<sub style="font-size: 0.8em;">$2</sub>')
            .replace(/([A-Za-z0-9])\^{([^}]+)}/g, '$1<sup style="font-size: 0.8em;">$2</sup>')
            .replace(/([A-Za-z])_{([0-9]+)}/g, '$1<sub style="font-size: 0.8em;">$2</sub>')
            .replace(/([A-Za-z])\^{([0-9]+)}/g, '$1<sup style="font-size: 0.8em;">$2</sup>')
            
            // List items
            .replace(/^- (.*$)/gim, '<li style="margin: 4px 0;">$1</li>')
            .replace(/^(\d+)\. (.*$)/gim, '<li style="margin: 4px 0;">$2</li>');

        // Wrap content in paragraphs
        if (!html.startsWith('<')) {
            html = '<p style="margin: 8px 0; line-height: 1.6;">' + html + '</p>';
        }

        // Wrap list items
        html = html.replace(/(<li[^>]*>.*<\/li>)/gs, (match) => {
            return '<ul style="margin: 8px 0; padding-left: 20px; line-height: 1.5;">' + match + '</ul>';
        });

        // ✅ SANITIZE OUTPUT with DOMPurify before rendering
        return DOMPurify.sanitize(html, {
            ALLOWED_TAGS: ['p', 'strong', 'em', 'code', 'h1', 'h2', 'h3', 'ul', 'li', 'ol', 'pre', 'hr', 'sub', 'sup', 'div', 'span'],
            ALLOWED_ATTR: ['style'],
            KEEP_CONTENT: true,
        });
    };

    const sampleQueries = [
        'Show where "Node123" is used',
        'Show the structure of "Project Alpha"',
        'List all connected nodes',
        'Show relationships for "Entity X"',
        'Find all nodes of type "Document"',
        'Show hierarchy for "Component Y"',
        'List nodes with status "Active"',
        'What are the entities owned by user "john.doe"'
    ];

    // ✅ SECURE: Input validation + error handling
    const handleAsk = async (queryText = null) => {
        const messageText = queryText || question.trim();
        
        try {
            // ✅ Validate input against prompt injection
            const validated = validateChatInput(messageText);
            
            // Cancel any in-flight request
            if (abortRef.current) abortRef.current.abort();
            const controller = new AbortController();
            abortRef.current = controller;

            const userMsg = { id: Date.now(), role: 'user', text: validated };
            const assistantId = Date.now() + 1;
            const assistantMsg = { id: assistantId, role: 'assistant', text: '', streaming: true };

            setChatMessages(prev => [...prev, userMsg, assistantMsg]);
            setQuestion('');
            setShowSpinner(true);
            setError(null);

            let accumulated = '';
            let buffer = '';

            logger.data('Sending chat request:', validated);

            const response = await fetch(`${API_BASE}/chat-stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionIdRef.current, message: validated }),
                signal: controller.signal,
            });

            if (!response.ok) throw new Error(`Server error ${response.status}`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            const processLine = (line) => {
                if (!line.startsWith('data: ')) return;
                const raw = line.slice(6).trim();
                if (!raw) return;
                try {
                    const parsed = JSON.parse(raw);
                    if (parsed.token) {
                        accumulated += parsed.token;
                        setShowSpinner(false);
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, text: accumulated } : m
                        ));
                    } else if (parsed.status) {
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, statusLabel: parsed.status } : m
                        ));
                    } else if (parsed.done) {
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, streaming: false, statusLabel: null } : m
                        ));
                        setShowSpinner(false);
                        if (setChatResults) {
                            setChatResults([{
                                query: validated,
                                response: accumulated,
                                timestamp: new Date().toISOString(),
                            }]);
                        }
                    } else if (parsed.error) {
                        throw new Error(parsed.error);
                    }
                } catch (_) { /* skip malformed lines */ }
            };

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                for (const line of lines) processLine(line.trim());
            }
            if (buffer.trim()) processLine(buffer.trim());

        } catch (err) {
            if (err.name === 'AbortError') return;
            
            if (err instanceof ValidationError) {
                setError(err.message);
                logger.warn('Input validation failed:', err.message);
                return;
            }

            logger.error('Chat stream error:', err);
            setShowSpinner(false);
            setError('Error: ' + (err.message || 'Unknown error occurred'));
            
            setChatMessages(prev => prev.map(m =>
                m.id === (Date.now() + 1)
                    ? { ...m, text: 'Sorry, I encountered an error. Please try again.', streaming: false, statusLabel: null }
                    : m
            ));
        }
    };

    const handleSampleQueryClick = (query) => {
        handleAsk(query);
    };

    // ✅ CLEANUP: Abort requests on unmount
    useEffect(() => {
        return () => {
            if (abortRef.current) {
                abortRef.current.abort();
            }
        };
    }, []);

    return (
        <div style={{ 
            height: '100%',
            position: 'relative',
            display: 'flex',
            flexDirection: 'column',
            minWidth: '0',
            backgroundColor: 'white',
            overflow: 'hidden'
        }}>
            {/* Chatbot Header */}
            <div 
                style={{ 
                    backgroundColor: '#6C757D', 
                    color: 'white', 
                    padding: '6px 10px', 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    alignItems: 'center',
                    cursor: 'pointer',
                    userSelect: 'none',
                    transition: 'background-color 0.2s ease'
                }}
                onClick={() => setIsCollapsed(!isCollapsed)}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#495057'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#6C757D'}
                title={isCollapsed ? 'Click to expand chat' : 'Click to collapse chat'}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 'bold', fontSize: '16px' }}>Chat Assistant</span>
                    {isCollapsed && chatMessages.length > 0 && (
                        <span style={{ 
                            backgroundColor: 'rgba(255,255,255,0.2)', 
                            borderRadius: '12px', 
                            padding: '2px 8px', 
                            fontSize: '12px',
                            fontWeight: 'bold'
                        }}>
                            {chatMessages.length}
                        </span>
                    )}
                </div>
            </div>
            
            {/* Collapsible Chat Container */}
            <div 
                style={{ 
                    overflow: 'hidden', 
                    flex: isCollapsed ? '0 0 0px' : '1 1 auto',
                    display: 'flex',
                    flexDirection: 'column',
                    transition: 'flex 0.3s ease, opacity 0.3s ease',
                    opacity: isCollapsed ? 0 : 1,
                    backgroundColor: 'white',
                    minHeight: 0
                }}
            >
                {/* Messages Container */}
                <div className='chat-messages' style={{
                    flex: 1,
                    overflowY: 'auto',
                    padding: '4px 6px',
                    backgroundColor: '#f8f9fa',
                    minHeight: 0
                }}>
                    {chatMessages.length === 0 ? (
                        <div style={{
                            textAlign: 'center',
                            color: '#6c757d',
                            paddingTop: '20px',
                            fontSize: '13px'
                        }}>
                            <p>Start a conversation by selecting a sample query or typing your own.</p>
                            <div style={{ marginTop: '12px' }}>
                                {sampleQueries.slice(0, 3).map((query, idx) => (
                                    <button
                                        key={idx}
                                        onClick={() => handleSampleQueryClick(query)}
                                        style={{
                                            display: 'block',
                                            width: '100%',
                                            padding: '8px',
                                            marginBottom: '6px',
                                            backgroundColor: '#e8f0fe',
                                            border: '1px solid #d0d9ed',
                                            borderRadius: '4px',
                                            color: '#004B87',
                                            cursor: 'pointer',
                                            fontSize: '12px',
                                            fontWeight: 500,
                                            textAlign: 'left'
                                        }}
                                    >
                                        {query}
                                    </button>
                                ))}
                            </div>
                        </div>
                    ) : (
                        chatMessages.map(msg => (
                            <div
                                key={msg.id}
                                style={{
                                    marginBottom: '4px',
                                    display: 'flex',
                                    justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start'
                                }}
                            >
                                <div
                                    style={{
                                        maxWidth: '90%',
                                        padding: '6px 8px',
                                        borderRadius: '6px',
                                        backgroundColor: msg.role === 'user' ? '#004B87' : '#e8e8e8',
                                        color: msg.role === 'user' ? 'white' : 'black',
                                        fontSize: '12px',
                                        lineHeight: '1.4',
                                        wordWrap: 'break-word'
                                    }}
                                >
                                    {msg.role === 'assistant' ? (
                                        <div dangerouslySetInnerHTML={{ __html: parseMarkdown(msg.text) }} />
                                    ) : (
                                        msg.text
                                    )}
                                    {msg.streaming && showSpinner && <span style={{ marginLeft: '8px' }}>⏳</span>}
                                    {msg.statusLabel && (
                                        <div style={{ fontSize: '11px', marginTop: '4px', opacity: 0.7 }}>
                                            {msg.statusLabel}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))
                    )}
                </div>

                {/* Error Display */}
                {error && (
                    <div style={{
                        backgroundColor: '#ffebee',
                        color: '#c62828',
                        padding: '8px 12px',
                        fontSize: '12px',
                        borderTop: '1px solid #ffcdd2'
                    }}>
                        {error}
                    </div>
                )}

                {/* Input Area */}
                <div style={{
                    padding: '4px 6px',
                    borderTop: '1px solid #ddd',
                    display: 'flex',
                    gap: '4px'
                }}>
                    <input
                        type='text'
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleAsk();
                            }
                        }}
                        placeholder='Ask a question...'
                        style={{
                            flex: 1,
                            padding: '4px 6px',
                            border: '1px solid #ddd',
                            borderRadius: '3px',
                            fontSize: '12px',
                            fontFamily: 'inherit'
                        }}
                        disabled={showSpinner}
                    />
                    <button
                        onClick={() => handleAsk()}
                        disabled={showSpinner || !question.trim()}
                        style={{
                            padding: '4px 10px',
                            backgroundColor: showSpinner || !question.trim() ? '#ccc' : '#004B87',
                            color: 'white',
                            border: 'none',
                            borderRadius: '3px',
                            cursor: showSpinner || !question.trim() ? 'not-allowed' : 'pointer',
                            fontSize: '12px',
                            fontWeight: 600
                        }}
                    >
                        {showSpinner ? 'Sending...' : 'Send'}
                    </button>
                </div>
            </div>
        </div>
    );
};

// 🔒 MEDIUM PRIORITY: Memoize component to prevent unnecessary re-renders
export default React.memo(Chatbot, (prevProps, nextProps) => {
  return (
    prevProps.setChatResults === nextProps.setChatResults &&
    prevProps.selectedNode === nextProps.selectedNode &&
    prevProps.graphData === nextProps.graphData
  );
});
