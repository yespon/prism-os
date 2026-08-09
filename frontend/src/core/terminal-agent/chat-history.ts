/**
 * Chat History Manager — localStorage-based chat session persistence.
 * Supports multi-tab sessions, history loading, pagination, and title generation.
 */

import { readMigratedStorage, writePrismOSStorage } from "@/core/storage/brand-migration";

export interface ChatSession {
  id: string;
  title: string;
  modelName: string;
  mode: 'cmd' | 'agent';
  assetId?: string;
  assetIp?: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  /** Parts from AI SDK v6 format */
  parts?: any[];
  /** Tool invocations */
  toolInvocations?: any[];
  /** User feedback */
  feedback?: 'up' | 'down';
  timestamp: string;
}

const STORAGE_KEY = 'prismos_terminal_chats';
const LEGACY_STORAGE_KEY = 'opsintech_terminal_chats';
const MAX_SESSIONS = 50;
const PAGE_SIZE = 40;

export class ChatHistoryManager {
  /**
   * Load all chat sessions from storage.
   */
  static loadSessions(): ChatSession[] {
    return readMigratedStorage({
      storage: localStorage,
      key: STORAGE_KEY,
      legacyKey: LEGACY_STORAGE_KEY,
      parse: parseChatSessions,
    }) ?? [];
  }

  /**
   * Save a session to storage.
   */
  static saveSession(session: ChatSession): void {
    const sessions = ChatHistoryManager.loadSessions();
    const idx = sessions.findIndex((s) => s.id === session.id);
    session.updatedAt = new Date().toISOString();

    if (idx >= 0) {
      sessions[idx] = session;
    } else {
      sessions.unshift(session);
    }

    // Enforce max sessions limit
    while (sessions.length > MAX_SESSIONS) {
      sessions.pop();
    }

    try {
      writePrismOSStorage(localStorage, STORAGE_KEY, JSON.stringify(sessions));
    } catch {
      console.warn('[ChatHistory] Failed to save session');
    }
  }

  /**
   * Delete a session by ID.
   */
  static deleteSession(sessionId: string): void {
    const sessions = ChatHistoryManager.loadSessions().filter((s) => s.id !== sessionId);
    writePrismOSStorage(localStorage, STORAGE_KEY, JSON.stringify(sessions));
  }

  /**
   * Load a specific session by ID.
   */
  static loadSession(sessionId: string): ChatSession | null {
    const sessions = ChatHistoryManager.loadSessions();
    return sessions.find((s) => s.id === sessionId) || null;
  }

  /**
   * Get paginated sessions (for history list).
   */
  static getSessionsPage(page: number = 1): ChatSession[] {
    const sessions = ChatHistoryManager.loadSessions();
    const start = (page - 1) * PAGE_SIZE;
    return sessions.slice(start, start + PAGE_SIZE);
  }

  /**
   * Search sessions by title or content.
   */
  static searchSessions(query: string): ChatSession[] {
    const sessions = ChatHistoryManager.loadSessions();
    const lower = query.toLowerCase();
    return sessions.filter(
      (s) =>
        s.title.toLowerCase().includes(lower) ||
        s.messages.some(
          (m) => m.content && m.content.toLowerCase().includes(lower)
        )
    );
  }

  /**
   * Generate a session ID.
   */
  static generateId(): string {
    return `chat_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
  }
}

function parseChatSessions(raw: string): ChatSession[] {
  const value: unknown = JSON.parse(raw);
  if (!Array.isArray(value) || !value.every((item) => typeof item === "object" && item !== null && !Array.isArray(item))) {
    throw new Error("Invalid chat session array");
  }
  return value as ChatSession[];
}
