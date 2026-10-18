/* Shared plumbing for the candidate PDFs built out of the pipeline's own data
   files. The styling lives here so a full brief and a bare CV come out of the
   same pack rather than drifting apart. Needs playwright with the preinstalled
   Chromium. */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright';

export const HERE = path.dirname(fileURLToPath(import.meta.url));

export const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/* Pull the candidate row and resume straight from the portal's data so these
   documents cannot drift from what the pipeline holds. */
export function load(sl) {
  const html = fs.readFileSync(HERE + '/pipeline_page.html', 'utf8');
  const a = html.indexOf('var ROLES ='), b = html.indexOf('/* ===================== derived');
  const C = new Function(html.slice(a, b) + '\n return C;')();
  const RESUMES = new Function(fs.readFileSync(HERE + '/pipeline_resumes.js', 'utf8') + '\n return RESUMES;')();
  const c = C.find(x => x.sl === sl), r = RESUMES[sl];
  if (!c || !r) throw new Error('candidate or resume missing for SL ' + sl);
  return { c, r };
}

/* ---- resume body, rendered from the same structured sections the portal uses ---- */
export function sections(r) {
  return r.sections.map(sec => {
    const blocks = sec.b.map(blk => {
      if (blk[0] === 'p') return `<p>${esc(blk[1])}</p>`;
      if (blk[0] === 'ul') return `<ul>${blk[1].map(li => `<li>${esc(li)}</li>`).join('')}</ul>`;
      if (blk[0] === 'kv') return `<dl class="kv">${blk[1].map(
        ([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`;
      if (blk[0] === 'job') {
        const [, title, org, meta, bullets] = blk;
        return `<div class="job">
          <div class="jt">${esc(title)}</div>
          ${org ? `<div class="jo">${esc(org)}</div>` : ''}
          ${meta ? `<div class="jm">${esc(meta)}</div>` : ''}
          ${bullets && bullets.length ? `<ul>${bullets.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
        </div>`;
      }
      return '';
    }).join('');
    return `<section class="res"><h3>${esc(sec.h)}</h3>${blocks}</section>`;
  }).join('');
}

export const CSS = `
  @page { size: A4; margin: 16mm 15mm 14mm; }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: "Bitstream Charter", "Liberation Serif", Georgia, serif;
    font-size: 10.2pt; line-height: 1.5; color: #1c1c1c;
  }
  .label { font-family: "Liberation Sans", Arial, sans-serif; }

  header.brief { border-bottom: 2.5pt solid #1c3557; padding-bottom: 9pt; margin-bottom: 14pt; }
  .eyebrow {
    font-family: "Liberation Sans", Arial, sans-serif; font-size: 7.6pt; letter-spacing: .13em;
    text-transform: uppercase; color: #6b7280; margin-bottom: 5pt;
  }
  h1 { font-size: 23pt; margin: 0; letter-spacing: -.2pt; font-weight: 700; }
  .role { font-size: 11.6pt; color: #1c3557; margin-top: 2pt; font-style: italic; }
  .contact {
    font-family: "Liberation Sans", Arial, sans-serif; font-size: 8.4pt; color: #4b5563;
    margin-top: 7pt; line-height: 1.6;
  }

  h2 {
    font-family: "Liberation Sans", Arial, sans-serif; font-size: 8.4pt; letter-spacing: .12em;
    text-transform: uppercase; color: #1c3557; margin: 16pt 0 7pt;
    border-bottom: .6pt solid #c7cdd6; padding-bottom: 3pt;
  }
  h2:first-of-type { margin-top: 0; }
  p { margin: 0 0 7pt; text-align: justify; }

  table.facts { width: 100%; border-collapse: collapse; margin-bottom: 4pt; }
  table.facts td { padding: 3.6pt 0; vertical-align: top; border-bottom: .4pt solid #e6e8ec; }
  table.facts td.k {
    font-family: "Liberation Sans", Arial, sans-serif; font-size: 8pt; color: #6b7280;
    width: 33%; letter-spacing: .02em;
  }
  table.facts tr:last-child td { border-bottom: 0; }

  table.career { width: 100%; border-collapse: collapse; }
  table.career th {
    font-family: "Liberation Sans", Arial, sans-serif; font-size: 7.6pt; letter-spacing: .09em;
    text-transform: uppercase; color: #6b7280; text-align: left; padding: 0 6pt 4pt 0;
    border-bottom: .6pt solid #c7cdd6;
  }
  table.career td { padding: 5pt 6pt 5pt 0; vertical-align: top; border-bottom: .4pt solid #eceef1; font-size: 9.4pt; }
  table.career td.when { white-space: nowrap; color: #4b5563; font-size: 8.8pt; width: 24%; }
  table.career td.what { font-weight: 700; }

  ul { margin: 0 0 7pt; padding-left: 13pt; }
  li { margin-bottom: 3.2pt; }

  .res h3 {
    font-family: "Liberation Sans", Arial, sans-serif; font-size: 8.4pt; letter-spacing: .1em;
    text-transform: uppercase; color: #1c3557; margin: 13pt 0 6pt;
    border-bottom: .5pt solid #dde0e5; padding-bottom: 2.5pt;
  }
  .job { margin-bottom: 9pt; page-break-inside: avoid; }
  .jt { font-weight: 700; font-size: 10.4pt; }
  .jo { color: #1c3557; font-size: 9.8pt; }
  .jm { color: #5b6472; font-size: 8.8pt; font-style: italic; margin-top: 1pt; }
  .job ul { margin-top: 4pt; }

  dl.kv { margin: 0 0 7pt; }
  dl.kv dt {
    font-family: "Liberation Sans", Arial, sans-serif; font-size: 7.8pt; letter-spacing: .05em;
    text-transform: uppercase; color: #6b7280; margin-top: 5pt;
  }
  dl.kv dd { margin: 1pt 0 0; }

  .pagebreak { page-break-before: always; }
  footer.note {
    margin-top: 14pt; padding-top: 7pt; border-top: .5pt solid #dde0e5;
    font-family: "Liberation Sans", Arial, sans-serif; font-size: 7.6pt; color: #8a8f98;
  }
`;

export async function renderPdf(doc, outPath, footerLeft) {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const page = await browser.newPage();
  await page.setContent(doc, { waitUntil: 'load' });
  await page.pdf({
    path: outPath,
    format: 'A4', printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: '<div style="width:100%;font-family:Arial,sans-serif;font-size:7pt;color:#9aa0a8;padding:0 15mm;">' +
                    '<span style="float:left">' + footerLeft + '</span>' +
                    '<span style="float:right">Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>',
    margin: { top: '16mm', bottom: '16mm', left: '15mm', right: '15mm' },
  });
  await browser.close();
  console.log('written ' + outPath);
}
