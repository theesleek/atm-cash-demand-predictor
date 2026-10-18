import { PageHeader } from '../components/ui';

const architecture = [
  ['Web client', 'React interface for public information and authenticated operations.'],
  ['API and access control', 'FastAPI routes validate requests and apply JWT authentication and role permissions.'],
  ['Application services', 'Forecast, risk, alerts, replenishment, notifications, and audit behavior.'],
  ['Repositories and data', 'SQLAlchemy repositories separate database access from application rules.'],
];

const integrations = [
  ['Telegram', 'Bot alerts and authorized alert acknowledgement.'],
  ['Gmail SMTP', 'Email notification delivery over authenticated SMTP.'],
  ['WebSockets', 'Authenticated real-time events for alert and replenishment updates.'],
];

const capabilities = [
  'ATM demand forecasts and cash-risk assessment',
  'Alert creation, acknowledgement, and resolution',
  'Replenishment requests, review, approval, scheduling, and completion',
  'Telegram and email notifications with delivery status logging',
  'Role-based access and audit records for operational actions',
  'Real-time updates for connected authenticated clients',
];

function DetailRows({ rows }) {
  return (
    <dl className="about-detail-rows">
      {rows.map(([term, detail]) => (
        <div key={term}>
          <dt>{term}</dt>
          <dd>{detail}</dd>
        </div>
      ))}
    </dl>
  );
}

function AboutSection({ number, title, children, className = '' }) {
  return (
    <section className={`about-section ${className}`.trim()}>
      <span className="about-section__number">{number}</span>
      <div className="about-section__body">
        <h2>{title}</h2>
        {children}
      </div>
    </section>
  );
}

export default function AboutPage() {
  return (
    <main className="about-page">
      <PageHeader
        eyebrow="About the project"
        title="ATM Cash Intelligence & Replenishment Platform"
        description="A prototype decision-support platform that combines signed net cash flow forecasting, cash-risk visibility, and replenishment workflows. It is designed to complement existing operational systems, with authorized teams retaining control of decisions and actions."
      />

      <div className="about-sections">
        <AboutSection number="01" title="Project Overview">
          <p>The project helps operations teams interpret signed net cash flow signals and organize the work that follows. Forecasts, alerts, and replenishment status are brought together in one application, rather than replacing a bank’s existing ATM infrastructure.</p>
        </AboutSection>

        <AboutSection number="02" title="Technology">
          <DetailRows rows={[
            ['Backend', 'Python and FastAPI'],
            ['Frontend', 'React and Vite'],
            ['Data access', 'SQLAlchemy'],
            ['Forecast inference', 'Scikit-learn model artifacts'],
          ]} />
        </AboutSection>

        <AboutSection number="03" title="Architecture">
          <p>The application uses a layered service architecture: the React client communicates with FastAPI, application services own business transitions, and repositories isolate database access. Forecasting, authorization, notifications, and audit behavior remain separate responsibilities.</p>
          <DetailRows rows={architecture} />
        </AboutSection>

        <AboutSection number="04" title="Dataset" className="about-dataset-section">
          <p>Historical operations come from Tinkoff-derived ATM competition data and are transformed into daily ATM observations for forecasting.</p>
          <dl className="about-metrics">
            <div><dt>Raw records</dt><dd>1,048,575</dd></div>
            <div><dt>ATMs</dt><dd>20</dd></div>
            <div><dt>Dates</dt><dd>477</dd></div>
            <div><dt>ATM-day records</dt><dd>8,461</dd></div>
            <div><dt>Usable ML records</dt><dd>7,841</dd></div>
          </dl>
        </AboutSection>

        <AboutSection number="05" title="Machine Learning">
          <p>The current forecast uses a 50/50 ensemble of Linear Regression and Random Forest, trained and evaluated with Tinkoff-derived historical data. It forecasts signed net cash flow in unspecified source units, not verified withdrawal demand, and does not make replenishment approvals.</p>
          <div className="about-model-tags" aria-label="Current model components">
            <span>Linear Regression</span><span>50/50 ensemble</span><span>Random Forest</span>
          </div>
        </AboutSection>

        <AboutSection number="06" title="Security">
          <div className="about-term-list">
            <span>JWT authentication</span>
            <span>bcrypt password hashing</span>
            <span>Role-based access control</span>
            <span>Audit logging</span>
          </div>
        </AboutSection>

        <AboutSection number="07" title="Integrations">
          <DetailRows rows={integrations} />
        </AboutSection>

        <AboutSection number="08" title="Current Capabilities">
          <ul className="about-capabilities">
            {capabilities.map((capability) => <li key={capability}>{capability}</li>)}
          </ul>
        </AboutSection>
      </div>
    </main>
  );
}
