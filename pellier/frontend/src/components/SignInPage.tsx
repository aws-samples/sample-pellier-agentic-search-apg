import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Eye, EyeOff, LoaderCircle } from 'lucide-react'
import ResponsiveImage from './ResponsiveImage'
import { asset } from '../utils/assetPath'
import { passwordAuth, PasswordAuthError, safeSignInReturn } from '../services/passwordAuth'
import '../styles/pellier-signin.css'

const ERROR_COPY: Record<string, string> = {
  invalid_credentials: 'That username and password did not match. Check both and try again.',
  invalid_state: 'Your sign-in session expired. Please try again.',
  try_later: 'Too many attempts in a short time. Wait a moment before trying again.',
  password_reset_required: 'Please reset your password before signing in.',
  invalid_reset_code: 'That code is incorrect or has expired. Check it or request a new code.',
  password_requirements: 'Choose a stronger password that meets your account’s requirements and has not been used before.',
  password_signin_unavailable: 'Password sign-in is unavailable here. You can continue with another sign-in method.',
  verification_required: 'Your account needs an additional verification step. Continue securely to finish signing in.',
}

type Mode = 'sign-in' | 'forgot' | 'reset'

export default function SignInPage() {
  const params = new URLSearchParams(window.location.search)
  const returnTo = safeSignInReturn(params.get('returnTo'), asset('/'))
  const operator = /\/operator(?:\/|\?|$)/.test(returnTo)
  const [mode, setMode] = useState<Mode>('sign-in')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [code, setCode] = useState('')
  const [visible, setVisible] = useState(false)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const controller = useRef<AbortController | null>(null)
  const busy = useRef(false)
  const heading = useRef<HTMLHeadingElement | null>(null)
  const mounted = useRef(false)
  const hosted = `/api/auth/signin?provider=email&returnTo=${encodeURIComponent(returnTo)}`

  useEffect(() => {
    const previous = document.title
    document.title = operator ? 'Sign in · Pellier Operator' : 'Sign in · Pellier'
    mounted.current = true
    return () => { mounted.current = false; controller.current?.abort(); document.title = previous }
  }, [operator])
  useEffect(() => { heading.current?.focus({ preventScroll: true }) }, [mode])

  const changeMode = (next: Mode) => {
    if (busy.current) return
    setMode(next); setPassword(''); setConfirmation(''); setCode('')
    setError(null); setNotice(null); setVisible(false)
  }
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (busy.current) return
    if (mode === 'reset' && password !== confirmation) {
      setError('The new passwords do not match. Please check both fields.')
      return
    }
    busy.current = true; setWorking(true); setError(null); setNotice(null)
    const request = new AbortController()
    controller.current = request
    const timeout = window.setTimeout(() => request.abort(), 30_000)
    try {
      const result = await passwordAuth(mode, { username: username.trim(), password, code, returnTo }, request.signal)
      if (!mounted.current) return
      if (result.status === 'signed_in') {
        setPassword('')
        window.location.assign(safeSignInReturn(result.returnTo ?? returnTo, asset('/')))
      } else if (result.status === 'verification_required') {
        setPassword(''); setError(ERROR_COPY.verification_required)
      } else if (result.status === 'recovery_requested') {
        setMode('reset'); setPassword(''); setConfirmation('')
        setNotice('If recovery is enabled for this account, a code is on its way to your registered email or phone. If none arrives, contact your workshop host.')
      } else if (result.status === 'password_reset') {
        setMode('sign-in'); setPassword(''); setConfirmation(''); setCode('')
        setNotice('Your password has been updated. Sign in with your new password.')
      } else {
        throw new PasswordAuthError('auth_unavailable')
      }
    } catch (reason) {
      if (mounted.current) setError(reason instanceof PasswordAuthError
        ? ERROR_COPY[reason.message] || 'Sign-in is temporarily unavailable. Please try again.'
        : 'We could not confirm the response. Check your connection and try again.')
    } finally {
      window.clearTimeout(timeout)
      busy.current = false
      if (mounted.current) setWorking(false)
    }
  }
  const title = mode === 'forgot' ? 'Reset your password.' : mode === 'reset' ? 'A fresh start.' : operator ? 'Welcome to the desk.' : 'Welcome to Pellier.'
  const description = mode === 'forgot' ? 'Enter your username to request a recovery code.' : mode === 'reset' ? 'Enter your recovery code and choose a new password.' : operator ? 'Sign in to your operator account to continue.' : 'Sign in for a more personal shopping experience.'

  return (
    <main className="pellier-signin" data-testid="pellier-signin">
      <div className="pellier-signin-shell">
        <div className="pellier-signin-form-panel">
          <a href={asset('/')} className="pellier-signin-wordmark" aria-label="Pellier home">
            pellier<span aria-hidden="true">.</span>
          </a>
          <div className="pellier-signin-content">
            <h1 ref={heading} tabIndex={-1}>{title}</h1>
            <p className="pellier-signin-description">{description}</p>
            <form onSubmit={(event) => void submit(event)} aria-busy={working}>
              <div className="pellier-signin-field">
                <label htmlFor="pellier-username">Username</label>
                <input id="pellier-username" name="username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" autoCapitalize="none" spellCheck={false} required maxLength={128} readOnly={working || mode === 'reset'} />
              </div>
              {mode === 'reset' ? <div className="pellier-signin-field"><label htmlFor="pellier-recovery-code">Recovery code</label><input id="pellier-recovery-code" name="code" value={code} onChange={(event) => setCode(event.target.value)} autoComplete="one-time-code" inputMode="numeric" required maxLength={64} readOnly={working} /></div> : null}
              {mode !== 'forgot' ? (
                <div className="pellier-signin-field">
                  <div className="pellier-signin-label-row"><label htmlFor="pellier-password">{mode === 'reset' ? 'New password' : 'Password'}</label>{mode === 'sign-in' ? <button type="button" onClick={() => changeMode('forgot')} disabled={working}>Forgot password?</button> : null}</div>
                  <div className="pellier-signin-password"><input id="pellier-password" name="password" type={visible ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === 'reset' ? 'new-password' : 'current-password'} required maxLength={256} readOnly={working} /><button type="button" onClick={() => setVisible((value) => !value)} aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible}>{visible ? <EyeOff size={19} /> : <Eye size={19} />}</button></div>
                </div>
              ) : null}
              {mode === 'reset' ? <div className="pellier-signin-field"><label htmlFor="pellier-password-confirmation">Confirm new password</label><input id="pellier-password-confirmation" name="passwordConfirmation" type={visible ? 'text' : 'password'} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" required maxLength={256} readOnly={working} /></div> : null}
              {error ? <p className="pellier-signin-feedback" data-tone="error" role="alert">{error}</p> : null}
              {notice ? <p className="pellier-signin-feedback" role="status">{notice}</p> : null}
              <button className="pellier-signin-submit" type="submit" disabled={working}>{working ? <><LoaderCircle size={18} className="spin" aria-hidden="true" />{mode === 'sign-in' ? 'Signing in…' : 'Please wait…'}</> : mode === 'sign-in' ? 'Sign in' : mode === 'forgot' ? 'Send recovery code' : 'Update password'}</button>
            </form>
            {mode !== 'sign-in' ? <button type="button" className="pellier-signin-back" disabled={working} onClick={() => changeMode('sign-in')}>Back to sign in</button> : <a className="pellier-signin-alternative" href={hosted}>{error === ERROR_COPY.verification_required ? 'Continue secure verification' : 'Use another sign-in method'}</a>}
            {mode === 'reset' ? <button type="button" className="pellier-signin-alternative" disabled={working} onClick={() => changeMode('forgot')}>Request a new code</button> : null}
          </div>
          <a href={asset('/')} className="pellier-signin-home">Back to Pellier</a>
        </div>
        <div className="pellier-signin-portrait" aria-hidden="true"><ResponsiveImage src="/products/hero-fresh-2.png" widths={[960, 1600]} sizes="(min-width: 900px) 50vw, 1px" alt="" /><div><span className="pellier-signin-image-wordmark">pellier<span>.</span></span><p>Considered pieces.<br />Personal attention.</p></div></div>
      </div>
    </main>
  )
}
