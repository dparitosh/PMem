import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Sparkles } from 'lucide-react';
import '../CSS/chat.css';
import { API, buildUrl, buildSemanticServiceUrl, config } from '../config';
import { validateChatInput, ValidationError } from '../utils/validation';
import { logger } from '../utils/logger';
import { formatChatMarkdown } from '../utils/chatMarkdown';
import { clearClientSessionId, getClientSessionId, setClientSessionId } from '../services/apiClient';
import { serviceAuthHeaders, getCredentialProfile, handleSessionRejection, wasBrowserSessionExpired } from '../services/serviceAuth';
import { createChatFrameParser } from '../services/chatStreamFrames';

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

const Chatbot = ({ setChatResults, graphData, ontologyId = '', ontologyPrefix = '' }) => {
    const [chatMessages, setChatMessages] = useState([]);
    const [question, setQuestion] = useState('');
    const [showSpinner, setShowSpinner] = useState(false);
    const [requestActive, setRequestActive] = useState(false);
    const [error, setError] = useState(null);
    const [statusLabel, setStatusLabel] = useState(null);
    const [historyVersion, setHistoryVersion] = useState(0);
    const abortRef = useRef(null);
    const requestActiveRef = useRef(false);
    const messageSequenceRef = useRef(0);
    const messagesEndRef = useRef(null);
    const followLatestRef = useRef(true);
    const [followingLatest, setFollowingLatest] = useState(true);
    const sessionIdRef = useRef(getClientSessionId());
    const scopeId = ontologyId || graphData?.view?.ontology_id || graphData?.ontology_id || graphData?.view?.ontology_prefix || graphData?.ontology_prefix || '';
    const scopePrefix = ontologyPrefix || graphData?.view?.ontology_prefix || graphData?.ontology_prefix || '';
    const scopeRef = useRef({ id: scopeId, prefix: scopePrefix });
    const resetConversation = useCallback(() => {
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
        followLatestRef.current = true; setFollowingLatest(true);
        setQuestion('');
    }, [setChatResults]);

    useEffect(() => {
        if (scopeRef.current.id === scopeId && scopeRef.current.prefix === scopePrefix) return;
        scopeRef.current = { id: scopeId, prefix: scopePrefix };
        resetConversation();
    }, [scopeId, scopePrefix, resetConversation]);

    useEffect(() => {
        let readKey = getCredentialProfile('GRAPH_READ_TOKEN');
        const reset = () => {
            const nextKey = getCredentialProfile('GRAPH_READ_TOKEN');
            if (nextKey === readKey) return;
            const previousKey = readKey;
            readKey = nextKey;
            if (!nextKey && wasBrowserSessionExpired()) {
                abortRef.current?.abort();
                setError('Access expired. Reconnect in Admin to resume this conversation.');
                return;
            }
            if (!previousKey && sessionIdRef.current) {
                setChatMessages([]);
                setHistoryVersion(value => value + 1);
                return;
            }
            resetConversation();
        };
        const replaced = () => {
            readKey = getCredentialProfile('GRAPH_READ_TOKEN');
            abortRef.current?.abort();
            setChatMessages([]);
            setChatResults?.([]);
            setError(null);
            setHistoryVersion(value => value + 1);
        };
        window.addEventListener('depo:session-replaced', replaced);
        window.addEventListener('depo:credentials-changed', reset);
        window.addEventListener('depo:credentials-cleared', resetConversation);
        return () => {
            window.removeEventListener('depo:session-replaced', replaced);
            window.removeEventListener('depo:credentials-changed', reset);
            window.removeEventListener('depo:credentials-cleared', resetConversation);
        };
    }, [resetConversation]);

    useEffect(() => {
        const identifier = sessionIdRef.current;
        const credential = getCredentialProfile('GRAPH_READ_TOKEN');
        if (!identifier || !credential) return undefined;
        const controller = new AbortController();
        let active = true;
        const timeout = setTimeout(() => controller.abort(), 10000);
        const url = buildSemanticServiceUrl('agentic', `/api/v1/chat/sessions/${encodeURIComponent(identifier)}/history`);
        fetch(url, { headers: serviceAuthHeaders(url), signal: controller.signal, credentials: 'omit', redirect: 'error' })
            .then(async response => {
                if ([404, 410].includes(response.status)) {
                    if (active && !requestActiveRef.current) { clearClientSessionId(); sessionIdRef.current = null; }
                    return null;
                }
                if (!response.ok) throw new Error(`Conversation restore failed (${response.status})`);
                return response.json();
            }).then(body => {
                if (!active || credential !== getCredentialProfile('GRAPH_READ_TOKEN') || requestActiveRef.current || !Array.isArray(body?.turns)) return;
                const restored = body.turns.flatMap(turn => [
                    { id: `${turn.job_id}-user`, role: 'user', text: turn.user_request || '' },
                    { id: `${turn.job_id}-assistant`, role: 'assistant', text: turn.response || '', evidence: turn.evidence, generation: turn.generation, retainedPromptJobId: turn.job_id },
                ]);
                setChatMessages(current => current.length ? current : restored);
            }).catch(error => { if (active && error.name !== 'AbortError') setError(error.message); })
            .finally(() => clearTimeout(timeout));
        return () => { active = false; clearTimeout(timeout); controller.abort(); };
    }, [scopeId, scopePrefix, historyVersion]);

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
            followLatestRef.current = true;
            setFollowingLatest(true);
            
            // Cancel any in-flight request and finalize its placeholder.
            if (abortRef.current) abortRef.current.abort();
            setChatMessages(prev => prev.map(item =>
                item.streaming ? { ...item, streaming: false } : item
            ));
            controller = new AbortController();
            abortRef.current = controller;
            requestActiveRef.current = true;
            setRequestActive(true);
            // config validates the shared 1-second to 30-minute range.
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
            let streamBytes = 0;
            let streamCompleted = false;
            let streamFailed = false;
            let evidenceReceived = false;
            let responseEvidence = [];
            let responseSources = [];
            let responseAnswerable = null;

            logger.data('Sending chat request:', validated);

            let activeSessionId = getClientSessionId() || sessionIdRef.current;
            sessionIdRef.current = activeSessionId;
            const graphContext = scopeId ? { ontology: scopeId, ontology_prefix: scopePrefix } : null;
            let requestAuthorization = '';
            const sendRequest = (sessionId) => {
                const authHeaders = serviceAuthHeaders(buildUrl(API.chat.chatStream), 'post');
                requestAuthorization = authHeaders.Authorization || '';
                return fetch(buildUrl(API.chat.chatStream), {
                method: 'POST',
                credentials: 'omit',
                redirect: 'error',
                headers: {
                    'Content-Type': 'application/json',
                    ...authHeaders,
                    ...(sessionId ? { 'X-Session-ID': sessionId } : {}),
                },
                body: JSON.stringify({ session_id: sessionId, message: validated, graph_context: graphContext }),
                signal: controller.signal,
                });
            };

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
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                handleSessionRejection(response.status, requestAuthorization, payload?.detail);
                throw new Error(payload?.detail || `Server error ${response.status}`);
            }

            if (!response.body) throw new Error('The server returned an empty chat stream.');
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            const processEvent = (parsed) => {
                if (controller.signal.aborted) return;
                if (streamCompleted) return;
                    if (typeof parsed.token === 'string') {
                        accumulated += parsed.token;
                        setShowSpinner(false);
                        setStatusLabel(null);
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, text: accumulated } : m
                        ));
                    } else if (Array.isArray(parsed.evidence)) {
                        if (typeof parsed.response === 'string') {
                            accumulated = parsed.response;
                        }
                        evidenceReceived = true;
                        responseEvidence = parsed.evidence;
                        responseSources = Array.isArray(parsed.sources) ? parsed.sources : [];
                        responseAnswerable = parsed.answerable;
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, text: accumulated, evidence: responseEvidence, sources: responseSources, answerable: responseAnswerable, generation: parsed.generation, runId: parsed.run_id, retainedPromptJobId: parsed.retained_prompt_job_id } : m
                        ));
                    } else if (parsed.status) {
                        setStatusLabel(parsed.status);
                    } else if (parsed.done === true) {
                        streamCompleted = true;
                        if ((!accumulated || !evidenceReceived) && !streamFailed) {
                            streamFailed = true;
                            const emptyMessage = 'The response was incomplete or missing evidence. Please try again.';
                            setError(emptyMessage);
                            setQuestion(messageText);
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
                        const errMsg = (typeof parsed.error === 'string' ? parsed.error : 'An error occurred.') +
                            (typeof parsed.action === 'string' ? ` ${parsed.action}` : '') +
                            (typeof parsed.request_id === 'string' && parsed.request_id ? ` Request ID: ${parsed.request_id}` : '');
                        setError(errMsg);
                        setQuestion(messageText);
                        setStatusLabel(null);
                        setShowSpinner(false);
                        setChatMessages(prev => prev.map(m =>
                            m.id === assistantId ? { ...m, text: errMsg, streaming: false, runId: parsed.run_id, requestId: parsed.request_id, failureCategory: parsed.category } : m
                        ));
                    }
            };
            const frames = createChatFrameParser(processEvent);

            try {
              while (true) {
                if (controller.signal.aborted) return;
                const { done, value } = await reader.read();
                if (done) break;
                streamBytes += value.byteLength;
                if (streamBytes > 8 * 1024 * 1024) { await reader.cancel(); throw new Error('Chat response exceeds the permitted size. Narrow your question.'); }
                frames.push(decoder.decode(value, { stream: true }));
                if (streamCompleted) { await reader.cancel?.(); break; }
              }
              if (!streamCompleted) {
                frames.push(decoder.decode());
                frames.finish();
              }
            } finally {
              if (!streamCompleted) await Promise.resolve(reader.cancel?.()).catch(() => {});
              reader.releaseLock?.();
            }
            if (!streamCompleted) {
                throw new Error('The chat stream ended before completion; the response is incomplete.');
            }

        } catch (err) {
            if (!controller?.signal.aborted || timedOut) setQuestion(messageText);
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
                    if (Array.isArray(data.queries) && data.queries.length > 0 && data.queries.every(query => typeof query === 'string' && query.trim())) {
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
        if (followLatestRef.current) messagesEndRef.current?.scrollIntoView?.({ block: 'end' });
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
            {/* Compact session utility row; the surrounding IX card owns the panel title. */}
            <div style={{
                background: 'var(--theme-color-std-background, #f4f6f8)',
                color: 'var(--theme-color-std-text, #252a2e)', padding: '6px 12px',
                borderBottom: '1px solid var(--theme-color-weak-bdr, #d9e2ec)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                flexShrink: 0, gap: 8, flexWrap: 'wrap',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Sparkles size={14} />
                    <span style={{ fontSize: 13, fontWeight: 600 }}>Evidence-grounded answers</span>
                    {chatMessages.length > 0 && (
                        <span style={{
                            background: 'rgba(255,255,255,0.2)', borderRadius: 10,
                            padding: '1px 8px', fontSize: 11, fontWeight: 600,
                        }}>{Math.ceil(chatMessages.length / 2)} {chatMessages.length <= 2 ? 'turn' : 'turns'}</span>
                    )}
                </div>
                <div className="chat-toolbar-actions">
                <a href="#/admin" title="Manage access in Admin → Service credentials">Manage access</a>
                {chatMessages.length > 0 && (
                    <button
                        type="button"
                        onClick={resetConversation}
                        title="Clear conversation"
                        style={{
                            background: 'var(--theme-color-std-background)', color: 'var(--theme-color-std-text, #252a2e)',
                            border: '1px solid rgba(255,255,255,0.3)', borderRadius: 5,
                            padding: '2px 10px', fontSize: 11, cursor: 'pointer',
                        }}
                    >Clear conversation</button>
                )}
                </div>
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
                <div className="chat-history-region">
                <div className='chat-messages' role="log" aria-label="Conversation history" aria-live="off" tabIndex={0}
                    onScroll={event => {
                        const panel = event.currentTarget;
                        const follow = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 80;
                        followLatestRef.current = follow; setFollowingLatest(follow);
                    }} style={{
                    flex: 1,
                    overflowY: 'auto',
                    padding: '10px 12px',
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
                        chatMessages.map((msg, index) => (
                            <div
                                key={msg.id}
                                style={{
                                    marginBottom: '12px',
                                    display: 'flex',
                                    justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start'
                                }}
                            >
                                <div
                                    style={{
                                        maxWidth: msg.role === 'user' ? '90%' : '100%',
                                        minWidth: 0,
                                        padding: '10px 12px',
                                        borderRadius: '10px',
                                        backgroundColor: msg.role === 'user' ? CHAT_COLORS.primary : CHAT_COLORS.assistantBubble,
                                        color: msg.role === 'user' ? '#fff' : 'var(--ui-text, var(--theme-color-std-text, #252a2e))',
                                        border: msg.role === 'assistant' ? '1px solid var(--ui-border, #e2e6ea)' : 'none',
                                        boxShadow: msg.role === 'assistant' ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
                                        fontSize: '14px',
                                        lineHeight: '1.65',
                                        overflowWrap: 'anywhere',
                                        whiteSpace: msg.role === 'user' ? 'pre-wrap' : 'normal'
                                    }}
                                >
                                    <div className="chat-message-label">{msg.role === 'user' ? 'You · Question' : 'Companion · Response'} {Math.floor(index / 2) + 1}</div>
                                    {msg.role === 'assistant' ? (
                                        <>
                                            <div dangerouslySetInnerHTML={{ __html: formatChatMarkdown(msg.text) }} />
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
                                    {msg.generation && <p>Model generation: {msg.generation.status}</p>}
                                    {msg.generation?.prompt_details && <details><summary>Prompt details</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 240, overflow: 'auto' }}>{JSON.stringify(msg.generation.prompt_details, null, 2)}</pre></details>}
                                    {msg.runId && <small>Agent run: {msg.runId}</small>}
                                    {msg.retainedPromptJobId && <small>Saved conversation result: {msg.retainedPromptJobId}</small>}
                                    {msg.stopped && <p>Stopped — partial text is not a completed answer.</p>}
                                    {msg.streaming && showSpinner && (
                                        <span style={{ display: 'inline-block', marginLeft: 6, fontSize: 10, color: '#888' }}>...</span>
                                    )}
                                </div>
                            </div>
                        ))
                    )}
                    <div ref={messagesEndRef} aria-hidden="true" />
                </div>
                {!followingLatest && chatMessages.length > 0 && <button type="button" className="chat-latest-button" onClick={() => {
                    followLatestRef.current = true; setFollowingLatest(true);
                    messagesEndRef.current?.scrollIntoView?.({ block: 'end' });
                }}>Jump to latest message</button>}
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

                <div className="chat-composer">
                    <form className="chat-composer-form" onSubmit={event => { event.preventDefault(); handleAsk(question); }}>
                        <textarea
                            value={question}
                            disabled={requestActive}
                            rows={2}
                            placeholder="Ask about parts, traceability, or ontology resources..."
                            aria-label="Chat question"
                            onChange={event => setQuestion(event.target.value)}
                            onKeyDown={event => {
                                if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                                    event.preventDefault();
                                    if (!requestActive && question.trim()) handleAsk(question);
                                }
                            }}
                        />
                        <button type="submit" aria-label="Send chat question" disabled={requestActive || !question.trim()}>Send</button>
                    </form>
                    <details className="chat-answer-help"><summary>About these answers</summary>Ontology search returns matching resources and evidence; comparison and impact analysis are not supported here. Use Shift+Enter for a new line.</details>
                    {requestActive && <button type="button" onClick={() => {
                        abortRef.current?.abort(); setStatusLabel('Stopped. Partial text is not a completed answer.');
                        setChatMessages(messages => messages.map(message => message.streaming ? { ...message, streaming: false, stopped: true } : message));
                    }}>Stop response</button>}
                </div>
            </div>
        </div>
    );
};

export default React.memo(Chatbot);
