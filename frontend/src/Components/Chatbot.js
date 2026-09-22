import React, { useState, useRef, useEffect } from 'react';
import { Sparkles } from 'lucide-react';
import { IxChatInput } from '@siemens/ix-react';
import '../CSS/chat.css';
import { API, buildUrl, config } from '../config';
import { validateChatInput, ValidationError } from '../utils/validation';
import { logger } from '../utils/logger';
import { formatChatMarkdown } from '../utils/chatMarkdown';
import { clearClientSessionId, getClientSessionId, setClientSessionId } from '../services/apiClient';

const CHAT_COLORS = {
    primary: '#005a9c',
    primarySoft: '#e8f1fc',
    primaryBorder: '#c2d9f0',
    surfaceMuted: '#f8fafc',
    assistantBubble: '#eef2f6',
    danger: '#c62828',
    dangerSoft: '#ffebee',
    dangerBorder: '#ffcdd2',
    textMuted: '#66788a',
};

const Chatbot = ({ setChatResults, graphData, searchResults }) => {
    const [chatMessages, setChatMessages] = useState([]);
    const [question, setQuestion] = useState('');
    const [accessToken, setAccessToken] = useState('');
    const [showSpinner, setShowSpinner] = useState(false);
    const [requestActive, setRequestActive] = useState(false);
    const [error, setError] = useState(null);
    const [statusLabel, setStatusLabel] = useState(null);
    const abortRef = useRef(null);
    const requestActiveRef = useRef(false);
    const messageSequenceRef = useRef(0);
    const messagesEndRef = useRef(null);
    const sessionIdRef = useRef(getClientSessionId());

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
        if (requestActiveRef.current) return;
        let controller = null;
        let assistantId = null;
        let timeoutId = null;
        let timedOut = false;
        
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
            requestActiveRef.current = true;
            setRequestActive(true);
            const timeoutMs = Number(config.chatStreamTimeout) || 900000;
            timeoutId = window.setTimeout(() => {
                timedOut = true;
                controller.abort();
            }, timeoutMs);

            const messageSequence = ++messageSequenceRef.current;
            const userMsg = { id: `user-${messageSequence}`, role: 'user', text: validated };
            assistantId = `asst-${messageSequence}`;
            const assistantMsg = { id: assistantId, role: 'assistant', text: '', streaming: true };

            setChatMessages(prev => [...prev, userMsg, assistantMsg]);
            setQuestion('');
            setShowSpinner(true);
            setError(null);
            setStatusLabel(null);

            let accumulated = '';
            let buffer = '';
            let streamCompleted = false;
            let streamFailed = false;
            let responseEvidence = [];
            let responseSources = [];
            let responseAnswerable = null;

            logger.data('Sending chat request:', validated);

            let activeSessionId = getClientSessionId() || sessionIdRef.current;
            sessionIdRef.current = activeSessionId;
            const graphContext = buildGraphContextSnapshot();
            const sendRequest = (sessionId) => fetch(buildUrl(API.chat.chatStream), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(accessToken.trim() ? { Authorization: `Bearer ${accessToken.trim()}` } : {}),
                    ...(sessionId ? { 'X-Session-ID': sessionId } : {}),
                },
                body: JSON.stringify({ session_id: sessionId, message: validated, graph_context: graphContext }),
                signal: controller.signal,
            });

            let response = await sendRequest(activeSessionId);
            let returnedSessionId = response.headers.get('x-session-id');
            if (returnedSessionId) {
                sessionIdRef.current = returnedSessionId;
                setClientSessionId(returnedSessionId);
            }
            if (response.status === 403 && returnedSessionId && returnedSessionId !== activeSessionId) {
                activeSessionId = returnedSessionId;
                response = await sendRequest(activeSessionId);
                returnedSessionId = response.headers.get('x-session-id');
                if (returnedSessionId) {
                    sessionIdRef.current = returnedSessionId;
                    setClientSessionId(returnedSessionId);
                }
            }
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload?.detail || `Server error ${response.status}`);
            }

            if (!response.body) throw new Error('The server returned an empty chat stream.');
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
                    } else if (Array.isArray(parsed.evidence)) {
                        responseEvidence = parsed.evidence;
                        responseSources = Array.isArray(parsed.sources) ? parsed.sources : [];
                        responseAnswerable = parsed.answerable;
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, evidence: responseEvidence, sources: responseSources, answerable: responseAnswerable } : m
                        ));
                    } else if (parsed.status) {
                        setStatusLabel(parsed.status);
                    } else if (parsed.done) {
                        streamCompleted = true;
                        if (!accumulated && !streamFailed) {
                            streamFailed = true;
                            const emptyMessage = 'The AI completed without returning an answer. Please try again.';
                            setError(emptyMessage);
                            setChatMessages(prev => prev.map(m =>
                                m.id === assistantId ? { ...m, text: emptyMessage, streaming: false } : m
                            ));
                        }
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, streaming: false } : m
                        ));
                        setStatusLabel(null);
                        setShowSpinner(false);
                        if (!streamFailed && setChatResults) setChatResults([{ query: validated, response: accumulated, evidence: responseEvidence, sources: responseSources, answerable: responseAnswerable, timestamp: new Date().toISOString() }]);
                    } else if (parsed.error) {
                        streamCompleted = true;
                        streamFailed = true;
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
            if (!streamCompleted && accumulated) {
                setChatMessages(prev => prev.map(item =>
                    item.id === assistantId ? { ...item, streaming: false } : item
                ));
                setStatusLabel(null);
                setShowSpinner(false);
                if (setChatResults) {
                    setChatResults([{ query: validated, response: accumulated, evidence: responseEvidence, sources: responseSources, answerable: responseAnswerable, timestamp: new Date().toISOString() }]);
                }
            } else if (!streamCompleted) {
                throw new Error('The chat stream ended without a response.');
            }

        } catch (err) {
            if (err.name === 'AbortError') {
                if (timedOut) {
                    const timeoutMessage = 'Chat request timed out. Please try again.';
                    setError(timeoutMessage);
                    setStatusLabel(null);
                    setShowSpinner(false);
                    setChatMessages(prev => prev.map(m =>
                        m.id === assistantId ? { ...m, text: timeoutMessage, streaming: false } : m
                    ));
                }
                return;
            }
            
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
        } finally {
            if (timeoutId) window.clearTimeout(timeoutId);
            if (abortRef.current === controller) {
                abortRef.current = null;
                requestActiveRef.current = false;
                setRequestActive(false);
                setShowSpinner(false);
                setStatusLabel(null);
            }
        }
    };

    const handleSampleQueryClick = (query) => {
        handleAsk(query);
    };

    // [OK] CLEANUP: Abort requests on unmount
    useEffect(() => {
        // Fetch dynamic sample queries from backend
        const sampleController = new AbortController();
        const fetchSampleQueries = async () => {
            try {
                const activeSessionId = getClientSessionId() || sessionIdRef.current;
                sessionIdRef.current = activeSessionId;
                const response = await fetch(buildUrl(API.chat.sampleQueries), {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        ...(activeSessionId ? { 'X-Session-ID': activeSessionId } : {}),
                    },
                    signal: sampleController.signal,
                });
                const returnedSessionId = response.headers.get('x-session-id');
                if (returnedSessionId) {
                    sessionIdRef.current = returnedSessionId;
                    setClientSessionId(returnedSessionId);
                }
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
                if (sampleController.signal.aborted || err?.name === 'AbortError') return;
                logger.warn('Could not fetch dynamic queries, using defaults:', err.message);
                // Keep default queries on error
            }
        };
        
        fetchSampleQueries();
        
        // Cleanup: Abort requests on unmount
        return () => {
            sampleController.abort();
            if (abortRef.current) {
                abortRef.current.abort();
            }
        };
    }, []);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView?.({ block: 'end' });
    }, [chatMessages, statusLabel]);

    return (
        <div style={{ 
            height: '100%',
            width: '100%',
            boxSizing: 'border-box',
            position: 'relative',
            display: 'flex',
            flexDirection: 'column',
            minWidth: '0',
            backgroundColor: 'white',
            overflow: 'hidden'
        }}>
            <details style={{ padding: '8px 14px', flexShrink: 0 }}>
                <summary>Connection credentials</summary>
                <label>API key <input aria-label="Chat API key" type="password" autoComplete="off"
                    value={accessToken} onChange={event => setAccessToken(event.target.value)} /></label>
                <small style={{ display: 'block' }}>Enter your graph read API key. Kept only in memory.</small>
            </details>
            {/* Compact session utility row; the surrounding IX card owns the panel title. */}
            <div style={{
                background: 'var(--theme-color-std-background, #f4f6f8)',
                color: 'var(--theme-color-std-text, #252a2e)', padding: '8px 14px',
                borderBottom: '1px solid var(--theme-color-weak-bdr, #d9e2ec)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                flexShrink: 0,
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Sparkles size={14} />
                    <span style={{ fontSize: 13, fontWeight: 600 }}>Evidence-grounded engineering queries</span>
                    {chatMessages.length > 0 && (
                        <span style={{
                            background: 'rgba(255,255,255,0.2)', borderRadius: 10,
                            padding: '1px 8px', fontSize: 11, fontWeight: 600,
                        }}>{Math.ceil(chatMessages.length / 2)} turns</span>
                    )}
                </div>
                {chatMessages.length > 0 && (
                    <button
                        type="button"
                        onClick={() => {
                            if (abortRef.current) abortRef.current.abort();
                            abortRef.current = null;
                            requestActiveRef.current = false;
                            clearClientSessionId();
                            sessionIdRef.current = null;
                            setChatMessages([]);
                            if (setChatResults) setChatResults([]);
                            setStatusLabel(null);
                            setShowSpinner(false);
                            setRequestActive(false);
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

            {/* Status bar â€” shown while a tool is executing */}
            {statusLabel && (
                <div style={{
                    background: CHAT_COLORS.primarySoft, color: CHAT_COLORS.primary,
                    borderBottom: `1px solid ${CHAT_COLORS.primaryBorder}`,
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
                    backgroundColor: CHAT_COLORS.surfaceMuted,
                    minHeight: 0
                }}>
                    {chatMessages.length === 0 ? (
                        <div style={{
                            textAlign: 'center',
                            color: CHAT_COLORS.textMuted,
                            paddingTop: '20px',
                            fontSize: '13px'
                        }}>
                            <p style={{ fontSize: 12, color: '#888', marginBottom: 12 }}>
                                Ask a question or start from a sample prompt.
                            </p>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, textAlign: 'left' }}>
                                {sampleQueries.map((query, idx) => (
                                    <button key={idx} type="button" onClick={() => handleSampleQueryClick(query)}
                                        style={{
                                            padding: '7px 10px',
                                            backgroundColor: CHAT_COLORS.primarySoft,
                                            border: `1px solid ${CHAT_COLORS.primaryBorder}`,
                                            borderRadius: 6,
                                            color: CHAT_COLORS.primary,
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
                                        backgroundColor: msg.role === 'user' ? CHAT_COLORS.primary : CHAT_COLORS.assistantBubble,
                                        color: msg.role === 'user' ? '#fff' : '#1a1a1a',
                                        border: msg.role === 'assistant' ? '1px solid #e2e6ea' : 'none',
                                        boxShadow: msg.role === 'assistant' ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
                                        fontSize: '12px',
                                        lineHeight: '1.4',
                                        wordWrap: 'break-word'
                                    }}
                                >
                                    {msg.role === 'assistant' ? (
                                        <>
                                            <div dangerouslySetInnerHTML={{ __html: parseMarkdown(msg.text) }} />
                                            {Array.isArray(msg.evidence) && msg.evidence.length > 0 && (
                                                <details style={{ marginTop: 8 }}>
                                                    <summary style={{ cursor: 'pointer', fontWeight: 700 }}>Evidence ({msg.evidence.length})</summary>
                                                    <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                                                        {msg.evidence.slice(0, 12).map((item, index) => (
                                                            <li key={`${item.resource_id || item.source_id || 'evidence'}-${index}`}>
                                                                {item.label || `${item.source_id} ${item.relationship || ''} ${item.target_id}`}
                                                                {item.ontology_id ? ` (${item.ontology_id})` : ''}
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </details>
                                            )}
                                        </>
                                    ) : (
                                        msg.text
                                    )}
                                    {msg.streaming && showSpinner && (
                                        <span style={{ display: 'inline-block', marginLeft: 6, fontSize: 10, color: '#888' }}>...</span>
                                    )}
                                </div>
                            </div>
                        ))
                    )}
                    <div ref={messagesEndRef} aria-hidden="true" />
                </div>

                {/* Error Display */}
                {error && (
                    <div style={{
                        backgroundColor: CHAT_COLORS.dangerSoft,
                        color: CHAT_COLORS.danger,
                        padding: '8px 12px',
                        fontSize: '12px',
                        borderTop: `1px solid ${CHAT_COLORS.dangerBorder}`,
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                        <span>{error}</span>
                        <button type="button" aria-label="Dismiss chat error" onClick={() => setError(null)} style={{ background: 'none', border: 'none', color: CHAT_COLORS.danger, cursor: 'pointer', fontSize: 14, padding: 0 }}>x</button>
                    </div>
                )}

                <div style={{ padding: '8px', borderTop: '1px solid var(--theme-color-weak-bdr, #d9e2ec)', background: '#fff' }}>
                    <IxChatInput
                        value={question}
                        disabled={requestActive}
                        state={requestActive ? 'processing' : 'input'}
                        placeholder="Ask about parts, traceability, CAD structure, or change impact..."
                        textareaLabel="Chat question"
                        disclaimer="AI-generated content may require engineering review."
                        onValueChange={(event) => setQuestion(event.detail)}
                        onPromptSubmit={(event) => handleAsk(event.detail)}
                    />
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
