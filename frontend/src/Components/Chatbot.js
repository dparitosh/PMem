import React, { useState, useRef, useEffect } from 'react';
import { Sparkles } from 'lucide-react';
import { IxChatInput } from '@siemens/ix-react';
import '../CSS/chat.css';
import { API, buildUrl, config } from '../config';
import { validateChatInput, ValidationError } from '../utils/validation';
import { logger } from '../utils/logger';
import { formatChatMarkdown } from '../utils/chatMarkdown';
import { clearClientSessionId, getClientSessionId, setClientSessionId } from '../services/apiClient';
import { serviceAuthHeaders, getCredentialProfile, expireBrowserSession } from '../services/serviceAuth';

const CHAT_COLORS = {
    primary: '#005a9c',
    primarySoft: 'var(--theme-color-soft-primary, var(--ui-surface, #e8f1fc))',
    primaryBorder: '#c2d9f0',
    surfaceMuted: 'var(--theme-color-std-background, #f8fafc)',
    assistantBubble: 'var(--theme-color-2, var(--ui-surface, #eef2f6))',
    danger: '#c62828',
    dangerSoft: '#ffebee',
    dangerBorder: '#ffcdd2',
    textMuted: 'var(--theme-color-soft-text, #66788a)',
};

const Chatbot = ({ setChatResults, graphData, searchResults }) => {
    const [chatMessages, setChatMessages] = useState([]);
    const [question, setQuestion] = useState('');
    const [showSpinner, setShowSpinner] = useState(false);
    const [requestActive, setRequestActive] = useState(false);
    const [error, setError] = useState(null);
    const [statusLabel, setStatusLabel] = useState(null);
    const abortRef = useRef(null);
    const requestActiveRef = useRef(false);
    const messageSequenceRef = useRef(0);
    const messagesEndRef = useRef(null);
    const sessionIdRef = useRef(getClientSessionId());

    useEffect(() => {
        let readKey = getCredentialProfile('GRAPH_READ_TOKEN');
        const reset = () => {
            const nextKey = getCredentialProfile('GRAPH_READ_TOKEN');
            if (nextKey === readKey) return;
            readKey = nextKey;
            abortRef.current?.abort();
            abortRef.current = null;
            requestActiveRef.current = false;
            clearClientSessionId();
            sessionIdRef.current = null;
            setChatMessages([]);
            setChatResults?.([]);
            setRequestActive(false);
            setShowSpinner(false);
            setStatusLabel(null);
            setError(null);
        };
        window.addEventListener('depo:credentials-changed', reset);
        window.addEventListener('depo:credentials-cleared', reset);
        return () => {
            window.removeEventListener('depo:credentials-changed', reset);
            window.removeEventListener('depo:credentials-cleared', reset);
        };
    }, [setChatResults]);

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
            ontology: graphData?.view?.ontology_id || graphData?.ontology_id || graphData?.view?.ontology_prefix || graphData?.ontology_prefix || '',
            importId: graphData?.view?.import_id || graphData?.import_id || '',
            searchQuery: graphData?.view?.search || graphData?.search || '',
            visibleGraph: graphSummary(visibleGraph, 'visibleGraph'),
            searchResults: graphSummary(searchGraph, 'searchResults'),
        };
    };

    /* response formatting lives in utils/chatMarkdown.js */
    const parseMarkdown = formatChatMarkdown;
    const [sampleQueries, setSampleQueries] = useState([
        'Find ontology resources matching product',
        'Find ontology resources matching requirement',
        'Find ontology resources matching measurement',
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
            let evidenceReceived = false;
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
                    ...serviceAuthHeaders(buildUrl(API.chat.chatStream), 'post'),
                    ...(sessionId ? { 'X-Session-ID': sessionId } : {}),
                },
                body: JSON.stringify({ session_id: sessionId, message: validated, graph_context: graphContext }),
                signal: controller.signal,
            });

            let response = await sendRequest(activeSessionId);
            if (activeSessionId && [404, 410].includes(response.status)) {
                // An expired session must not be silently reused. Retrieval is
                // read-only, so retry once with a fresh server-owned session.
                clearClientSessionId();
                sessionIdRef.current = null;
                activeSessionId = null;
                response = await sendRequest(null);
            }
            if (controller.signal.aborted) return;
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
            if (response.status === 401) expireBrowserSession(getCredentialProfile('GRAPH_READ_TOKEN'));
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload?.detail || `Server error ${response.status}`);
            }

            if (!response.body) throw new Error('The server returned an empty chat stream.');
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            const processLine = (line) => {
                if (controller.signal.aborted) return;
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
                        evidenceReceived = true;
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
                        if ((!accumulated || !evidenceReceived) && !streamFailed) {
                            streamFailed = true;
                            const emptyMessage = 'The response was incomplete or missing evidence. Please try again.';
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
            if (!streamCompleted) {
                throw new Error('The chat stream ended before completion; the response is incomplete.');
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

            if (controller?.signal.aborted) return;
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
                        ...serviceAuthHeaders(buildUrl(API.chat.sampleQueries), 'get'),
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
            backgroundColor: 'var(--theme-color-std-background, var(--ui-surface, #fff))',
            color: 'var(--theme-color-std-text, var(--ui-text, #252a2e))',
            overflow: 'hidden'
        }}>
            <div style={{ padding: "8px 14px", flexShrink: 0 }}><a href="#/admin">Manage access in Admin → Service credentials</a></div>
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
                            background: 'var(--theme-color-std-background)', color: 'var(--theme-color-std-text, #252a2e)',
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
            <div style={{ flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column', backgroundColor: 'var(--theme-color-std-background, var(--ui-surface, #fff))' }}>
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
                                        color: msg.role === 'user' ? '#fff' : 'var(--theme-color-std-text, #252a2e)',
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

                <div style={{ padding: '8px', borderTop: '1px solid var(--theme-color-weak-bdr, #d9e2ec)', background: 'var(--theme-color-std-background, var(--ui-surface, #fff))' }}>
                    <IxChatInput
                        value={question}
                        disabled={requestActive}
                        state={requestActive ? 'processing' : 'input'}
                        placeholder="Ask about parts, traceability, CAD structure, or change impact..."
                        textareaLabel="Chat question"
                        disclaimer="Ontology search returns matching resources and evidence; comparison and impact analysis are not supported here."
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
