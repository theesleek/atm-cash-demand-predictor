import { lazy, Suspense } from 'react';
import { Link, Navigate, Outlet, Route, Routes, useNavigate } from 'react-router-dom';
import { useAuth } from './auth';
import { Navbar, Sidebar } from './components/Navigation';
import { ArrowLeft, ArrowRight, House } from 'lucide-react';
import { LoadingState, PageHeader } from './components/ui';
import HomePage from './pages/HomePage';
import MissionPage from './pages/MissionPage';
import AboutPage from './pages/AboutPage';
import ContactPage from './pages/ContactPage';
import LoginPage from './pages/LoginPage';

const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const AlertsPage = lazy(() => import('./pages/AlertsPage'));
const AlertDetailPage = lazy(async () => {
  const module = await import('./pages/AlertsPage');
  return { default: module.AlertDetailPage };
});
const ATMNetworkPage = lazy(() => import('./pages/ATMNetworkPage'));
const ATMDetailPage = lazy(async () => {
  const module = await import('./pages/ATMNetworkPage');
  return { default: module.ATMDetailPage };
});
const ForecastPage = lazy(() => import('./pages/ForecastPage'));
const ReplenishmentsPage = lazy(() => import('./pages/ReplenishmentsPage'));
const ReplenishmentDetailPage = lazy(() => import('./pages/ReplenishmentDetailPage'));
const ActivityPage = lazy(() => import('./pages/ActivityPage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const UserManagementPage = lazy(() => import('./pages/UserManagementPage'));
const ATMOnboardingPage = lazy(() => import('./pages/ATMOnboardingPage'));
const DataImportPage = lazy(() => import('./pages/DataImportPage'));

const internalPages = [
  { path: 'dashboard', title: 'Dashboard' },
];

function PublicLayout() {
  return <><Navbar /><div className="public-content"><Outlet /></div></>;
}

function InternalLayout() {
  return <div className="internal-layout"><Sidebar /><div className="internal-content"><Outlet /></div></div>;
}

function ProtectedLayout() {
  const { user, checking } = useAuth();
  if (checking) return <LoadingState label="Checking session" />;
  if (!user) return <Navigate to="/login" replace />;
  return <InternalLayout />;
}

function PageScaffold({ title, audience = 'Public' }) {
  return (
    <main className="page-scaffold">
      <PageHeader
        eyebrow={audience === 'Public' ? 'ATM Cash Intelligence' : 'Operations workspace'}
        title={title}
        breadcrumbs={audience === 'Internal' ? [{ label: 'Dashboard', to: '/dashboard' }, { label: title }] : undefined}
      />
    </main>
  );
}

function LoginRoute() {
  const { checking } = useAuth();
  if (checking) return <LoadingState label="Checking session" />;
  return <LoginPage />;
}

function NotFoundPage() {
  const navigate = useNavigate();
  const { user } = useAuth();

  function goBack() {
    const currentIndex = window.history.state?.idx;
    navigate(typeof currentIndex === 'number' && currentIndex > 0 ? -1 : user ? '/dashboard' : '/');
  }

  return (
    <main className="not-found-page">
      <section className="not-found-panel">
        <p className="not-found-code">404 <span>·</span> ROUTE NOT FOUND</p>
        <h1>Page not found.</h1>
        <p className="not-found-copy">That address does not lead to a page in this workspace.</p>
        <nav className="not-found-actions" aria-label="Recovery navigation">
          <button className="button button--secondary" type="button" onClick={goBack}><ArrowLeft size={15} />Back</button>
          <Link className="button button--secondary" to="/"><House size={15} />Home</Link>
          <Link className="button button--primary" to="/dashboard">Dashboard <ArrowRight size={15} /></Link>
        </nav>
      </section>
    </main>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<PublicLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/mission" element={<MissionPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/contact" element={<ContactPage />} />
        <Route path="/login" element={<LoginRoute />} />
      </Route>
      <Route element={<ProtectedLayout />}>
        <Route path="/alerts/:recordId" element={<Suspense fallback={<LoadingState label="Loading alert" />}><AlertDetailPage /></Suspense>} />
        <Route path="/alerts" element={<Suspense fallback={<LoadingState label="Loading alerts" />}><AlertsPage /></Suspense>} />
        <Route path="/replenishments/:recordId" element={<Suspense fallback={<LoadingState label="Loading request" />}><ReplenishmentDetailPage /></Suspense>} />
        <Route path="/replenishments" element={<Suspense fallback={<LoadingState label="Loading replenishments" />}><ReplenishmentsPage /></Suspense>} />
        <Route path="/atms/new" element={<Suspense fallback={<LoadingState label="Loading ATM onboarding" />}><ATMOnboardingPage /></Suspense>} />
        <Route path="/atms/:atmId" element={<Suspense fallback={<LoadingState label="Loading ATM" />}><ATMDetailPage /></Suspense>} />
        <Route path="/atms" element={<Suspense fallback={<LoadingState label="Loading ATM network" />}><ATMNetworkPage /></Suspense>} />
        <Route path="/data-imports" element={<Suspense fallback={<LoadingState label="Loading data import" />}><DataImportPage /></Suspense>} />
        <Route path="/data-imports/:versionId" element={<Suspense fallback={<LoadingState label="Loading dataset" />}><DataImportPage /></Suspense>} />
        <Route path="/forecast" element={<Suspense fallback={<LoadingState label="Loading forecast" />}><ForecastPage /></Suspense>} />
        <Route path="/activity" element={<Suspense fallback={<LoadingState label="Loading audit feed" />}><ActivityPage /></Suspense>} />
        <Route path="/profile" element={<Suspense fallback={<LoadingState label="Loading profile" />}><ProfilePage /></Suspense>} />
        <Route path="/users" element={<Suspense fallback={<LoadingState label="Loading user management" />}><UserManagementPage /></Suspense>} />
        {internalPages.map(({ path, title }) => (
          <Route key={path} path={`/${path}`} element={path === 'dashboard' ? <Suspense fallback={<LoadingState label="Loading dashboard" />}><DashboardPage /></Suspense> : <PageScaffold title={title} audience="Internal" />} />
        ))}
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
