import React, { useState, useRef, useEffect } from 'react';
import DOMPurify from 'dompurify';
import '../CSS/chat.css';
import { API, buildUrl } from '../config';
import { validateChatInput, ValidationError } from '../utils/validation';
import { logger } from '../utils/logger';

const Chatbot = ({ setChatResults }) => {
    const [chatMessages, setChatMessages] = useState([]);
    const [question, setQuestion] = useState('');
    const [showSpinner, setShowSpinner] = useState(false);
    const [error, setError] = useState(null);
    const [statusLabel, setStatusLabel] = useState(null);
    const abortRef = useRef(null);
    const sessionIdRef = useRef(
        typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
            ? crypto.randomUUID()
            : Math.random().toString(36).slice(2) + Date.now().toString(36)
    );
    const assistantIdRef = useRef(null);

    // [OK] SECURE: Markdown parser with DOMPurify sanitization
    const parseMarkdown = (text) => {
        if (!text) return text;
        
        let html = text
            // Headers
            .replace(/^### (.*$)/gim, '<h3 style="color:#004B87;font-size:1.05em;margin:8px 0 4px 0;font-weight:bold;">$1</h3>')
            .replace(/^## (.*$)/gim, '<h2 style="color:#004B87;font-size:1.15em;margin:10px 0 6px 0;font-weight:bold;">$1</h2>')
            .replace(/^# (.*$)/gim, '<h1 style="color:#004B87;font-size:1.3em;margin:12px 0 8px 0;font-weight:bold;">$1</h1>')
            
            // Bold text
            .replace(/\*\*(.*?)\*\*/g, '<strong style="font-weight:bold;">$1</strong>')
            
            // Italic text
            .replace(/\*(.*?)\*/g, '<em style="font-style:italic;">$1</em>')
            
            // Inline code
            .replace(/`(.*?)`/g, '<code style="background-color:rgba(0,75,135,0.08);padding:2px 5px;border-radius:4px;font-family:monospace;font-size:0.9em;color:#004B87;">$1</code>')
            
            // Horizontal rules
            .replace(/^---$/gim, '<hr style="border:none;border-top:1px solid #dde3ea;margin:12px 0;" />')
            
            // Line breaks
            .replace(/\n\n/g, '</p><p style="margin:6px 0;line-height:1.6;">')
            
            // LaTeX-style math (safe)
            .replace(/\\\((.*?)\\\)/g, '<span style="font-style:italic;">$1</span>')
            .replace(/\\\[(.*?)\\\]/g, '<div style="text-align:center;margin:10px 0;font-style:italic;">$1</div>')
            
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

        // Wrap consecutive list items in a single <ul>
        html = html.replace(/((<li[^>]*>.*?<\/li>\s*)+)/gs, (match) => {
            return '<ul style="margin:6px 0;padding-left:20px;line-height:1.5;">' + match + '</ul>';
        });

        // [OK] SANITIZE OUTPUT with DOMPurify before rendering
        return DOMPurify.sanitize(html, {
            ALLOWED_TAGS: ['p', 'strong', 'em', 'code', 'h1', 'h2', 'h3', 'ul', 'li', 'ol', 'pre', 'hr', 'sub', 'sup', 'div', 'span'],
            ALLOWED_ATTR: ['style'],
            KEEP_CONTENT: true,
        });
    };

    const [sampleQueries, setSampleQueries] = useState([
        'What are all the parts in the 5 HP MOTOR ASSEMBLY and in what sequence are they assembled?',
        'Show the complete assembly operation sequence for 5 HP MOTOR ASSEMBLY',
        'Recommend manufacturing processes for ROTOR SHAFT',
        'Find parts similar to LAMINATED ROTOR CORE that could be substituted',
        'What SysML requirements relate to the Variable Speed Drive?',
        'Show all use cases and actors in the Sugar Production Plant MBSE model',
        'Analyse change impact if ROTOR SHAFT is modified',
        'Analyse change impact if THREE PHASE WINDINGS is modified',
    ]);

    // [OK] SECURE: Input validation + error handling
    const handleAsk = async (queryText = null) => {
        const messageText = queryText || question.trim();
        
        try {
            // [OK] Validate input against prompt injection
            const validated = validateChatInput(messageText);
            
            // Cancel any in-flight request
            if (abortRef.current) abortRef.current.abort();
            const controller = new AbortController();
            abortRef.current = controller;

            const userMsg = { id: Date.now(), role: 'user', text: validated };
            const assistantId = `asst-${Date.now()}`;
            assistantIdRef.current = assistantId;
            const assistantMsg = { id: assistantId, role: 'assistant', text: '', streaming: true };

            setChatMessages(prev => [...prev, userMsg, assistantMsg]);
            setQuestion('');
            setShowSpinner(true);
            setError(null);
            setStatusLabel(null);

            let accumulated = '';
            let buffer = '';

            logger.data('Sending chat request:', validated);

            const response = await fetch(buildUrl(API.chat.chatStream), {
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
                        setStatusLabel(null);
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, text: accumulated } : m
                        ));
                    } else if (parsed.status) {
                        setStatusLabel(parsed.status);
                    } else if (parsed.done) {
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, streaming: false } : m
                        ));
                        setStatusLabel(null);
                        setShowSpinner(false);
                        if (setChatResults) setChatResults([{ query: validated, response: accumulated, timestamp: new Date().toISOString() }]);
                    } else if (parsed.error) {
                        const errMsg = typeof parsed.error === 'string' ? parsed.error : 'An error occurred.';
                        setError(errMsg);
                        setStatusLabel(null);
                        setShowSpinner(false);
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, text: errMsg, streaming: false } : m
                        ));
                    }
                } catch (_e) { /* skip malformed SSE lines */ }
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
            setStatusLabel(null);
            setError('Error: ' + (err.message || 'Unknown error occurred'));
            
            const failId = assistantIdRef.current;
            setChatMessages(prev => prev.map(m =>
                m.id === failId
                    ? { ...m, text: 'Sorry, I encountered an error. Please try again.', streaming: false, statusLabel: null }
                    : m
            ));
        }
    };

    const handleSampleQueryClick = (query) => {
        handleAsk(query);
    };

    // [OK] CLEANUP: Abort requests on unmount
    useEffect(() => {
        // Fetch dynamic sample queries from backend
        const fetchSampleQueries = async () => {
            try {
                const response = await fetch(buildUrl(API.chat.sampleQueries), {
                    method: 'GET',
                    headers: { 'Content-Type': 'application/json' },
                });
                if (response.ok) {
                    const data = await response.json();
                    if (data.queries && data.queries.length > 0) {
                        setSampleQueries(data.queries);
                        logger.data('Loaded dynamic sample queries', {
                            count: data.queries.length,
                            data_available: data.data_available,
                            entities: data.sample_entities
                        });
                    }
                }
            } catch (err) {
                logger.warn('Could not fetch dynamic queries, using defaults:', err.message);
                // Keep default queries on error
            }
        };
        
        fetchSampleQueries();
        
        // Cleanup: Abort requests on unmount
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
            {/* Chat header */}
            <div style={{
                background: 'linear-gradient(135deg,#004B87 0%,#1a6fb5 100%)',
                color: '#fff', padding: '8px 14px',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                flexShrink: 0,
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 15, fontWeight: 700 }}>[AI] Knowledge Assistant</span>
                    {chatMessages.length > 0 && (
                        <span style={{
                            background: 'rgba(255,255,255,0.2)', borderRadius: 10,
                            padding: '1px 8px', fontSize: 11, fontWeight: 600,
                        }}>{Math.ceil(chatMessages.length / 2)} turns</span>
                    )}
                </div>
                {chatMessages.length > 0 && (
                    <button
                        onClick={() => { setChatMessages([]); setStatusLabel(null); setError(null); }}
                        title="Clear conversation"
                        style={{
                            background: 'rgba(255,255,255,0.15)', color: '#fff',
                            border: '1px solid rgba(255,255,255,0.3)', borderRadius: 5,
                            padding: '2px 10px', fontSize: 11, cursor: 'pointer',
                        }}
                    >Clear</button>
                )}
            </div>

            {/* Status bar — shown while a tool is executing */}
            {statusLabel && (
                <div style={{
                    background: '#eaf2fb', color: '#004B87',
                    borderBottom: '1px solid #c2d9f0',
                    padding: '5px 14px', fontSize: 12, fontWeight: 600,
                    display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
                }}>
                    <span style={{ animation: 'pulse 1.4s ease infinite', display: 'inline-block' }}>[*]</span>
                    {statusLabel}
                </div>
            )}

            {/* Chat body */}
            <div style={{ flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column', backgroundColor: 'white' }}>
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
                            <p style={{ margin: '0 0 12px', fontWeight: 600, color: '#004B87' }}>
                                Motor Assembly · SysML MBSE · Process Planning · Change Impact
                            </p>
                            <p style={{ fontSize: 12, color: '#888', marginBottom: 12 }}>
                                Select a query below or type your own question.
                            </p>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, textAlign: 'left' }}>
                                {sampleQueries.map((query, idx) => (
                                    <button key={idx} onClick={() => handleSampleQueryClick(query)}
                                        style={{
                                            padding: '7px 10px',
                                            backgroundColor: '#e8f0fe',
                                            border: '1px solid #c2d9f0',
                                            borderRadius: 6,
                                            color: '#004B87',
                                            cursor: 'pointer',
                                            fontSize: 11,
                                            fontWeight: 500,
                                            textAlign: 'left',
                                            lineHeight: '1.35',
                                        }}
                                    >{query}</button>
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
                                        color: msg.role === 'user' ? '#fff' : '#1a1a1a',
                                        border: msg.role === 'assistant' ? '1px solid #e2e6ea' : 'none',
                                        boxShadow: msg.role === 'assistant' ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
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
                                    {msg.streaming && showSpinner && (
                                        <span style={{ display: 'inline-block', marginLeft: 6, fontSize: 10, color: '#888' }}>●●●</span>
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
                        borderTop: '1px solid #ffcdd2',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                        <span>{error}</span>
                        <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', color: '#c62828', cursor: 'pointer', fontSize: 14, padding: 0 }}>✕</button>
                    </div>
                )}

                {/* Input Area */}
                <div style={{
                    padding: '6px 8px',
                    borderTop: '1px solid #ddd',
                    display: 'flex',
                    gap: '6px',
                    background: '#fff',
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
                        placeholder='Ask about parts, traceability, CAD structure, change impact…'
                        style={{
                            flex: 1,
                            padding: '7px 10px',
                            border: '1px solid #ddd',
                            borderRadius: '6px',
                            fontSize: '12px',
                            fontFamily: 'inherit'
                        }}
                        disabled={showSpinner}
                    />
                    <button
                        onClick={() => handleAsk()}
                        disabled={showSpinner || !question.trim()}
                        style={{
                            padding: '7px 16px',
                            backgroundColor: showSpinner || !question.trim() ? '#ccc' : '#004B87',
                            color: 'white',
                            border: 'none',
                            borderRadius: '6px',
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
export default React.memo(Chatbot, (prevProps, nextProps) => prevProps.setChatResults === nextProps.setChatResults);
