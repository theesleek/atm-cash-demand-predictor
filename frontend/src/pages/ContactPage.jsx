import { ArrowLeft, ArrowUpRight, Mail } from 'lucide-react';
import { Link } from 'react-router-dom';
import { PageHeader } from '../components/ui';

const discussionTopics = [
  'Project discussion',
  'Collaboration',
  'Feedback',
  'Technical discussion',
];

export default function ContactPage() {
  return (
    <main className="contact-page">
      <PageHeader
        eyebrow="Contact"
        title="Let’s Connect"
        description="Reach out to the project team for a conversation about the platform or its development."
      />

      <section className="contact-topics" aria-labelledby="contact-topics-title">
        <h2 id="contact-topics-title">Open to</h2>
        <ul>
          {discussionTopics.map((topic) => <li key={topic}>{topic}</li>)}
        </ul>
      </section>

      <section className="contact-details" aria-label="Contact details">
        <a href="mailto:atm.cash.intelligence@gmail.com">
          <span className="contact-details__icon"><Mail size={18} /></span>
          <span><small>Email</small><strong>atm.cash.intelligence@gmail.com</strong></span>
          <ArrowUpRight className="contact-details__external" size={17} aria-hidden="true" />
        </a>
        <a href="https://www.linkedin.com/in/rishi-srivastava-869672329/" target="_blank" rel="noreferrer">
          <span className="contact-details__icon contact-details__icon--linkedin">in</span>
          <span><small>LinkedIn</small><strong>Rishi Srivastava</strong></span>
          <ArrowUpRight className="contact-details__external" size={17} aria-hidden="true" />
        </a>
      </section>

      <Link className="contact-back" to="/"><ArrowLeft size={16} />Back to Home</Link>
    </main>
  );
}