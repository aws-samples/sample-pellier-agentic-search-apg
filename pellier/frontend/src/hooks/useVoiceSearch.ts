/**
 * useVoiceSearch — real-time voice-to-text via Amazon Transcribe.
 *
 * Captures mic audio via Web Audio API, streams PCM chunks to the
 * backend's /ws/transcribe WebSocket, and relays interim + final
 * transcript events back to the caller.
 *
 * Usage:
 *   const { isListening, startListening, stopListening } = useVoiceSearch({
 *     onInterimTranscript: (text) => setSearchValue(text),
 *     onFinalTranscript: (text) => openDrawerWithQuery(text),
 *   })
 */
import { useCallback, useRef, useState } from 'react'

interface UseVoiceSearchOptions {
  /** Called with interim (partial) transcripts as the user speaks. */
  onInterimTranscript?: (text: string) => void
  /** Called with the final transcript when the user stops speaking. */
  onFinalTranscript?: (text: string) => void
  /** Called on error (mic denied, WebSocket fail, etc.). */
  onError?: (error: string) => void
}

interface UseVoiceSearchReturn {
  isListening: boolean
  startListening: () => void
  stopListening: () => void
  error: string | null
}

// PCM audio config matching the backend's expectations
const SAMPLE_RATE = 16000
const BUFFER_SIZE = 4096

// WebSocket URL — same host as the page, ws:// or wss://
function getWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  // In dev, Vite serves on 5173 but backend is on 8000
  const host = window.location.hostname
  const port = import.meta.env.DEV ? '8000' : window.location.port
  return `${proto}://${host}:${port}/ws/transcribe`
}

export function useVoiceSearch(options: UseVoiceSearchOptions = {}): UseVoiceSearchReturn {
  const { onInterimTranscript, onFinalTranscript, onError } = options
  const [isListening, setIsListening] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  // Track the latest final transcript to auto-fire on stop
  const lastFinalRef = useRef<string>('')

  const stopListening = useCallback(() => {
    // Stop audio capture
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }
    if (contextRef.current) {
      contextRef.current.close().catch(() => {})
      contextRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    // Close WebSocket
    if (wsRef.current) {
      try {
        wsRef.current.send('stop')
      } catch { /* ignore */ }
      try {
        wsRef.current.close()
      } catch { /* ignore */ }
      wsRef.current = null
    }
    setIsListening(false)
  }, [])

  const startListening = useCallback(async () => {
    setError(null)
    lastFinalRef.current = ''

    // 1. Request mic permission
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
    } catch (err) {
      const msg = 'Microphone access denied. Please allow mic permission and try again.'
      setError(msg)
      onError?.(msg)
      return
    }
    streamRef.current = stream

    // 2. Open WebSocket to backend
    let ws: WebSocket
    try {
      ws = new WebSocket(getWsUrl())
      ws.binaryType = 'arraybuffer'
    } catch (err) {
      const msg = 'Could not connect to voice service.'
      setError(msg)
      onError?.(msg)
      stream.getTracks().forEach(t => t.stop())
      return
    }
    wsRef.current = ws

    // 3. Handle transcript events from backend
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'interim') {
          onInterimTranscript?.(data.text)
        } else if (data.type === 'final') {
          lastFinalRef.current = data.text
          onFinalTranscript?.(data.text)
        } else if (data.type === 'error') {
          setError(data.text)
          onError?.(data.text)
          stopListening()
        } else if (data.type === 'done') {
          stopListening()
        }
      } catch { /* ignore parse errors */ }
    }

    ws.onerror = () => {
      const msg = 'Voice service connection error.'
      setError(msg)
      onError?.(msg)
      stopListening()
    }

    ws.onclose = () => {
      setIsListening(false)
    }

    // 4. Wait for WebSocket to open, then start audio capture
    ws.onopen = () => {
      setIsListening(true)

      // Create AudioContext at the target sample rate
      const audioContext = new AudioContext({ sampleRate: SAMPLE_RATE })
      contextRef.current = audioContext

      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(BUFFER_SIZE, 1, 1)
      processorRef.current = processor

      processor.onaudioprocess = (e) => {
        if (ws.readyState !== WebSocket.OPEN) return
        const float32 = e.inputBuffer.getChannelData(0)
        // Convert float32 → int16 PCM (what Transcribe expects)
        const int16 = new Int16Array(float32.length)
        for (let i = 0; i < float32.length; i++) {
          const s = Math.max(-1, Math.min(1, float32[i]))
          int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
        }
        ws.send(int16.buffer)
      }

      source.connect(processor)
      processor.connect(audioContext.destination)
    }

    // Auto-stop after 15 seconds to prevent runaway sessions
    setTimeout(() => {
      if (wsRef.current) {
        stopListening()
      }
    }, 15000)
  }, [onInterimTranscript, onFinalTranscript, onError, stopListening])

  return { isListening, startListening, stopListening, error }
}
