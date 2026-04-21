import { useCallback, useEffect, useRef, useState } from "react"
import type { WsMessage } from "@/lib/types"

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>(null)
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let cancelled = false

    const connect = () => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws`)

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!cancelled) {
          reconnectTimerRef.current = setTimeout(connect, 3000)
        }
      }
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WsMessage
          setLastMessage(msg)
        } catch {
          // ignore parse errors
        }
      }

      wsRef.current = ws
    }

    connect()
    return () => {
      cancelled = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
      wsRef.current?.close()
    }
  }, [])

  const send = useCallback((msg: WsMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  return { lastMessage, connected, send }
}
