/* Prince Kumar P's curriculum vitae on its own, typeset from the same
   structured resume the portal shows. No assessment, no commercials, no
   covering notes — the document as submitted. */
import { HERE, esc, load, sections, CSS, renderPdf } from './resume_pdf_common.mjs';

const { c, r } = load(18);

const doc = `<!doctype html>
<html><head><meta charset="utf-8"><title>Curriculum Vitae — ${esc(c.name)}</title>
<style>${CSS}
  /* Slightly tighter than the brief's settings, and headings stay with the
     block they introduce so a section never splits across the page break. */
  .job { margin-bottom: 7pt; }
  li { margin-bottom: 2.6pt; }
  .res p { margin-bottom: 6.5pt; }
  .res h3 { margin: 11pt 0 5pt; page-break-after: avoid; }
</style></head><body>

<header class="brief">
  <div class="eyebrow">Curriculum vitae</div>
  <h1>${esc(c.name)}</h1>
  <div class="role">${esc(r.title)}</div>
  <div class="contact">${esc(r.contact)}</div>
</header>

${sections(r)}

</body></html>`;

await renderPdf(doc, HERE + '/Prince_Kumar_P_Resume.pdf',
                'Prince Kumar P &middot; curriculum vitae');
