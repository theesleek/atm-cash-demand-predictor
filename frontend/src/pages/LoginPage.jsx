import { useEffect, useState } from 'react';
import { ArrowRight, LockKeyhole, UserRound } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth';
import { Button } from '../components/ui';
import { CashNetworkArtwork } from './HomePage';

export default function LoginPage() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [state, setState] = useState('idle');

  useEffect(() => {
    if (user && state === 'idle') navigate('/dashboard', { replace: true });
  }, [navigate, state, user]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (state === 'loading') return;
    setState('loading');
    try {
      await login(username.trim(), password);
      setState('success');
      window.setTimeout(() => navigate('/dashboard', { replace: true }), 450);
    } catch (error) {
      setState(error.message === 'invalid_credentials' ? 'invalid' : 'error');
    }
  }

  const message = {
    invalid: 'Username or password is incorrect.',
    error: 'Sign in is temporarily unavailable. Please try again.',
    success: 'Signed in. Opening your dashboard…',
  }[state];

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-heading">
        <div className="login-panel__form-side">
          <Link className="login-brand" to="/">
            <span className="brand__mark">A</span>
            <span>ATM Cash Intelligence</span>
          </Link>
          <p className="login-eyebrow">Secure operations access</p>
          <h1 id="login-heading">Welcome back</h1>
          <p className="login-intro">Sign in to continue to your operations workspace.</p>

          <form className="login-form" onSubmit={handleSubmit}>
            <label htmlFor="login-username">Username</label>
            <div className="login-input-wrap">
              <UserRound size={17} aria-hidden="true" />
              <input
                id="login-username"
                name="username"
                autoComplete="username"
                required
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                disabled={state === 'loading'}
              />
            </div>

            <label htmlFor="login-password">Password</label>
            <div className="login-input-wrap">
              <LockKeyhole size={17} aria-hidden="true" />
              <input
                id="login-password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={state === 'loading'}
              />
            </div>

            {message && <p className={`login-message login-message--${state}`} role={state === 'invalid' || state === 'error' ? 'alert' : 'status'}>{message}</p>}

            <Button type="submit" className="login-submit" disabled={state === 'loading'}>
              {state === 'loading' ? <><span className="loading-indicator" />Signing in</> : <>Sign in <ArrowRight size={16} /></>}
            </Button>
          </form>
          <Link className="login-home-link" to="/"><ArrowRight size={14} />Back to Home</Link>
        </div>
        <CashNetworkArtwork className="login-panel__visual" />
      </section>
    </main>
  );
}