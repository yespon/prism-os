/**
 * TodoReadTool — Server-side todo_read tool implementation.
 * Ported from Chaterm's src/main/agent/core/task/todo-tools/todo_read_tool.ts
 *
 * Reads current todos and returns formatted output with focus chain state.
 */

import { TodoWriteTool, type TodoItem } from './todo-write-tool';

// In-memory todo store — keyed by taskId.
// In production, this would be backed by a database.
const todoStore = new Map<string, TodoItem[]>();

export class TodoReadTool {
  /**
   * Execute todo_read — read current todo list for the given task.
   */
  execute(_params: {}, taskId: string): string {
    const todos = todoStore.get(taskId) ?? [];

    if (todos.length === 0) {
      return '当前没有待办任务。如果需要管理复杂任务，可以使用 todo_write 创建一个任务清单。';
    }

    if (todos.length < 3) {
      const list = todos.map((t) => `- ${t.status === 'in_progress' ? '🔄' : t.status === 'completed' ? '✅' : '📋'} ${t.content}`).join('\n');
      return `当前仅有 ${todos.length} 个任务，不构成复杂任务清单。请直接执行。\n${list}`;
    }

    const writeTool = new TodoWriteTool();
    return writeTool.generateOutput(todos);
  }

  /**
   * Get raw todos for a given taskId.
   */
  getTodos(taskId: string): TodoItem[] {
    return todoStore.get(taskId) ?? [];
  }

  /**
   * Set todos for a given taskId.
   */
  setTodos(taskId: string, todos: TodoItem[]): void {
    todoStore.set(taskId, todos);
  }

  /**
   * Clear todos for a taskId.
   */
  clearTodos(taskId: string): void {
    todoStore.delete(taskId);
  }
}

// Singleton instance used by the tools
export const todoReadToolInstance = new TodoReadTool();
export { todoStore };
