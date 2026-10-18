import { useEffect, useRef } from 'react';
import { Activity, ArrowDown, ArrowRight, BarChart3, Boxes, FileCheck2, Mail, RadioTower } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth';
import { Button } from '../components/ui';

const capabilities = [
  {
    number: '01',
    title: 'Predictive Cash Forecasting',
    description: 'Interpret signed net cash flow from historical ATM activity and plan replenishment with more lead time.',
    icon: BarChart3,
  },
  {
    number: '02',
    title: 'Real-Time Risk Monitoring',
    description: 'Surface low-cash risk early and keep operational teams aware as conditions change.',
    icon: RadioTower,
  },
  {
    number: '03',
    title: 'Intelligent Replenishment',
    description: 'Turn forecast recommendations into requests that can be reviewed and managed by operations.',
    icon: Boxes,
  },
  {
    number: '04',
    title: 'Auditable Operations',
    description: 'Keep decisions and status changes traceable across the replenishment lifecycle.',
    icon: FileCheck2,
  },
];

const workflow = [
  'Historical ATM Data',
  'Forecast',
  'Risk Detection',
  'Replenishment',
  'Operational Action',
];

export function CashNetworkArtwork({ className = '' }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;

    function draw() {
      const bounds = canvas.getBoundingClientRect();
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      const context = canvas.getContext('2d');
      canvas.width = Math.round(bounds.width * pixelRatio);
      canvas.height = Math.round(bounds.height * pixelRatio);
      context.scale(pixelRatio, pixelRatio);
      const width = bounds.width;
      const height = bounds.height;

      context.fillStyle = '#111a1f';
      context.fillRect(0, 0, width, height);
      context.strokeStyle = 'rgba(113, 156, 177, 0.09)';
      context.lineWidth = 1;
      for (let x = 22; x < width; x += 34) {
        context.beginPath();
        context.moveTo(x, 0);
        context.lineTo(x, height);
        context.stroke();
      }
      for (let y = 24; y < height; y += 34) {
        context.beginPath();
        context.moveTo(0, y);
        context.lineTo(width, y);
        context.stroke();
      }

      const machineX = width * 0.47;
      const machineY = height * 0.13;
      const machineWidth = width * 0.34;
      const machineHeight = height * 0.73;
      const sideWidth = width * 0.055;

      context.fillStyle = '#202d34';
      context.beginPath();
      context.moveTo(machineX, machineY);
      context.lineTo(machineX + machineWidth, machineY);
      context.lineTo(machineX + machineWidth + sideWidth, machineY + height * 0.04);
      context.lineTo(machineX + machineWidth + sideWidth, machineY + machineHeight - height * 0.03);
      context.lineTo(machineX, machineY + machineHeight);
      context.closePath();
      context.fill();
      context.fillStyle = '#26363e';
      context.fillRect(machineX, machineY, machineWidth, machineHeight);
      context.strokeStyle = '#48616d';
      context.strokeRect(machineX, machineY, machineWidth, machineHeight);
      context.fillStyle = '#162126';
      context.fillRect(machineX + 11, machineY + 11, machineWidth - 22, machineHeight - 22);

      const screenX = machineX + machineWidth * 0.14;
      const screenY = machineY + machineHeight * 0.12;
      const screenWidth = machineWidth * 0.72;
      const screenHeight = machineHeight * 0.37;
      context.fillStyle = '#0c151a';
      context.fillRect(screenX, screenY, screenWidth, screenHeight);
      context.strokeStyle = '#365866';
      context.strokeRect(screenX, screenY, screenWidth, screenHeight);
      context.fillStyle = '#93b7c5';
      context.font = `500 ${Math.max(8, width * 0.018)}px monospace`;
      context.fillText('CASH FLOW', screenX + 10, screenY + 17);

      const graphPoints = [
        [0.08, 0.76], [0.25, 0.62], [0.4, 0.68], [0.55, 0.4], [0.71, 0.5], [0.9, 0.22],
      ];
      context.beginPath();
      graphPoints.forEach(([pointX, pointY], index) => {
        const x = screenX + pointX * screenWidth;
        const y = screenY + 27 + pointY * (screenHeight - 38);
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      context.strokeStyle = '#59b5e3';
      context.lineWidth = 2;
      context.stroke();
      graphPoints.forEach(([pointX, pointY]) => {
        context.beginPath();
        context.arc(screenX + pointX * screenWidth, screenY + 27 + pointY * (screenHeight - 38), 2.5, 0, Math.PI * 2);
        context.fillStyle = '#9fe3ff';
        context.fill();
      });

      const keypadX = machineX + machineWidth * 0.57;
      const keypadY = machineY + machineHeight * 0.58;
      context.fillStyle = '#34444b';
      context.fillRect(keypadX, keypadY, machineWidth * 0.28, machineHeight * 0.17);
      for (let row = 0; row < 3; row += 1) {
        for (let column = 0; column < 3; column += 1) {
          context.fillStyle = '#9aaab0';
          context.fillRect(keypadX + 7 + column * 11, keypadY + 8 + row * 10, 5, 4);
        }
      }
      context.fillStyle = '#10171b';
      context.fillRect(machineX + machineWidth * 0.17, machineY + machineHeight * 0.79, machineWidth * 0.66, 8);
      context.fillStyle = '#52a9d4';
      context.fillRect(machineX + machineWidth * 0.19, machineY + machineHeight * 0.79, machineWidth * 0.62, 2);

      context.strokeStyle = 'rgba(101, 185, 236, 0.4)';
      context.lineWidth = 1.2;
      const connections = [
        [[width * 0.08, height * 0.25], [width * 0.31, height * 0.25], [machineX, height * 0.39]],
        [[width * 0.1, height * 0.72], [width * 0.31, height * 0.72], [machineX, height * 0.66]],
        [[machineX + machineWidth + sideWidth, height * 0.35], [width * 0.91, height * 0.35]],
      ];
      connections.forEach((path) => {
        context.beginPath();
        path.forEach(([pointX, pointY], index) => {
          if (index === 0) context.moveTo(pointX, pointY);
          else context.lineTo(pointX, pointY);
        });
        context.stroke();
        path.forEach(([pointX, pointY]) => {
          context.beginPath();
          context.arc(pointX, pointY, 3, 0, Math.PI * 2);
          context.fillStyle = '#80d4ff';
          context.fill();
        });
      });

      context.fillStyle = '#8fa5ae';
      context.font = `500 ${Math.max(8, width * 0.017)}px monospace`;
      context.fillText('DEMAND SIGNAL', width * 0.07, height * 0.2);
      context.fillText('NETWORK STATUS', width * 0.07, height * 0.66);
      context.fillText('REPLENISHMENT', width * 0.74, height * 0.42);
      context.fillStyle = '#48b47b';
      context.beginPath();
      context.arc(width * 0.77, height * 0.46, 3, 0, Math.PI * 2);
      context.fill();
    }

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  return (
    <div className={`home-artwork ${className}`.trim()}>
      <canvas ref={canvasRef} role="img" aria-label="Original illustration of an ATM connected to cash-flow forecasting and replenishment signals" />
      <div className="home-artwork__caption"><Activity size={15} /> OPERATIONS SIGNAL / 01</div>
    </div>
  );
}

function HomePage() {
  const { user } = useAuth();
  const startPath = user ? '/dashboard' : '/login';

  return (
    <>
      <section className="home-hero">
        <div className="home-hero__copy">
          <p className="home-eyebrow"><span /> PREDICT <i /> MONITOR <i /> OPTIMIZE</p>
          <h1>Smarter ATM Operations <span>for a Reliable Tomorrow</span></h1>
          <p className="home-hero__supporting">
            An intelligent platform for forecasting signed ATM net cash flow, monitoring operational risk, and supporting timely replenishment decisions.
          </p>
          <div className="home-hero__actions">
            <Link className="button button--primary" to={startPath}>Get Started <ArrowRight size={16} /></Link>
            <a className="button button--secondary" href="#capabilities">Explore Platform <ArrowDown size={15} /></a>
          </div>
          <p className="home-hero__note">Operational clarity, from forecast to action.</p>
        </div>
        <CashNetworkArtwork />
      </section>

      <section className="home-section home-capabilities" id="capabilities">
        <div className="home-section__heading">
          <p className="home-eyebrow"><span /> PLATFORM CAPABILITIES</p>
          <h2>Make every cash decision more deliberate.</h2>
        </div>
        <div className="capability-grid">
          {capabilities.map(({ number, title, description, icon: Icon }) => (
            <article className="capability-item" key={title}>
              <div className="capability-item__top"><span>{number}</span><Icon size={19} strokeWidth={1.7} /></div>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="home-section workflow-section">
        <div className="home-section__heading">
          <p className="home-eyebrow"><span /> FROM SIGNAL TO SERVICE</p>
          <h2>A clear path from data to action.</h2>
        </div>
        <ol className="workflow-list">
          {workflow.map((step, index) => (
            <li key={step}>
              <span className="workflow-list__index">0{index + 1}</span>
              <span>{step}</span>
              {index < workflow.length - 1 && <ArrowRight className="workflow-list__arrow" size={17} aria-hidden="true" />}
            </li>
          ))}
        </ol>
      </section>

      <section className="home-section home-intro-grid">
        <article className="home-intro-block">
          <p className="home-eyebrow"><span /> OUR MISSION</p>
          <h2>Keep essential cash access dependable.</h2>
          <p>We aim to help ATM operations teams interpret signed net cash flow, recognize risk sooner, and make timely replenishment decisions with greater confidence.</p>
          <Link className="home-text-link" to="/mission">Read our mission <ArrowRight size={15} /></Link>
        </article>
        <article className="home-intro-block home-intro-block--project">
          <p className="home-eyebrow"><span /> THE PROJECT</p>
          <h2>Operations insight, made understandable.</h2>
          <p>ATM Cash Intelligence brings forecasts, alerts, and replenishment workflows together. You do not need a data science background to understand what needs attention and what action comes next.</p>
          <Link className="home-text-link" to="/about">Meet the project <ArrowRight size={15} /></Link>
        </article>
      </section>

      <footer className="home-footer">
        <Link className="brand" to="/">
          <span className="brand__mark">A</span>
          <span>ATM Cash Intelligence</span>
        </Link>
        <nav className="home-footer__links" aria-label="Footer links">
          <Link to="/contact"><Mail size={15} />Email</Link>
          <a href="https://www.linkedin.com/in/rishi-srivastava-869672329/" target="_blank" rel="noreferrer">LinkedIn <ArrowRight size={14} /></a>
        </nav>
        <span className="home-footer__copyright">ATM Cash Intelligence · Operations insight</span>
      </footer>
    </>
  );
}

export default HomePage;
