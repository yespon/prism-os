/**
 * TodoContextTracker — Per-session context usage tracking.
 * Ported from Chaterm's src/main/agent/services/todo_context_tracker.ts
 *
 * Tracks context usage percentage and provides threshold-based suggestions.
 */

const CONTEXT_THRESHOLDS = {
  WARNING: 50,   // Time to start thinking about wrapping up
  CRITICAL: 70,  // Should plan new task handoff soon
  MAXIMUM: 90,   // Must create new task immediately
} as const;

export type ThresholdLevel = 'normal' | 'warning' | 'critical' | 'maximum';

export interface ContextSuggestion {
  suggest: boolean;
  reason?: string;
  level: ThresholdLevel;
}

export class TodoContextTracker {
  private currentUsage = 0;
  private activeTodoId: string | null = null;

  /**
   * Update the tracked context usage percentage.
   */
  updateUsage(usagePercent: number): ContextSuggestion {
    this.currentUsage = Math.min(100, Math.max(0, usagePercent));

    if (this.currentUsage >= CONTEXT_THRESHOLDS.MAXIMUM) {
      return {
        suggest: true,
        level: 'maximum',
        reason: `上下文使用率达到 ${this.currentUsage}%，已超过最大阈值。建议立即创建新任务来继续剩余工作。`,
      };
    }

    if (this.currentUsage >= CONTEXT_THRESHOLDS.CRITICAL) {
      return {
        suggest: true,
        level: 'critical',
        reason: `上下文使用率达到 ${this.currentUsage}%，已接近临界值。请计划在完成当前任务后创建新任务。`,
      };
    }

    if (this.currentUsage >= CONTEXT_THRESHOLDS.WARNING) {
      return {
        suggest: false,
        level: 'warning',
        reason: `上下文使用率 ${this.currentUsage}%，请注意监控。`,
      };
    }

    return { suggest: false, level: 'normal' };
  }

  /**
   * Set the active todo being worked on.
   */
  setActiveTodo(todoId: string | null): void {
    this.activeTodoId = todoId;
  }

  /**
   * Get current state.
   */
  getState() {
    return {
      currentUsage: this.currentUsage,
      activeTodoId: this.activeTodoId,
      level: this.getLevel(),
    };
  }

  private getLevel(): ThresholdLevel {
    if (this.currentUsage >= CONTEXT_THRESHOLDS.MAXIMUM) return 'maximum';
    if (this.currentUsage >= CONTEXT_THRESHOLDS.CRITICAL) return 'critical';
    if (this.currentUsage >= CONTEXT_THRESHOLDS.WARNING) return 'warning';
    return 'normal';
  }

  /**
   * Reset tracker.
   */
  reset(): void {
    this.currentUsage = 0;
    this.activeTodoId = null;
  }
}
