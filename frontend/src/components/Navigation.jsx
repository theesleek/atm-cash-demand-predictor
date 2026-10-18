import { useEffect, useState } from 'react';
import { Activity, Bell, ChartNoAxesCombined, ChevronRight, CircleUserRound, Database, Home as HomeIcon, House, Landmark, LogOut, Menu, Radio, X } from 'lucide-react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth';
import { Button } from './ui';

const publicLinks = [
  { label: 'Home', to: '/' },
  { label: 'Mission', to: '/mission' },
  { label: 'About', to: '/about' },
  { label: 'Contact', to: '/contact' },
];

const internalLinks = [
  { label: 'Dashboard', to: '/dashboard', icon: House },
  { label: 'Home', to: '/', icon: HomeIcon },
  { label: 'ATMs', to: '/atms', icon: Landmark },
  { label: 'Data Ingestion', to: '/data-imports', icon: Database },
  { label: 'Forecast', to: '/forecast', icon: ChartNoAxesCombined },
  { label: 'Alerts', to: '/alerts', icon: Bell },
  { label: 'Replenishment', to: '/replenishments', icon: Radio },
  { label: 'Activity', to: '/activity', icon: Activity },
  { label: 'Profile', to: '/profile', icon: CircleUserRound },
];

export function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { user } = useAuth();
  return (
    <header className="public-nav">
      <Link className="brand" to="/" onClick={() => setMenuOpen(false)}>
        <span className="brand__mark">A</span>
        <span>ATM Cash Intelligence</span>
      </Link>
      <Button
        className="public-nav__toggle"
        variant="icon"
        aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen((open) => !open)}
      >
        {menuOpen ? <X size={20} /> : <Menu size={20} />}
      </Button>
      <nav className={`public-nav__links ${menuOpen ? 'is-open' : ''}`} aria-label="Public navigation">
        {publicLinks.map((link) => (
          <NavLink key={link.to} to={link.to} end={link.to === '/'} onClick={() => setMenuOpen(false)}>
            {link.label}
          </NavLink>
        ))}
        <Link className="public-nav__login" to={user ? '/dashboard' : '/login'} onClick={() => setMenuOpen(false)}>
          {user ? 'Dashboard' : 'Login'} <ChevronRight size={15} />
        </Link>
      </nav>
    </header>
  );
}

export function Sidebar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(() => window.matchMedia('(max-width: 760px)').matches);
  const { logout, user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const query = window.matchMedia('(max-width: 760px)');
    const update = (event) => setIsMobile(event.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  const sidebarClosed = isMobile && !menuOpen;

  async function onLogout() {
    await logout();
    navigate('/login');
  }

  return (
    <>
      <div className="internal-mobile-bar">
        <Button variant="icon" aria-label={menuOpen ? 'Close sidebar' : 'Open sidebar'} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </Button>
        <Link className="brand" to="/dashboard"><span className="brand__mark">A</span>ATM Cash Intelligence</Link>
      </div>
      {menuOpen && <button className="sidebar-scrim" aria-label="Close sidebar" onClick={() => setMenuOpen(false)} />}
      <aside className={`sidebar ${menuOpen ? 'sidebar--open' : ''}`} aria-hidden={sidebarClosed || undefined} inert={sidebarClosed}>
        <Link className="brand sidebar__brand" to="/dashboard">
          <span className="brand__mark">A</span>
          <span>ATM Cash Intelligence</span>
        </Link>
        <p className="sidebar__label">Workspace</p>
        <nav className="sidebar__links" aria-label="Authenticated navigation">
          {internalLinks.map(({ label, to, icon: Icon }) => (
            <NavLink key={to} to={to} onClick={() => setMenuOpen(false)}>
              <Icon size={17} strokeWidth={1.8} />{label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__footer">
          {user && <div className="sidebar__user"><span className="user-avatar">{user.username.slice(0, 1).toUpperCase()}</span><span>{user.username}</span></div>}
          <Button variant="sidebar" onClick={onLogout}><LogOut size={17} />Logout</Button>
        </div>
      </aside>
    </>
  );
}
