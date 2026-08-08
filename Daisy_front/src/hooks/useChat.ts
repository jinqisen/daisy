import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { message } from 'antd';
import { API_BASE_URL } from '../config';

// 消息接口定义
export interface Message {
    id: string | number; // 本地临时 ID (string) 或 后端 ID (number)
    role: 'user' | 'ai';
    content: string;
    action?: string;
    status: 'sending' | 'sent' | 'error' | 'streaming'; // streaming 用于 AI 正在输入
    createdAt: number;
}

interface UseChatProps {
    token?: string | null;
    onUnauthorized?: () => void;
    onStateUpdate?: (data: any) => void;
    onHistoryLoad?: (snapshots: any[]) => void;
}

type ChatSSEPayload = Record<string, unknown> & {
    type?: string;
    event?: string;
    response?: unknown;
    response_parts?: unknown;
    parts?: unknown;
    content?: unknown;
    timestamp?: unknown;
    data?: Record<string, unknown>;
};

interface SessionInfoResponse {
    session_id?: string | null;
    previous_session_id?: string | null;
    status?: string;
    meta?: Record<string, unknown>;
}

const STREAM_START_TYPES = new Set([
    'response_start',
    'message_start',
    'stream_start',
    'start',
    'chat_started'
]);

const STREAM_CHUNK_TYPES = new Set([
    'response_delta',
    'response_chunk',
    'message_delta',
    'message_chunk',
    'stream_delta',
    'stream_chunk',
    'delta',
    'chunk',
    'token',
    'chat_delta'
]);

const STREAM_END_TYPES = new Set([
    'response_end',
    'response_done',
    'response_complete',
    'message_end',
    'message_done',
    'message_complete',
    'stream_end',
    'stream_done',
    'stream_complete',
    'done',
    'complete',
    'completed',
    'final',
    'chat_completed'
]);

const normalizeEventType = (payload: ChatSSEPayload): string => {
    const rawType = typeof payload.type === 'string'
        ? payload.type
        : (typeof payload.event === 'string' ? payload.event : '');
    return rawType.trim().toLowerCase().replace(/[\s.-]+/g, '_');
};

const findFirstStringField = (...values: unknown[]): string | null => {
    for (const value of values) {
        if (typeof value === 'string') {
            return value;
        }
    }
    return null;
};

const extractTextFromUnknown = (value: unknown, depth = 0): string | null => {
    if (depth > 4 || value == null) {
        return null;
    }

    if (typeof value === 'string') {
        return value;
    }

    if (Array.isArray(value)) {
        const segments = value
            .map(item => extractTextFromUnknown(item, depth + 1))
            .filter((item): item is string => item !== null);
        return segments.length > 0 ? segments.join('') : null;
    }

    if (typeof value === 'object') {
        const record = value as Record<string, unknown>;
        for (const key of ['text', 'content', 'value', 'delta', 'chunk', 'output_text', 'response', 'message', 'final']) {
            const nested = extractTextFromUnknown(record[key], depth + 1);
            if (nested !== null) {
                return nested;
            }
        }
    }

    return null;
};

const extractResponseParts = (payload: ChatSSEPayload): string[] => {
    const partsSource = Array.isArray(payload.response_parts)
        ? payload.response_parts
        : (Array.isArray(payload.parts) ? payload.parts : []);

    return partsSource.filter((item): item is string => typeof item === 'string');
};

const extractStreamChunkText = (payload: ChatSSEPayload): string => {
    const text = findFirstStringField(
        payload.delta,
        payload.chunk,
        payload.text,
        payload.content,
        payload.token,
        payload.response_delta,
        payload.response_chunk,
        payload.partial_response
    );

    if (text !== null) {
        return text;
    }

    return extractTextFromUnknown(payload.delta)
        ?? extractTextFromUnknown(payload.chunk)
        ?? extractTextFromUnknown(payload.content)
        ?? '';
};

const extractLegacyResponseText = (payload: ChatSSEPayload): string => {
    const directText = findFirstStringField(
        payload.response,
        payload.final_response,
        payload.output_text,
        payload.output,
        payload.full_response
    );

    if (directText !== null) {
        return directText;
    }

    return extractTextFromUnknown(payload.response)
        ?? extractTextFromUnknown(payload.final_response)
        ?? extractTextFromUnknown(payload.output)
        ?? '';
};

const extractEventTimestamp = (payload: ChatSSEPayload): number => {
    const rawTimestamp = payload.timestamp;
    if (typeof rawTimestamp === 'string' || typeof rawTimestamp === 'number') {
        const parsed = new Date(rawTimestamp).getTime();
        if (!Number.isNaN(parsed)) {
            return parsed;
        }
    }
    return Date.now();
};

const extractStreamKey = (payload: ChatSSEPayload): string => {
    const key = findFirstStringField(
        payload.stream_id,
        payload.response_id,
        payload.assistant_message_id,
        payload.message_id,
        payload.user_message_id,
        payload.id,
        payload.trace_id
    );

    return key ?? 'default';
};

const extractPayloadSessionId = (payload: ChatSSEPayload): string | null => {
    const data = payload.data && typeof payload.data === 'object'
        ? payload.data as Record<string, unknown>
        : null;

    return findFirstStringField(
        payload.session_id,
        data?.session_id
    );
};

const parseJwtPayload = (token: string): any | null => {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    try {
        const base64Url = parts[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
        const json = decodeURIComponent(
            Array.from(atob(padded))
                .map(c => `%${c.charCodeAt(0).toString(16).padStart(2, '0')}`)
                .join('')
        );
        return JSON.parse(json);
    } catch {
        return null;
    }
};

const isJwtExpired = (token: string, skewSeconds = 30) => {
    const payload = parseJwtPayload(token);
    const exp = payload?.exp;
    if (typeof exp !== 'number') return true;
    const nowSeconds = Math.floor(Date.now() / 1000);
    return exp <= (nowSeconds + skewSeconds);
};

const normalizeToken = (value: string | null | undefined): string | null => {
    if (value == null) return null;
    const trimmed = value.trim();
    if (!trimmed) return null;
    if (trimmed === 'null' || trimmed === 'undefined') return null;
    return trimmed;
};

export const useChat = ({ token: providedToken, onUnauthorized, onStateUpdate, onHistoryLoad }: UseChatProps = {}) => {
    const [messages, setMessages] = useState<Message[]>([]);
    const [loading, setLoading] = useState(false);
    const [isConnected, setIsConnected] = useState(false);
    const [sessionId, setSessionId] = useState<string>('');
    const eventSourceRef = useRef<EventSource | null>(null);
    const sessionIdRef = useRef('');
    const activeAiStreamKeyRef = useRef<string | null>(null);
    const activeAiMessageIdRef = useRef<string | null>(null);
    const activeAiRawContentRef = useRef('');

    const getToken = useCallback((): string | null => {
        const raw = providedToken === undefined ? localStorage.getItem('token') : providedToken;
        const normalized = normalizeToken(raw);
        if (normalized === null && providedToken === undefined && raw !== null) {
            localStorage.removeItem('token');
        }
        return normalized;
    }, [providedToken]);
    
    // Use refs to keep latest callbacks without triggering re-effects
    const onStateUpdateRef = useRef(onStateUpdate);
    const onHistoryLoadRef = useRef(onHistoryLoad);
    const onUnauthorizedRef = useRef(onUnauthorized);

    useEffect(() => {
        onStateUpdateRef.current = onStateUpdate;
    }, [onStateUpdate]);

    useEffect(() => {
        onHistoryLoadRef.current = onHistoryLoad;
    }, [onHistoryLoad]);

    useEffect(() => {
        onUnauthorizedRef.current = onUnauthorized;
    }, [onUnauthorized]);

    useEffect(() => {
        sessionIdRef.current = sessionId;
    }, [sessionId]);

    // 辅助函数：提取 content 和 action
    const extractContentAndAction = (rawContent: string) => {
        let content = rawContent;
        let action = "";

        // 1. Extract <action> tags
        const actionMatch = content.match(/<action>([\s\S]*?)<\/action>/);
        if (actionMatch) {
            action = actionMatch[1].trim();
            content = content.replace(actionMatch[0], "").trim();
        }

        // 2. Extract parentheses (...) or （...）
        const parensRegex = /[\(（]([\s\S]*?)[\)）]/g;
        const extracted: string[] = [];
        
        content = content.replace(parensRegex, (_match, group1) => {
            extracted.push(group1.trim());
            return ""; 
        });
        
        // Clean up extra spaces
        content = content.replace(/\s{2,}/g, " ").trim();

        if (extracted.length > 0) {
            const parensAction = extracted.join("; ");
            if (action) {
                action = `${action}\n${parensAction}`;
            } else {
                action = parensAction;
            }
        }

        return { content, action: action || undefined };
    };

    // Helper: Merge pure action messages into the previous message
    const mergeActionsIntoMessages = (msgs: Message[]): Message[] => {
        return msgs.reduce((acc, curr) => {
            const last = acc[acc.length - 1];
            // Condition for merging:
            // 1. Current message has no content but has action
            // 2. Previous message is from AI
            // 3. Current message is from AI
            if (last && last.role === 'ai' && curr.role === 'ai' && !curr.content && curr.action) {
                // Merge action
                const separator = last.action ? '\n' : '';
                last.action = last.action ? `${last.action}${separator}${curr.action}` : curr.action;
                // Since we modify 'last' in place (which is a reference to an object in 'acc'),
                // we don't push 'curr'
                return acc;
            }
            acc.push(curr);
            return acc;
        }, [] as Message[]);
    };

    const markSendingMessagesAsSent = (msgs: Message[]): Message[] => {
        return msgs.map(msg => (
            msg.status === 'sending'
                ? { ...msg, status: 'sent' as const }
                : msg
        ));
    };

    const appendAiMessages = (prev: Message[], newMsgs: Message[]): Message[] => {
        const updated = markSendingMessagesAsSent(prev);
        const mergedNewMsgs = mergeActionsIntoMessages(newMsgs);

        const [firstMsg, ...remainingMsgs] = mergedNewMsgs;
        const lastMsg = updated[updated.length - 1];

        if (lastMsg && lastMsg.role === 'ai' && !firstMsg.content && firstMsg.action) {
            const separator = lastMsg.action ? '\n' : '';
            const mergedLastMsg: Message = {
                ...lastMsg,
                action: lastMsg.action ? `${lastMsg.action}${separator}${firstMsg.action}` : firstMsg.action
            };
            return [...updated.slice(0, -1), mergedLastMsg, ...remainingMsgs];
        }

        return [...updated, ...mergedNewMsgs];
    };

    const resetActiveAiStream = () => {
        activeAiStreamKeyRef.current = null;
        activeAiMessageIdRef.current = null;
        activeAiRawContentRef.current = '';
    };

    const resetSessionView = useCallback(() => {
        setMessages([]);
        setLoading(false);
        resetActiveAiStream();
        onHistoryLoadRef.current?.([]);
    }, []);

    const upsertStreamingAiMessage = (
        rawContent: string,
        status: Extract<Message['status'], 'streaming' | 'sent'>,
        createdAt: number
    ) => {
        activeAiRawContentRef.current = rawContent;

        const { content, action } = extractContentAndAction(rawContent);
        if (!content && !action && status === 'streaming') {
            return;
        }

        if (!activeAiMessageIdRef.current) {
            const messageId = `stream-${Date.now()}`;
            activeAiMessageIdRef.current = messageId;

            const newAiMsg: Message = {
                id: messageId,
                role: 'ai',
                content,
                action,
                status,
                createdAt
            };

            setMessages(prev => appendAiMessages(prev, [newAiMsg]));
            return;
        }

        const messageId = activeAiMessageIdRef.current;
        setMessages(prev => prev.map(msg => (
            msg.id === messageId
                ? {
                    ...msg,
                    content,
                    action,
                    status
                }
                : msg
        )));
    };

    const startStreamingAiMessage = (payload: ChatSSEPayload) => {
        const streamKey = extractStreamKey(payload);
        if (activeAiStreamKeyRef.current && activeAiStreamKeyRef.current !== streamKey) {
            const existingRaw = activeAiRawContentRef.current;
            if (existingRaw) {
                upsertStreamingAiMessage(existingRaw, 'sent', extractEventTimestamp(payload));
            }
            resetActiveAiStream();
        }

        activeAiStreamKeyRef.current = streamKey;

        const initialChunk = extractStreamChunkText(payload);
        if (initialChunk) {
            upsertStreamingAiMessage(initialChunk, 'streaming', extractEventTimestamp(payload));
        }
    };

    const appendStreamingAiChunk = (payload: ChatSSEPayload) => {
        if (!activeAiStreamKeyRef.current) {
            activeAiStreamKeyRef.current = extractStreamKey(payload);
        }

        const nextStreamKey = extractStreamKey(payload);
        if (activeAiStreamKeyRef.current !== nextStreamKey) {
            startStreamingAiMessage(payload);
            return;
        }

        const chunk = extractStreamChunkText(payload);
        if (chunk === '') {
            return;
        }

        const nextRawContent = `${activeAiRawContentRef.current}${chunk}`;
        upsertStreamingAiMessage(nextRawContent, 'streaming', extractEventTimestamp(payload));
    };

    const finishStreamingAiMessage = (payload?: ChatSSEPayload, finalContent?: string) => {
        if (payload) {
            const streamKey = extractStreamKey(payload);
            if (activeAiStreamKeyRef.current && activeAiStreamKeyRef.current !== streamKey) {
                return;
            }
            if (!activeAiStreamKeyRef.current) {
                activeAiStreamKeyRef.current = streamKey;
            }
        }

        const resolvedFinalContent = finalContent ?? (payload ? extractLegacyResponseText(payload) : '') ?? '';
        const finalRawContent = resolvedFinalContent || activeAiRawContentRef.current;

        if (!finalRawContent) {
            resetActiveAiStream();
            return;
        }

        upsertStreamingAiMessage(
            finalRawContent,
            'sent',
            payload ? extractEventTimestamp(payload) : Date.now()
        );
        resetActiveAiStream();
    };

    const applyHistoryRecords = useCallback((history: any[]) => {
        if (!Array.isArray(history)) {
            resetSessionView();
            return;
        }

        let latestMsgTime = 0;
        let latestMsgRole = '';
        let latestUserMsgStatus = '';

        let formattedMessages: Message[] = history.flatMap((item: any): Message[] => {
            const rawContent = item.content || "";
            const itemId = item.id;
            const msgTime = new Date(item.timestamp).getTime();

            if (msgTime > latestMsgTime) {
                latestMsgTime = msgTime;
                latestMsgRole = item.role;
                latestUserMsgStatus = (item.role === 'user') ? item.status : '';
            }
            
            if (item.role === 'ai') {
                const parts = item.parts || item.response_parts;
                if (parts && Array.isArray(parts) && parts.length > 0) {
                    return parts.map((part: string, index: number) => {
                        const { content, action } = extractContentAndAction(part);
                        return {
                            id: `${itemId}-${index}`,
                            role: 'ai',
                            content,
                            action,
                            status: 'sent',
                            createdAt: msgTime
                        };
                    });
                }

                if (!rawContent.trim()) return [];
                
                const { content, action } = extractContentAndAction(rawContent);
                return [{
                    id: itemId,
                    role: 'ai',
                    content,
                    action,
                    status: 'sent',
                    createdAt: msgTime
                }];
            }

            let status: Message['status'] = 'sent';
            if (item.status === 'failed') {
                status = 'error';
            }

            return [{
                id: itemId,
                role: 'user',
                content: rawContent,
                status,
                createdAt: msgTime
            }];
        });
        
        formattedMessages.sort((a, b) => a.createdAt - b.createdAt);
        formattedMessages = mergeActionsIntoMessages(formattedMessages);

        setMessages(formattedMessages);
        resetActiveAiStream();

        if (latestMsgRole === 'user' && (latestUserMsgStatus === 'pending' || latestUserMsgStatus === 'processing')) {
            setLoading(true);
        } else {
            setLoading(false);
        }

        const snapshots = history
            .map((item: any) => {
                if (item.role === 'ai' && item.state_snapshot) {
                    return {
                        ...item.state_snapshot,
                        user_input: item.user_input,
                        agent_response: item.content
                    };
                }
                return null;
            })
            .filter((item: any) => item !== null);

        onHistoryLoadRef.current?.(snapshots);
    }, [resetSessionView]);

    const loadHistory = useCallback(async (targetSessionId?: string) => {
        try {
            const token = getToken();
            if (!token) {
                resetSessionView();
                return false;
            }

            const effectiveSessionId = targetSessionId ?? sessionIdRef.current;
            if (!effectiveSessionId) {
                resetSessionView();
                return false;
            }

            const res = await axios.get(`${API_BASE_URL}/api/chat/history`, {
                headers: { Authorization: `Bearer ${token}` },
                params: {
                    mode: 'count',
                    limit: 50,
                    session_id: effectiveSessionId,
                }
            });

            applyHistoryRecords(res.data);
            return Array.isArray(res.data) && res.data.length > 0;
        } catch (error) {
            console.error("Failed to load history:", error);
            message.error("加载历史记录失败");
            return false;
        }
    }, [applyHistoryRecords, getToken, resetSessionView]);

    const loadRecentHistory = useCallback(async () => {
        try {
            const token = getToken();
            if (!token) {
                resetSessionView();
                return false;
            }

            const res = await axios.get(`${API_BASE_URL}/api/chat/history`, {
                headers: { Authorization: `Bearer ${token}` },
                params: {
                    mode: 'count',
                    limit: 50,
                }
            });

            applyHistoryRecords(res.data);
            return Array.isArray(res.data) && res.data.length > 0;
        } catch (error) {
            console.error("Failed to load recent history:", error);
            message.error("加载历史记录失败");
            return false;
        }
    }, [applyHistoryRecords, getToken, resetSessionView]);

    const initializeCurrentSession = useCallback(async (createIfMissing = true): Promise<SessionInfoResponse | null> => {
        try {
            const token = getToken();
            if (!token) {
                setSessionId('');
                sessionIdRef.current = '';
                resetSessionView();
                return null;
            }

            const res = await axios.get<SessionInfoResponse>(`${API_BASE_URL}/api/session/current`, {
                headers: { Authorization: `Bearer ${token}` },
                params: {
                    create_if_missing: createIfMissing,
                }
            });

            const nextSessionId = res.data?.session_id ?? '';
            setSessionId(nextSessionId);
            sessionIdRef.current = nextSessionId;
            resetActiveAiStream();

            if (nextSessionId) {
                await loadHistory(nextSessionId);
            } else {
                resetSessionView();
            }

            return res.data;
        } catch (error) {
            console.error("Failed to initialize current session:", error);
            message.error("初始化会话失败");
            return null;
        }
    }, [getToken, loadHistory, resetSessionView]);

    const startNewSession = useCallback(async ({ endCurrent = true }: { endCurrent?: boolean } = {}): Promise<string | null> => {
        try {
            const token = getToken();
            if (!token) {
                message.error("未登录");
                return null;
            }

            const res = await axios.post<SessionInfoResponse>(
                `${API_BASE_URL}/api/session/start`,
                { end_current: endCurrent },
                { headers: { Authorization: `Bearer ${token}` } }
            );

            const nextSessionId = res.data?.session_id ?? '';
            setSessionId(nextSessionId);
            sessionIdRef.current = nextSessionId;
            resetSessionView();

            if (nextSessionId) {
                await loadHistory(nextSessionId);
                return nextSessionId;
            }

            return null;
        } catch (error) {
            console.error("Failed to start new session:", error);
            message.error("创建新会话失败");
            return null;
        }
    }, [getToken, loadHistory, resetSessionView]);

    // 发送消息
    const sendMessage = async (content: string) => {
        if (!content.trim()) return;

        const token = getToken();
        if (!token) {
            message.error("未登录");
            return;
        }

        // 1. Optimistic UI: 立即显示用户消息
        const tempId = `temp-${Date.now()}`;
        const tempMessage: Message = {
            id: tempId,
            role: 'user',
            content: content,
            status: 'sending',
            createdAt: Date.now()
        };

        setMessages(prev => [...prev, tempMessage]);
        setLoading(true);

        try {
            let activeSessionId = sessionIdRef.current;
            if (!activeSessionId) {
                const sessionInfo = await initializeCurrentSession(true);
                activeSessionId = sessionInfo?.session_id ?? '';
            }

            if (!activeSessionId) {
                throw new Error('No active session available');
            }

            // 2. 发送请求
            const res = await axios.post(`${API_BASE_URL}/api/chat`, 
                { 
                    message: content,
                    session_id: activeSessionId
                },
                { headers: { Authorization: `Bearer ${token}` } }
            );

            const resolvedSessionId = typeof res.data?.data?.session_id === 'string' ? res.data.data.session_id : activeSessionId;
            if (resolvedSessionId && resolvedSessionId !== sessionIdRef.current) {
                setSessionId(resolvedSessionId);
                sessionIdRef.current = resolvedSessionId;
            }

            // 3. 更新消息状态：使用后端返回的 ID
            if (res.data.status === 'queued' && res.data.data?.user_message_id) {
                const realId = res.data.data.user_message_id;
                setMessages(prev => prev.map(msg => 
                    msg.id === tempId 
                        ? { ...msg, id: realId, status: 'sent' }
                        : msg
                ));
            } else {
                // Fallback if backend doesn't return ID (shouldn't happen with new backend)
                setMessages(prev => prev.map(msg => 
                    msg.id === tempId ? { ...msg, status: 'sent' } : msg
                ));
            }
        } catch (error) {
            console.error("Send failed:", error);
            setMessages(prev => prev.map(msg => 
                msg.id === tempId ? { ...msg, status: 'error' } : msg
            ));
            message.error("消息发送失败");
        } finally {
            // Loading 状态其实更多代表“用户是否可以再次输入”或者“AI是否正在思考”
            // 但在这里，我们允许用户继续输入，所以 loading 可以设为 false
            // 或者如果想表示 AI 正在生成，可以保持 loading 直到 SSE 收到结束（但 SSE 没有明确结束事件）
            // 简单起见，发送成功就解除 loading
            setLoading(false);
        }
    };

    useEffect(() => {
        const token = getToken();
        if (!token) {
            setSessionId('');
            sessionIdRef.current = '';
            resetSessionView();
            return;
        }

        const restore = async () => {
            try {
                const res = await axios.get<SessionInfoResponse>(`${API_BASE_URL}/api/session/current`, {
                    headers: { Authorization: `Bearer ${token}` },
                    params: {
                        create_if_missing: false,
                    }
                });

                const activeSessionId = res.data?.session_id ?? '';
                setSessionId(activeSessionId);
                sessionIdRef.current = activeSessionId;
                resetActiveAiStream();

                if (activeSessionId) {
                    const hasSessionHistory = await loadHistory(activeSessionId);
                    if (hasSessionHistory) {
                        return;
                    }
                }

                await loadRecentHistory();
            } catch (error) {
                console.error("Failed to restore history after login:", error);
                message.error("恢复聊天记录失败");
            }
        };

        restore();
    }, [getToken, loadHistory, loadRecentHistory, resetSessionView]);

    // SSE 连接管理
    useEffect(() => {
        const token = getToken();
        if (!token) {
            setIsConnected(false);
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
                eventSourceRef.current = null;
            }
            return;
        }

        let retryCount = 0;
        const MAX_RETRIES = 3;
        let isClosing = false;

        const checkTokenValidity = async () => {
            if (isJwtExpired(token)) {
                return false;
            }
            try {
                // 使用开销较小的接口验证 Token，添加时间戳防止缓存
                await axios.get(`${API_BASE_URL}/api/chat/history?mode=count&limit=1&_t=${Date.now()}`, {
                    headers: { Authorization: `Bearer ${token}` }
                });
                return true;
            } catch (error: any) {
                return false;
            }
        };

        const connectSSE = async () => {
            if (isClosing) return;

            // 预先检查 Token，避免 403 无限循环
            const isValid = await checkTokenValidity();
            if (!isValid) {
                console.error("Token expired, aborting SSE connection");
                message.error("请重新登录");
                setIsConnected(false);
                onUnauthorizedRef.current?.();
                return;
            }

            // 关键：await 之后必须重新检查 isClosing。connectSSE 是 async，
            // 在 checkTokenValidity 期间可能已经触发了 effect cleanup（如 StrictMode 的
            // mount→cleanup→mount）。若不重检，旧闭包会在 cleanup 之后仍然创建一个
            // EventSource，导致同一 Redis 频道被订阅两次，每条回复被推送两次 → 重复回复。
            if (isClosing) return;

            // 创建前先关闭任何已存在的连接，确保任意时刻只有一个 SSE 连接。
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
                eventSourceRef.current = null;
            }

            const url = `${API_BASE_URL}/api/chat/stream?token=${encodeURIComponent(token)}`;
            const eventSource = new EventSource(url);
            eventSourceRef.current = eventSource;

            eventSource.onopen = () => {
                console.log("SSE Connected");
                setIsConnected(true);
                retryCount = 0;
            };

            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data) as ChatSSEPayload;
                    const eventType = normalizeEventType(data);
                    if (!eventType && !extractLegacyResponseText(data) && extractResponseParts(data).length === 0) {
                        return;
                    }

                    // Handle Error
                    if (eventType === 'error' || eventType === 'chat_error' || eventType === 'system_error') {
                        console.error("Received error from backend:", data);
                        const errorMsg = data.node && data.node !== "Unknown Node"
                            ? `节点 [${data.node}] 异常: ${data.message}`
                            : `系统异常: ${data.message}`;

                        message.error(errorMsg);
                        setLoading(false);
                        setMessages(prev => {
                            const activeMessageId = activeAiMessageIdRef.current;
                            if (activeMessageId) {
                                return prev.map(msg => (
                                    msg.id === activeMessageId
                                        ? { ...msg, status: 'error' }
                                        : msg
                                ));
                            }

                            // Fallback: mark the last 'sending' message
                            const index = [...prev].reverse().findIndex(m => m.status === 'sending');
                            if (index !== -1) {
                                const realIndex = prev.length - 1 - index;
                                const newMsgs = [...prev];
                                newMsgs[realIndex] = { ...newMsgs[realIndex], status: 'error' };
                                return newMsgs;
                            }
                            return prev;
                        });
                        resetActiveAiStream();
                        return;
                    }

                    // Handle Proactive Message
                    if (eventType === 'proactive_message' && typeof data.content === 'string') {
                        const { content, action } = extractContentAndAction(data.content);
                        
                        setMessages(prev => {
                            const lastMsg = prev[prev.length - 1];
                            // Simple deduplication
                            if (lastMsg && lastMsg.role === 'ai' && lastMsg.content === content) {
                                return prev;
                            }
                            
                            const newAiMsg: Message = {
                                id: `proactive-${Date.now()}`,
                                role: 'ai',
                                content: content,
                                action: action,
                                status: 'sent',
                                createdAt: extractEventTimestamp(data)
                            };
                            return [...prev, newAiMsg];
                        });
                    }

                    if (eventType === 'chat_queued') {
                        setLoading(true);
                    } else if (STREAM_START_TYPES.has(eventType)) {
                        setLoading(true);
                        startStreamingAiMessage(data);
                    } else if (STREAM_CHUNK_TYPES.has(eventType)) {
                        appendStreamingAiChunk(data);
                    } else if (STREAM_END_TYPES.has(eventType)) {
                        finishStreamingAiMessage(data);
                        setLoading(false);
                    } else {
                        const responseParts = extractResponseParts(data);
                        if (responseParts.length > 0) {
                            const aiMsgId = `ai-${Date.now()}`;
                            const createdAt = extractEventTimestamp(data);
                            const newMsgs: Message[] = responseParts.map((part, index) => {
                                const { content, action } = extractContentAndAction(part);
                                return {
                                    id: `${aiMsgId}-${index}`,
                                    role: 'ai',
                                    content,
                                    action,
                                    status: 'sent',
                                    createdAt: createdAt + index
                                };
                            });

                            resetActiveAiStream();
                            setMessages(prev => appendAiMessages(prev, newMsgs));
                            setLoading(false);
                        } else {
                            const legacyResponse = extractLegacyResponseText(data);
                            if (legacyResponse) {
                                if (activeAiStreamKeyRef.current) {
                                    finishStreamingAiMessage(data, legacyResponse);
                                } else {
                                    const { content, action } = extractContentAndAction(legacyResponse);
                                    if (content || action) {
                                        const newAiMsg: Message = {
                                            id: `ai-${Date.now()}`,
                                            role: 'ai',
                                            content,
                                            action,
                                            status: 'sent',
                                            createdAt: extractEventTimestamp(data)
                                        };

                                        setMessages(prev => {
                                            const lastMsg = prev[prev.length - 1];
                                            if (lastMsg && lastMsg.role === 'ai' && lastMsg.content === content && lastMsg.action === action) {
                                                return prev;
                                            }
                                            return appendAiMessages(prev, [newAiMsg]);
                                        });
                                        setLoading(false);
                                    }
                                }
                            }
                        }
                    }

                    // Handle State Update
                    if (onStateUpdateRef.current) {
                        onStateUpdateRef.current(data);
                    }

                } catch (e) {
                    console.error("SSE Parse Error", e);
                }
            };

            eventSource.onerror = async (e) => {
                const isStaleConnection = eventSourceRef.current !== eventSource;
                const isClosedConnection = eventSource.readyState === EventSource.CLOSED;

                // Ignore expected errors from cleanup, reload, or stale SSE instances.
                if (isClosing || isStaleConnection || isClosedConnection) {
                    return;
                }

                console.warn("SSE connection interrupted, attempting recovery", e);
                setIsConnected(false);
                eventSource.close();
                resetActiveAiStream();

                // 检查 Token 是否依然有效
                const isValid = await checkTokenValidity();
                if (!isValid) {
                    message.error("请重新登录");
                    onUnauthorizedRef.current?.();
                    return; // 停止重连
                }
                
                // 简单的重连逻辑：指数退避
                if (retryCount < MAX_RETRIES) {
                    const timeout = Math.min(1000 * Math.pow(2, retryCount), 10000);
                    retryCount++;
                    console.log(`SSE Reconnecting in ${timeout}ms... (Attempt ${retryCount}/${MAX_RETRIES})`);
                    
                    setTimeout(() => {
                        if (eventSourceRef.current === eventSource) { // 防止多重重连
                            connectSSE();
                        }
                    }, timeout);
                } else {
                    message.error("连接断开，请刷新页面");
                }
            };
        };

        connectSSE();

        return () => {
            isClosing = true;
            resetActiveAiStream();
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
                eventSourceRef.current = null;
            }
        };
    }, [getToken, loadHistory]);

    return {
        messages,
        loading,
        isConnected,
        sessionId,
        sendMessage,
        loadHistory,
        startNewSession,
        initializeCurrentSession,
    };
};
