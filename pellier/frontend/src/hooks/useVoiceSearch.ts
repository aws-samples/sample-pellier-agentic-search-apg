/**
 * useVoiceSearch — real-time voice-to-text via Amazon Transcribe.
 *
 * Captures mic audio via Web Audio API, streams PCM chunks to the
 * backend's /ws/transcribe WebSocket, and relays interim + final
 * transcript events back to the caller.
 *
 * The WebSocket URL is same-origin under `import.meta.env.BASE_URL` so
 * Workshop Studio (CloudFront path proxy) can upgrade the connection.
 * If the mic never starts in an embedded IDE frame, the host page may
 * need `allow="microphone"` on the iframe (AWS controls that).
 *
 * Usage:
 *   const { isListening, startListening, stopListening } = useVoiceSearch({
 *     onInterimTranscript: (text) => setSearchValue(text),
 *     onFinalTranscript: (text) => openDrawerWithQuery(text),
 *   })
 */
import { useCallback, useRef, useState } from 'react'
import { getTranscribeWebSocketUrl } from '../utils/transcribeWsUrl'

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

// Output PCM config matching the backend (16 kHz mono int16).
const OUTPUT_SAMPLE_RATE = 16000
const BUFFER_SIZE = 4096

/** Float32 mono → int16 PCM at OUTPUT_SAMPLE_RATE (linear resample if input rate differs). */
function float32To16kPcmMono(input: Float32Array, inputSampleRate: number): Int16Array {
  const toInt16 = (sample: number) => {
    const s = Math.max(-1, Math.min(1, sample))
    return s < 0 ? s * 0x8000 : s * 0x7fff
  }

  if (input.length === 0) {
    return new Int16Array(0)
  }

  if (Math.abs(inputSampleRate - OUTPUT_SAMPLE_RATE) < 1) {
    const int16 = new Int16Array(input.length)
    for (let i = 0; i < input.length; i++) {
      int16[i] = toInt16(input[i]!)
    }
    return int16
  }

  const outLen = Math.max(1, Math.round((input.length * OUTPUT_SAMPLE_RATE) / inputSampleRate))
  const int16 = new Int16Array(outLen)
  for (let i = 0; i < outLen; i++) {
    const src = ((i + 0.5) * inputSampleRate) / OUTPUT_SAMPLE_RATE - 0.5
    const i0 = Math.max(0, Math.min(input.length - 1, Math.floor(src)))
    const i1 = Math.max(0, Math.min(input.length - 1, i0 + 1))
    const t = src - Math.floor(src)
    const s = (1 - t) * input[i0]! + t * input[i1]!
    int16[i] = toInt16(s)
  }
  return int16
}

export function useVoiceSearch(options: UseVoiceSearchOptions = {}): UseVoiceSearchReturn {
  const { onInterimTranscript, onFinalTranscript, onError } = options
  const [isListening, setIsListening] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const gainRef = useRef<GainNode | null>(null)
  const autoStopRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Track the latest final transcript to auto-fire on stop
  const lastFinalRef = useRef<string>('')

  const stopListening = useCallback(() => {
    if (autoStopRef.current) {
      clearTimeout(autoStopRef.current)
      autoStopRef.current = null
    }
    // Stop audio capture
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }
    if (gainRef.current) {
      gainRef.current.disconnect()
      gainRef.current = null
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
          sampleRate: OUTPUT_SAMPLE_RATE,
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

    // 2. AudioContext must be created and resumed while still in the user-gesture
    //    chain (mic click). If we wait until WebSocket `onopen`, Chrome often leaves
    //    the context suspended and ScriptProcessor never fires — no audio reaches
    //    Transcribe, so the search bar stays empty.
    let audioContext: AudioContext
    try {
      audioContext = new AudioContext()
      if (audioContext.state === 'suspended') {
        await audioContext.resume()
      }
    } catch (err) {
      const msg = 'Could not start audio capture. Try again after allowing the microphone.'
      setError(msg)
      onError?.(msg)
      stream.getTracks().forEach(t => t.stop())
      streamRef.current = null
      return
    }
    contextRef.current = audioContext

    // 3. Open WebSocket to backend
    let ws: WebSocket
    try {
      ws = new WebSocket(getTranscribeWebSocketUrl())
      ws.binaryType = 'arraybuffer'
    } catch (err) {
      const msg = 'Could not connect to voice service.'
      setError(msg)
      onError?.(msg)
      stream.getTracks().forEach(t => t.stop())
      streamRef.current = null
      await audioContext.close().catch(() => {})
      contextRef.current = null
      return
    }
    wsRef.current = ws

    // 4. Handle transcript events from backend
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

    // 5. Wait for WebSocket to open, then wire the graph (context already running).
    ws.onopen = () => {
      if (wsRef.current !== ws || contextRef.current !== audioContext) {
        return
      }
      setIsListening(true)

      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(BUFFER_SIZE, 1, 1)
      processorRef.current = processor

      const inputRate = audioContext.sampleRate
      processor.onaudioprocess = (e) => {
        if (ws.readyState !== WebSocket.OPEN) return
        const float32 = e.inputBuffer.getChannelData(0)
        const int16 = float32To16kPcmMono(float32, inputRate)
        if (int16.byteLength > 0) {
          ws.send(int16.buffer)
        }
      }

      const mute = audioContext.createGain()
      mute.gain.value = 0
      gainRef.current = mute
      source.connect(processor)
      processor.connect(mute)
      mute.connect(audioContext.destination)
    }

    // Auto-stop after 15 seconds to prevent runaway sessions
    if (autoStopRef.current) {
      clearTimeout(autoStopRef.current)
    }
    autoStopRef.current = setTimeout(() => {
      autoStopRef.current = null
      if (wsRef.current) {
        stopListening()
      }
    }, 15000)
  }, [onInterimTranscript, onFinalTranscript, onError, stopListening])

  return { isListening, startListening, stopListening, error }
}
