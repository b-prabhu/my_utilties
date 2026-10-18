/* Builds the CEO-interview brief for SL 18, Prince Kumar P. The prose sections
   are written about him specifically, so this is one candidate's generator, not
   a template: the facts come from the pipeline, the reading of them does not. */
import { HERE, esc, load, sections, CSS, renderPdf } from './resume_pdf_common.mjs';

const { c, r } = load(18);

/* ---- facts drawn from the CV, stated without assessment ---- */
const CAREER = [
  ['Jan 2020 – present', 'Senior Lead Software Engineer', 'Virtusa Consulting Services, Chennai',
   'British Telecom account. Visual API Orchestration &amp; Transformation Platform (Mar 2024 onward); Custom ETL Tool and Migration Dashboard (Mar 2020 – Mar 2024)'],
  ['May 2013 – Jan 2020', 'Senior Application Developer', 'Treselle Systems, Chennai',
   'Discern, a financial and stock-market analytics platform; Rehlte.com, a flight and hotel booking platform'],
  ['Oct 2012 – Apr 2013', 'Senior Developer', 'Congruent Solutions, Chennai', ''],
  ['Nov 2010 – Sep 2012', 'Developer', 'AEL Data, Chennai', ''],
];

const STACK = [
  ['Angular', '~9 years'],
  ['Node.js', '~7 years'],
  ['Java / Spring Boot', '~5 years'],
  ['React', '~5 years'],
  ['AWS, Kafka, Docker, Kubernetes', 'Virtusa engagements, 2020 onward'],
];

const doc = `<!doctype html>
<html><head><meta charset="utf-8"><title>Candidate Brief — Prince Kumar P</title>
<style>${CSS}</style></head><body>

<header class="brief">
  <div class="eyebrow">Candidate brief &middot; prepared for CEO interview</div>
  <h1>${esc(c.name)}</h1>
  <div class="role">${esc(c.role)} &nbsp;·&nbsp; ${esc(r.title)}</div>
  <div class="contact">${esc(r.contact)}</div>
</header>

<h2>At a glance</h2>
<table class="facts">
  <tr><td class="k">Position under consideration</td><td>${esc(c.role)}</td></tr>
  <tr><td class="k">Current organisation</td><td>${esc(c.company)}</td></tr>
  <tr><td class="k">Total experience</td><td>${esc(c.totalExp)}</td></tr>
  <tr><td class="k">Location</td><td>Chennai, per his CV. The submission records Coimbatore \u2014 worth confirming.</td></tr>
  <tr><td class="k">Role is based in</td><td>Coimbatore</td></tr>
  <tr><td class="k">Education</td><td>B.E. Computer Science — Anna University, Coimbatore (2004–2008)</td></tr>
  <tr><td class="k">Recognition</td><td>Technology Excellence Award, H1 FY23 — Virtusa (British Telecom account)</td></tr>
</table>

<h2>Profile summary</h2>
<p>Prince Kumar is a senior full-stack engineering lead with sixteen years in enterprise software
delivery, the last six and a half of them at Virtusa on the British Telecom account. He works across the whole
stack — Java and Spring Boot and Node.js on the server, Angular and React on the client — and has
spent the recent part of his career designing and leading cloud-native, event-driven systems on AWS
rather than writing features within someone else's architecture.</p>

<p>His two most substantial pieces of work are both platforms rather than applications. The first is
a visual API orchestration and transformation platform that lets users assemble and run API
workflows through a drag-and-drop designer, built as Kafka-connected Java and Node
microservices, containerised with Docker and run on Kubernetes, which he reports taking to 99.9%
uptime. The second is a configurable ETL and migration platform that moved more than 200 database
tables, files and S3 objects between legacy and modern systems with, by his account, zero data loss
— again orchestrated through Kafka with a monitoring dashboard he also built.</p>

<p>Two things stand out beyond the delivery record. He has invested in production observability as a
discipline — Prometheus, Grafana and Loki wired across services to watch JVM memory, GC behaviour
and application performance, with real-time dashboards and anomaly detection, which is a level of
operational care not everyone at this grade brings. And he leads: he mentored more than ten
developers, set coding standards, reports a 100% promotion rate within his team, and resolved 40+
production incidents at a two-hour average. Earlier in his career at Treselle he built consumer-scale
products — a market analytics platform tracking 1,000+ tickers for 5,000 concurrent users, and a
travel booking platform integrating Amadeus, Sabre and Travelport for 10,000+ monthly users.</p>

<h2>Technology profile, as stated on his CV</h2>
<table class="facts">
  ${STACK.map(([k, v]) => `<tr><td class="k">${k}</td><td>${v}</td></tr>`).join('')}
</table>

<h2>Career at a glance</h2>
<table class="career">
  <tr><th>Period</th><th>Role</th><th>Organisation / focus</th></tr>
  ${CAREER.map(([when, what, org, focus]) => `<tr>
    <td class="when">${when}</td>
    <td class="what">${what}</td>
    <td>${org}${focus ? `<br><span style="color:#5b6472;font-size:8.8pt">${focus}</span>` : ''}</td>
  </tr>`).join('')}
</table>

<h2>Suggested ground for the CEO conversation</h2>
<ul>
  <li>How he decides where a service boundary belongs, and when he has argued against splitting one.</li>
  <li>The orchestration platform: what he would build differently a second time.</li>
  <li>How he grew ten developers — what he changed about how the team worked, not just what he taught.</li>
  <li>What he wants from the next role that Virtusa could not give him.</li>
</ul>

<footer class="note">
  Prepared 18 October 2026 from the candidate's own curriculum vitae. Interview feedback and
  commercial terms are deliberately excluded.
</footer>

<div class="pagebreak"></div>
<header class="brief">
  <div class="eyebrow">Curriculum vitae as submitted</div>
  <h1 style="font-size:17pt">${esc(c.name)}</h1>
  <div class="role" style="font-size:10.4pt">${esc(r.title)}</div>
  <div class="contact">${esc(r.contact)}</div>
</header>
${sections(r)}

</body></html>`;

await renderPdf(doc, HERE + '/Prince_Kumar_P_Candidate_Brief.pdf',
                'Prince Kumar P &middot; candidate brief &middot; confidential');
