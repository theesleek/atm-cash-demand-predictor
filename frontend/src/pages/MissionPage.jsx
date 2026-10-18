import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { PageHeader } from '../components/ui';

const workflow = [
  'Historical Data',
  'Forecast',
  'Risk Assessment',
  'Alert',
  'Replenishment Recommendation',
  'Authorized Action',
];

function EditorialSection({ number, title, children, className = '' }) {
  return (
    <section className={`mission-section ${className}`.trim()}>
      <span className="mission-section__number">{number}</span>
      <div className="mission-section__content">
        <h2>{title}</h2>
        {children}
      </div>
    </section>
  );
}

export default function MissionPage() {
  return (
    <main className="mission-page">
      <PageHeader
        eyebrow="Purpose and principles"
        title="Our mission"
        description="Help ATM operations teams make timely, informed cash decisions with greater confidence."
      />

      <div className="mission-sections">
        <EditorialSection number="01" title="Mission">
          <p>We aim to make cash availability easier to anticipate and manage. By bringing signed net cash flow forecasts, risk signals, and replenishment decisions into one view, the platform helps teams focus attention where it can matter most.</p>
        </EditorialSection>

        <EditorialSection number="02" title="The Problem">
          <p>ATM cash flows vary across locations and over time. When information is spread across reports and operational tools, it can take extra effort to identify which ATMs may need attention and when a response should be considered.</p>
        </EditorialSection>

        <EditorialSection number="03" title="Our Approach">
          <p>ATM Cash Intelligence acts as an intelligence and decision-support layer. It turns historical activity into forecasts, highlights changing risk, and provides context for operational choices.</p>
          <p>It is designed to complement existing ATM and banking systems, not replace them. Teams remain in control of review, approval, and action through their established processes.</p>
        </EditorialSection>

        <EditorialSection number="04" title="What the Platform Provides">
          <ul className="mission-provides">
            <li><span>Signed net cash flow forecasts</span><span>Source-unit flow signals to support planning.</span></li>
            <li><span>Risk visibility</span><span>Signals that help prioritize operational review.</span></li>
            <li><span>Replenishment guidance</span><span>Recommendations that can inform a request.</span></li>
            <li><span>Decision traceability</span><span>A record of key changes and actions.</span></li>
          </ul>
        </EditorialSection>

        <EditorialSection number="05" title="Operational Workflow" className="mission-workflow-section">
          <p>Information moves from observation to action, with authorized people making operational decisions.</p>
          <ol className="mission-workflow">
            {workflow.map((step, index) => (
              <li key={step}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{step}</strong>
                {index < workflow.length - 1 && <ArrowRight size={16} aria-hidden="true" />}
              </li>
            ))}
          </ol>
        </EditorialSection>
      </div>

      <section className="mission-cta">
        <div>
          <p className="eyebrow">Continue to operations</p>
          <h2>Explore the Dashboard</h2>
        </div>
        <Link className="button button--primary" to="/dashboard">Explore Dashboard <ArrowRight size={16} /></Link>
      </section>
    </main>
  );
}
