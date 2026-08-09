import type { Todo, FocusChainState, FocusChainTransition, FocusChainHandoff } from './todo/TodoSchemas'

const CONTEXT_THRESHOLDS = {
  WARNING: 50,
  CRITICAL: 70,
  MAXIMUM: 90
} as const

export class FocusChainService {
  private state: FocusChainState
  private transitions: FocusChainTransition[] = []
  private todos: Todo[] = []
  private readonly taskId: string
  private onTodosChange?: (todos: Todo[]) => void

  constructor(taskId: string, initialTodos: Todo[] = [], onTodosChange?: (todos: Todo[]) => void) {
    this.taskId = taskId
    this.todos = initialTodos
    this.onTodosChange = onTodosChange
    this.state = this.createInitialState(taskId)
    this.syncWithTodos()
  }

  private createInitialState(taskId: string): FocusChainState {
    return {
      taskId,
      focusedTodoId: null,
      chainProgress: 0,
      totalTodos: 0,
      completedTodos: 0,
      currentContextUsage: 0,
      lastFocusChangeAt: new Date(),
      autoTransitionEnabled: true
    }
  }

  getState(): FocusChainState {
    return { ...this.state }
  }

  getTodos(): Todo[] {
    return [...this.todos]
  }

  getTransitions(): FocusChainTransition[] {
    return [...this.transitions]
  }

  updateContextUsage(usagePercent: number): {
    shouldTransition: boolean
    reason?: string
    threshold?: keyof typeof CONTEXT_THRESHOLDS
  } {
    this.state.currentContextUsage = Math.min(100, Math.max(0, usagePercent))

    if (usagePercent >= CONTEXT_THRESHOLDS.MAXIMUM) {
      return {
        shouldTransition: true,
        reason: `Context usage at ${usagePercent}% exceeds maximum threshold. Consider creating a new task to continue.`,
        threshold: 'MAXIMUM'
      }
    }

    if (usagePercent >= CONTEXT_THRESHOLDS.CRITICAL) {
      return {
        shouldTransition: false,
        reason: `Context usage at ${usagePercent}% is critical. Plan to wrap up current work soon.`,
        threshold: 'CRITICAL'
      }
    }

    if (usagePercent >= CONTEXT_THRESHOLDS.WARNING) {
      return {
        shouldTransition: false,
        reason: `Context usage at ${usagePercent}%. Monitor usage as you continue.`,
        threshold: 'WARNING'
      }
    }

    return { shouldTransition: false }
  }

  async focusTodo(todoId: string, reason: FocusChainTransition['reason'] = 'user_request'): Promise<void> {
    const todo = this.todos.find((t) => t.id === todoId)

    if (!todo) {
      console.warn(`[FocusChainService] Todo ${todoId} not found`)
      return
    }

    const transition: FocusChainTransition = {
      fromTodoId: this.state.focusedTodoId,
      toTodoId: todoId,
      reason,
      timestamp: new Date(),
      contextUsageAtTransition: this.state.currentContextUsage
    }
    this.transitions.push(transition)

    const previousFocusedId = this.state.focusedTodoId
    this.state.focusedTodoId = todoId
    this.state.lastFocusChangeAt = new Date()

    const now = new Date()
    this.todos = this.todos.map((t) => ({
      ...t,
      isFocused: t.id === todoId,
      focusedAt: t.id === todoId ? now : t.focusedAt,
      ...(t.id === previousFocusedId && t.id !== todoId ? { isFocused: false } : {})
    }))

    this.onTodosChange?.(this.todos)
  }

  async completeFocusedTodo(): Promise<{
    completed: Todo | null
    nextFocused: Todo | null
    allCompleted: boolean
  }> {
    if (!this.state.focusedTodoId) {
      return { completed: null, nextFocused: null, allCompleted: false }
    }

    const completedTodo = this.todos.find((t) => t.id === this.state.focusedTodoId)
    if (!completedTodo) {
      return { completed: null, nextFocused: null, allCompleted: false }
    }

    const now = new Date()
    completedTodo.status = 'completed'
    completedTodo.completedAt = now
    completedTodo.updatedAt = now
    completedTodo.isFocused = false

    const nextTodo = this.todos.find((t) => t.id !== completedTodo.id && t.status === 'pending')

    if (nextTodo && this.state.autoTransitionEnabled) {
      nextTodo.status = 'in_progress'
      nextTodo.isFocused = true
      nextTodo.focusedAt = now
      nextTodo.updatedAt = now

      this.transitions.push({
        fromTodoId: completedTodo.id,
        toTodoId: nextTodo.id,
        reason: 'task_completed',
        timestamp: now,
        contextUsageAtTransition: this.state.currentContextUsage
      })

      this.state.focusedTodoId = nextTodo.id
    } else {
      this.state.focusedTodoId = null
    }

    const completed = this.todos.filter((t) => t.status === 'completed').length
    this.state.completedTodos = completed
    this.state.totalTodos = this.todos.length
    this.state.chainProgress = this.todos.length > 0 ? Math.round((completed / this.todos.length) * 100) : 0
    this.state.lastFocusChangeAt = now

    this.onTodosChange?.(this.todos)

    return {
      completed: completedTodo,
      nextFocused: nextTodo ?? null,
      allCompleted: !nextTodo
    }
  }

  syncWithTodos(): void {
    const completed = this.todos.filter((t) => t.status === 'completed').length
    const inProgress = this.todos.find((t) => t.status === 'in_progress')
    const focused = this.todos.find((t) => t.isFocused)

    this.state.totalTodos = this.todos.length
    this.state.completedTodos = completed
    this.state.chainProgress = this.todos.length > 0 ? Math.round((completed / this.todos.length) * 100) : 0
    this.state.focusedTodoId = focused?.id ?? inProgress?.id ?? null
  }

  generateHandoff(): FocusChainHandoff {
    const completed = this.todos.filter((t) => t.status === 'completed')
    const inProgress = this.todos.find((t) => t.status === 'in_progress')
    const pending = this.todos.filter((t) => t.status === 'pending')

    const completedWork =
      completed.length > 0 ? `Completed ${completed.length} tasks:\n${completed.map((t) => `- ${t.content}`).join('\n')}` : 'No tasks completed yet.'

    const currentState = inProgress
      ? `Currently working on: ${inProgress.content}${inProgress.description ? `\nDetails: ${inProgress.description}` : ''}`
      : 'No task currently in progress.'

    const nextSteps =
      pending.length > 0 ? `${pending.length} tasks remaining:\n${pending.map((t) => `- ${t.content}`).join('\n')}` : 'All tasks completed.'

    return {
      completedWork,
      currentState,
      nextSteps,
      contextSnapshot: {
        progress: this.state.chainProgress,
        contextUsage: this.state.currentContextUsage,
        totalTodos: this.state.totalTodos,
        completedTodos: this.state.completedTodos
      }
    }
  }

  getProgressSummary() {
    return {
      total: this.state.totalTodos,
      completed: this.state.completedTodos,
      inProgress: this.state.focusedTodoId ? 1 : 0,
      pending: this.state.totalTodos - this.state.completedTodos - (this.state.focusedTodoId ? 1 : 0),
      progressPercent: this.state.chainProgress,
      focusedTodoId: this.state.focusedTodoId,
      contextUsage: this.state.currentContextUsage
    }
  }

  setAutoTransition(enabled: boolean): void {
    this.state.autoTransitionEnabled = enabled
  }

  shouldSuggestNewTask(): { suggest: boolean; reason?: string } {
    if (this.state.currentContextUsage >= CONTEXT_THRESHOLDS.CRITICAL) {
      return {
        suggest: true,
        reason: `Context usage at ${this.state.currentContextUsage}%. Consider creating a new task to continue with remaining work.`
      }
    }

    if (this.state.chainProgress >= 100) {
      return {
        suggest: false,
        reason: 'All tasks completed.'
      }
    }

    return { suggest: false }
  }

  addTodos(newTodos: Todo[]): void {
    this.todos = [...this.todos, ...newTodos]
    this.syncWithTodos()
    this.onTodosChange?.(this.todos)
  }
}
