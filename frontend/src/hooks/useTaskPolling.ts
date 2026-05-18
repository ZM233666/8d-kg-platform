/** 轮询 extraction run 直至终态（succeeded / failed） */

import { useEffect, useRef } from 'react'
import { taskApi } from '../api'
import type { Task, TaskStatus } from '../types'

const TERMINAL: TaskStatus[] = ['succeeded', 'failed']

export function useTaskPolling(
  runId: string | undefined,
  onUpdate: (task: Task) => void,
  intervalMs = 2000,
) {
  const onUpdateRef = useRef(onUpdate)

  useEffect(() => {
    onUpdateRef.current = onUpdate
  }, [onUpdate])

  useEffect(() => {
    if (!runId) return

    let cancelled = false

    const poll = async () => {
      try {
        const task = await taskApi.getRun(runId)
        if (!cancelled) onUpdateRef.current(task)
        return task.status
      } catch {
        return null
      }
    }

    void poll()

    const timer = setInterval(async () => {
      const status = await poll()
      if (status && TERMINAL.includes(status as TaskStatus)) {
        clearInterval(timer)
      }
    }, intervalMs)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [runId, intervalMs])
}
