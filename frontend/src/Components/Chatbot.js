import React, { useState, useRef, useEffect } from 'react';
import { Sparkles } from 'lucide-react';
import '../CSS/chat.css';
import { API, buildUrl } from '../config';
import { validateChatInput, ValidationError } from '../utils/validation';
import { logger } from '../utils/logger';
import { formatChatMarkdown } from '../utils/chatMarkdown';

const Chatbot = ({ setChatResults, graphData, searchResults }) => {
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

    const buildGraphContextSnapshot = () => {
        const summarizeNode = (node) => {
            const props = node?.properties && typeof node.properties === 'object' ? node.properties : {};
            return {
                elementId: node?.elementId || node?.id || props.elementId || props.id || '',
                name: node?.name || props.name || node?.title || props.title || node?.label || props.label || '',
                label: node?.label || node?.labels?.[0] || props.label || props.class_label || props.class_name || '',
                type: node?.entity_type || props.entity_type || props.type || props.original_type || '',
            };
        };

        const summarizeLink = (link) => ({
            type: link?.type || link?.label || '',
            source: typeof link?.source === 'object' ? (link.source.elementId || link.source.id || link.source.name || '') : (link?.source || ''),
            target: typeof link?.target === 'object' ? (link.target.elementId || link.target.id || link.target.name || '') : (link?.target || ''),
        });

        const normalizeGraph = (payload) => {
            if (!payload) return { nodes: [], links: [] };
            if (Array.isArray(payload)) {
                return { nodes: payload, links: [] };
            }
            return {
                nodes: Array.isArray(payload.nodes) ? payload.nodes : [],
                links: Array.isArray(payload.links) ? payload.links : payload.relationships || [],
            };
        };

        const visibleGraph = normalizeGraph(graphData);
        const searchGraph = normalizeGraph(searchResults);

        const graphSummary = (graph, name) => ({
            name,
            nodeCount: graph.nodes.length,
            linkCount: graph.links.length,
            nodes: graph.nodes.slice(0, 12).map(summarizeNode),
            links: graph.links.slice(0, 16).map(summarizeLink),
        });

        if (!visibleGraph.nodes.length && !visibleGraph.links.length && !searchGraph.nodes.length && !searchGraph.links.length) {
            return null;
        }

        const selectedNode = graphData?.selectedNode || graphData?.selected_node || graphData?.root || null;
        return {
            source: 'frontend-graph-context',
            capturedAt: new Date().toISOString(),
            selectedNode: selectedNode ? summarizeNode(selectedNode) : null,
            rootNode: graphData?.root ? summarizeNode(graphData.root) : null,
            viewMode: graphData?.view?.mode || graphData?.mode || '',
            ontology: graphData?.view?.ontology_prefix || graphData?.ontology_prefix || '',
            importId: graphData?.view?.import_id || graphData?.import_id || '',
            searchQuery: graphData?.view?.search || graphData?.search || '',
            visibleGraph: graphSummary(visibleGraph, 'visibleGraph'),
            searchResults: graphSummary(searchGraph, 'searchResults'),
        };
    };

    /* response formatting lives in utils/chatMarkdown.js */
    const parseMarkdown = formatChatMarkdown;
    /*
        if (!text) return '';

        const escapeHtml = (value) => String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
        const inline = (value) => escapeHtml(value)
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\*\*([^*]+)\*\* \/g, '<strong>$1</strong>')
            .replace(/\*([^*]+)\* \/g, '<em>$1</em>');
        const lines = String(text).replace(/\r\n/g, '\n').split('\n');
        let html = '';
        let paragraph = [];
        let listType = null;
        let listItems = [];
        let tableRows = [];

        const flushParagraph = () => {
            if (paragraph.length) {
                html += `<p class="chat-paragraph">${inline(paragraph.join(' '))}</p>`;
                paragraph = [];
            }
        };
        const flushList = () => {
            if (!listItems.length) return;
            html += `<${listType} class="chat-list">${listItems.map(item => `<li>${inline(item)}</li>`).join('')}</${listType}>`;
            listItems = [];
            listType = null;
        };
        const flushTable = () => {
            if (!tableRows.length) return;
            const rows = tableRows.filter(row => !/^\s*\|?\s*:?-{3,}/.test(row));
            if (rows.length) {
                const cells = rows.map(row => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim()));
                const header = cells[0];
                html += `<div class="chat-table-wrap"><table class="chat-table"><thead><tr>${header.map(cell => `<th>${inline(cell)}</th>`).join('')}</tr></thead><tbody>${cells.slice(1).map(row => `<tr>${row.map(cell => `<td>${inline(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
            }
            tableRows = [];
        };

        lines.forEach((rawLine) => {
            const line = rawLine.trim();
            if (!line) {
                flushParagraph(); flushList(); flushTable();
                return;
            }
            if (/^\|.*\|$/.test(line)) {
                flushParagraph(); flushList(); tableRows.push(line); return;
            }
            flushTable();
            const heading = line.match(/^(#{1,3})\s+(.+)$/);
            if (heading) {
                flushParagraph(); flushList();
                const level = heading[1].length;
                html += `<h${level} class="chat-heading chat-heading-${level}">${inline(heading[2])}</h${level}>`;
                return;
            }
            if (/^---+$/.test(line)) {
                flushParagraph(); flushList(); html += '<hr class="chat-rule" />'; return;
            }
            const bullet = line.match(/^[-*]\s+(.+)$/);
            const numbered = line.match(/^\d+[.)]\s+(.+)$/);
            if (bullet || numbered) {
                flushParagraph();
                const nextType = numbered ? 'ol' : 'ul';
                if (listType && listType !== nextType) flushList();
                listType = nextType;
                listItems.push((bullet || numbered)[1]);
                return;
            }
            const fact = line.match(/^([A-Za-z][A-Za-z0-9 _/-]{1,36}):\s+(.+)$/);
            if (fact && !line.includes('://')) {
                flushParagraph(); flushList();
                html += `<div class="chat-fact"><span>${inline(fact[1])}</span><strong>${inline(fact[2])}</strong></div>`;
                return;
            }
            paragraph.push(line);
        });
        flushParagraph(); flushList(); flushTable();

        return DOMPurify.sanitize(html, {
            ALLOWED_TAGS: ['p', 'strong', 'em', 'code', 'h1', 'h2', 'h3', 'ul', 'li', 'ol', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'div', 'span'],
            ALLOWED_ATTR: ['class'],
            KEEP_CONTENT: true,
        });
    }; */

    const [sampleQueries, setSampleQueries] = useState([
        'Show MBSE to EBOM traceability for the Variable Speed Drive',
        'Compare EBOM and MBOM for 5 HP MOTOR ASSEMBLY',
        'Show the bill of process for MOTOR COVER',
        'Show requirements linked to the Variable Speed Drive',
        'Analyse change impact if ROTOR SHAFT tolerance is modified',
    ]);

    // [OK] SECURE: Input validation + error handling
    const handleAsk = async (queryText = null) => {
        const messageText = queryText || question.trim();
        let controller = null;
        let assistantId = null;
        
        try {
            // [OK] Validate input against prompt injection
            const validated = validateChatInput(messageText);
            
            // Cancel any in-flight request and finalize its placeholder.
            if (abortRef.current) abortRef.current.abort();
            setChatMessages(prev => prev.map(item =>
                item.streaming ? { ...item, streaming: false } : item
            ));
            controller = new AbortController();
            abortRef.current = controller;

            const userMsg = { id: Date.now(), role: 'user', text: validated };
            assistantId = `asst-${Date.now()}`;
            const assistantMsg = { id: assistantId, role: 'assistant', text: '', streaming: true };

            setChatMessages(prev => [...prev, userMsg, assistantMsg]);
            setQuestion('');
            setShowSpinner(true);
            setError(null);
            setStatusLabel(null);

            let accumulated = '';
            let buffer = '';
            let streamCompleted = false;

            logger.data('Sending chat request:', validated);

            const response = await fetch(buildUrl(API.chat.chatStream), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionIdRef.current,
                    message: validated,
                    graph_context: buildGraphContextSnapshot(),
                }),
                signal: controller.signal,
            });

            if (!response.ok) throw new Error(`Server error ${response.status}`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            const processLine = (line) => {
                if (!/^data:\s?/.test(line)) return;
                const raw = line.slice(5).trim();
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
                        streamCompleted = true;
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, streaming: false } : m
                        ));
                        setStatusLabel(null);
                        setShowSpinner(false);
                        if (setChatResults) setChatResults([{ query: validated, response: accumulated, timestamp: new Date().toISOString() }]);
                    } else if (parsed.error) {
                        streamCompleted = true;
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
            buffer += decoder.decode();
            if (buffer.trim()) processLine(buffer.trim());
            if (!streamCompleted) {
                setChatMessages(prev => prev.map(item =>
                    item.id === assistantId ? { ...item, streaming: false } : item
                ));
                setStatusLabel(null);
                setShowSpinner(false);
                if (setChatResults) {
                    setChatResults([{ query: validated, response: accumulated, timestamp: new Date().toISOString() }]);
                }
            }

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
            
            setChatMessages(prev => prev.map(m =>
                m.id === assistantId
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
                    <Sparkles size={14} />
                    <span style={{ fontSize: 15, fontWeight: 700 }}>Knowledge Companion</span>
                    {chatMessages.length > 0 && (
                        <span style={{
                            background: 'rgba(255,255,255,0.2)', borderRadius: 10,
                            padding: '1px 8px', fontSize: 11, fontWeight: 600,
                        }}>{Math.ceil(chatMessages.length / 2)} turns</span>
                    )}
                </div>
                {chatMessages.length > 0 && (
                    <button
                        onClick={() => {
                            if (abortRef.current) abortRef.current.abort();
                            abortRef.current = null;
                            setChatMessages([]);
                            setStatusLabel(null);
                            setShowSpinner(false);
                            setError(null);
                        }}
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
                    <span style={{ animation: 'pulse 1.4s ease infinite', display: 'inline-block' }}>...</span>
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
                            <p style={{ fontSize: 12, color: '#888', marginBottom: 12 }}>
                                Ask a question or start from a sample prompt.
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

// Memoize while still allowing graph context updates to flow into chat prompts
export default React.memo(
    Chatbot,
    (prevProps, nextProps) =>
        prevProps.setChatResults === nextProps.setChatResults &&
        prevProps.graphData === nextProps.graphData &&
        prevProps.searchResults === nextProps.searchResults
);
