/* Candidate pack: one .zip holding a workbook of the filtered candidates and
   a typeset PDF of each of their resumes.

   The PDFs reproduce the resume already transcribed into RESUMES, laid out to
   one standard format in Poppins. Nothing is rewritten, summarised or added:
   the same sections, in the same order, with the same words.

   The caller passes the full column set and this file decides what the pack
   carries. Two things come out. Compensation, so the pack can go to someone
   who should not see it. And the Round 1 question and expected-answer columns:
   they are the same question bank repeated on every row, they would add eighty
   columns, and handing an interviewer the model answers in advance defeats the
   round. Scores and notes stay — those are the candidate's.

   jsPDF, SheetJS and JSZip are fetched from cdnjs the first time a pack is
   built rather than on every page load. */

var BUNDLE = (function () {
  "use strict";

  var CDN = [
    "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"
  ];

  /* Column keys the pack never carries, whatever the caller picked. */
  var SALARY_COLS = ["ctc", "ectc", "hike", "offers", "offerCtc"];
  function omitted(k) {
    return SALARY_COLS.indexOf(k) > -1 || /^r1[qa]_/.test(k);
  }

  var libs = null;
  function present() {
    var jsPDF = (window.jspdf && window.jspdf.jsPDF) || window.jsPDF;
    return (jsPDF && window.XLSX && window.JSZip)
      ? { jsPDF: jsPDF, XLSX: window.XLSX, JSZip: window.JSZip } : null;
  }
  function loadLibs() {
    if (libs) return libs;
    var have = present();                      // already on the page: nothing to fetch
    if (have) { libs = Promise.resolve(have); return libs; }
    libs = Promise.all(CDN.map(function (src) {
      return new Promise(function (resolve, reject) {
        var s = document.createElement("script");
        s.src = src;
        s.onload = resolve;
        s.onerror = function () { reject(new Error("blocked: " + src)); };
        document.head.appendChild(s);
      });
    })).then(function () {
      var got = present();
      if (!got) throw new Error("libraries did not load");
      return got;
    });
    libs.catch(function () { libs = null; });   // let a later attempt retry
    return libs;
  }

  /* ---------------------------------------------------------------- paper */
  var PAGE = { w: 210, h: 297, top: 16, bottom: 17, left: 15, right: 15 };
  var INK = [28, 28, 28], MUTE = [91, 100, 114], FAINT = [138, 143, 152],
      ACCENT = [28, 53, 87], RULE = [199, 205, 214];
  var COL = PAGE.w - PAGE.left - PAGE.right;

  /* A sheet of paper that knows where the pen is and when to turn the page. */
  function Sheet(doc, footerLeft) {
    this.doc = doc;
    this.y = PAGE.top;
    this.footerLeft = footerLeft;
  }
  Sheet.prototype.room = function (mm) {
    if (this.y + mm <= PAGE.h - PAGE.bottom) return;
    this.doc.addPage();
    this.y = PAGE.top;
  };
  Sheet.prototype.font = function (weight, size, colour) {
    this.doc.setFont("Poppins", weight === "medium" ? "bold" : "normal");
    this.doc.setFontSize(size);
    this.doc.setTextColor(colour[0], colour[1], colour[2]);
  };
  /* Line height in mm for a given point size, at the ratio the page uses. */
  function lh(size) { return size * 0.3528 * 1.42; }

  Sheet.prototype.text = function (str, opts) {
    var o = opts || {};
    var size = o.size || 9.5, weight = o.weight || "regular";
    var colour = o.colour || INK, indent = o.indent || 0;
    var width = COL - indent - (o.trim || 0);
    this.font(weight, size, colour);
    var lines = this.doc.splitTextToSize(String(str), width);
    var step = lh(size);
    for (var i = 0; i < lines.length; i++) {
      this.room(step);
      this.font(weight, size, colour);       // a page break resets nothing, but be explicit
      this.doc.text(lines[i], PAGE.left + indent, this.y + step * 0.74);
      this.y += step;
    }
    if (o.after) this.y += o.after;
  };

  Sheet.prototype.bullet = function (str, size) {
    var s = size || 9.5, step = lh(s), indent = 4.2;
    this.font("regular", s, INK);
    var lines = this.doc.splitTextToSize(String(str), COL - indent);
    for (var i = 0; i < lines.length; i++) {
      this.room(step);
      this.font("regular", s, i === 0 ? MUTE : INK);
      if (i === 0) this.doc.text("•", PAGE.left + 0.8, this.y + step * 0.74);
      this.font("regular", s, INK);
      this.doc.text(lines[i], PAGE.left + indent, this.y + step * 0.74);
      this.y += step;
    }
    this.y += 0.7;
  };

  Sheet.prototype.heading = function (str) {
    /* Keep a heading with at least the first two lines under it. */
    this.room(lh(8.5) + 10);
    this.y += 4.5;
    this.font("medium", 8.5, ACCENT);
    this.doc.text(String(str).toUpperCase(), PAGE.left, this.y + 3, { charSpace: 0.35 });
    this.y += 5.1;
    this.doc.setDrawColor(RULE[0], RULE[1], RULE[2]);
    this.doc.setLineWidth(0.2);
    this.doc.line(PAGE.left, this.y, PAGE.w - PAGE.right, this.y);
    this.y += 2.6;
  };

  function header(sh, c, r) {
    sh.font("medium", 7.2, FAINT);
    sh.doc.text("CANDIDATE RESUME", PAGE.left, sh.y + 2.5, { charSpace: 0.5 });
    sh.y += 6.2;
    sh.font("medium", 20, INK);
    sh.doc.text(c.name, PAGE.left, sh.y + 6.5);
    sh.y += 9.4;
    if (r.title) sh.text(r.title, { size: 10.2, colour: ACCENT });
    sh.y += 0.6;
    if (r.contact) sh.text(r.contact, { size: 8.4, colour: MUTE });
    sh.y += 2.4;
    sh.doc.setDrawColor(ACCENT[0], ACCENT[1], ACCENT[2]);
    sh.doc.setLineWidth(0.7);
    sh.doc.line(PAGE.left, sh.y, PAGE.w - PAGE.right, sh.y);
    sh.y += 4;
  }

  /* The facts the portal holds about the candidate, as submitted. Never any
     compensation: this page is read by whoever is about to interview them. */
  function facts(sh, c) {
    var rows = [
      ["Applied for", c.role],
      ["Current company", c.company],
      ["Total experience", c.totalExp],
      ["Relevant experience", c.relExp],
      ["Current location", c.curLoc],
      ["Work location", "Coimbatore"],
      ["Availability", c.notice]
    ].filter(function (p) { return p[1] && String(p[1]).trim(); });
    if (!rows.length) return;
    sh.heading("At a glance");
    var labelW = 38, step = lh(9);
    rows.forEach(function (p) {
      sh.font("regular", 9, INK);
      var lines = sh.doc.splitTextToSize(String(p[1]), COL - labelW);
      sh.room(step * lines.length);
      sh.font("regular", 8.2, MUTE);
      sh.doc.text(p[0], PAGE.left, sh.y + step * 0.74);
      sh.font("regular", 9, INK);
      for (var i = 0; i < lines.length; i++) {
        sh.doc.text(lines[i], PAGE.left + labelW, sh.y + step * 0.74);
        sh.y += step;
      }
      sh.y += 0.6;
    });
  }

  function block(sh, b) {
    if (b[0] === "p") { sh.text(b[1], { size: 9.5, after: 2 }); return; }
    if (b[0] === "ul") { (b[1] || []).forEach(function (li) { sh.bullet(li); }); sh.y += 1.4; return; }
    if (b[0] === "kv") {
      (b[1] || []).forEach(function (p) {
        sh.room(lh(8) + lh(9.5));
        sh.text(String(p[0]).toUpperCase(), { size: 7.8, weight: "medium", colour: MUTE });
        sh.text(p[1], { size: 9.5, after: 1.6 });
      });
      return;
    }
    if (b[0] === "job") {
      var title = b[1], org = b[2], meta = b[3], bullets = b[4] || [];
      sh.room(lh(10.2) + lh(9.4) + lh(8.6) + 4);
      sh.y += 1.2;
      sh.text(title, { size: 10.2, weight: "medium" });
      if (org) sh.text(org, { size: 9.4, colour: ACCENT });
      if (meta) sh.text(meta, { size: 8.6, colour: MUTE });
      if (bullets.length) { sh.y += 1; bullets.forEach(function (x) { sh.bullet(x, 9.2); }); }
      sh.y += 1.8;
      return;
    }
  }

  function resumePdf(jsPDF, c, r, stamp) {
    var doc = new jsPDF({ unit: "mm", format: "a4", compress: true });
    doc.addFileToVFS("Poppins-Regular.ttf", POPPINS.regular);
    doc.addFont("Poppins-Regular.ttf", "Poppins", "normal");
    doc.addFileToVFS("Poppins-Medium.ttf", POPPINS.medium);
    doc.addFont("Poppins-Medium.ttf", "Poppins", "bold");
    doc.setProperties({ title: c.name + " — resume", creator: "Certainti Hiring Portal" });

    var sh = new Sheet(doc);
    header(sh, c, r);
    facts(sh, c);
    (r.sections || []).forEach(function (sec) {
      sh.heading(sec.h);
      (sec.b || []).forEach(function (b) { block(sh, b); });
    });

    var n = doc.getNumberOfPages();
    for (var i = 1; i <= n; i++) {
      doc.setPage(i);
      doc.setFont("Poppins", "normal");
      doc.setFontSize(7);
      doc.setTextColor(FAINT[0], FAINT[1], FAINT[2]);
      doc.text(c.name + "  ·  SL " + c.sl + "  ·  " + stamp, PAGE.left, PAGE.h - 9);
      doc.text("Page " + i + " of " + n, PAGE.w - PAGE.right, PAGE.h - 9, { align: "right" });
    }
    return doc.output("arraybuffer");
  }

  /* ------------------------------------------------------------- workbook */
  function workbook(XLSX, cols, rows, stamp) {
    var head = cols.map(function (c) { return c.h; });
    var aoa = [head].concat(rows.map(function (c) {
      return cols.map(function (col) {
        var v = col.v(c);
        return (v == null || v === "") ? "" : v;
      });
    }));
    var ws = XLSX.utils.aoa_to_sheet(aoa);
    ws["!cols"] = cols.map(function (c) {
      var w = Math.max(c.h.length + 2, 10);
      rows.forEach(function (r) {
        var v = c.v(r);
        if (v != null) w = Math.max(w, Math.min(String(v).length + 2, 60));
      });
      return { wch: w };
    });
    ws["!freeze"] = { xSplit: 0, ySplit: 1 };
    ws["!autofilter"] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 },
                                                         e: { r: aoa.length - 1, c: head.length - 1 } }) };
    var wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Candidates");

    var note = XLSX.utils.aoa_to_sheet([
      ["Certainti hiring — candidate pack"],
      [],
      ["Generated", stamp],
      ["Candidates", rows.length],
      [],
      ["Compensation is deliberately excluded.",
       "Current CTC, expected CTC, the hike, competing offers and any offered CTC are not in this file."],
      ["Round 1 answers are excluded.",
       "Per-topic scores and notes are here; the question text and expected answers are not, so " +
       "nobody reads the model answer before the interview."],
      ["Resumes", "One PDF per candidate sits beside this workbook in the same zip."],
      ["Source", "Generated from the Certainti Hiring Portal; the resumes are as transcribed there."]
    ]);
    note["!cols"] = [{ wch: 42 }, { wch: 86 }];
    XLSX.utils.book_append_sheet(wb, note, "Read Me");
    return XLSX.write(wb, { bookType: "xlsx", type: "array" });
  }

  /* ----------------------------------------------------------------- pack */
  function safeName(s) {
    return String(s).replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60) || "candidate";
  }

  /* cols: the full column list. rows: the filtered candidates, in view order.
     resumes: the RESUMES map. onStep: progress callback (done, total). */
  function build(opts) {
    var rows = opts.rows, resumes = opts.resumes || {};
    var stamp = opts.stamp, onStep = opts.onStep || function () {};
    var cols = opts.cols.filter(function (c) { return !omitted(c.k); });

    if (typeof POPPINS === "undefined") {
      return Promise.reject(new Error("blocked: the Poppins font file did not load"));
    }
    return loadLibs().then(function (L) {
      var zip = new L.JSZip();
      zip.file("Candidates.xlsx", workbook(L.XLSX, cols, rows, stamp));
      var folder = zip.folder("Resumes");
      var missing = [];
      var total = rows.length, done = 0;

      /* One at a time, yielding between each, so a pack of thirty resumes
         does not lock the tab up while it renders. */
      return rows.reduce(function (chain, c) {
        return chain.then(function () {
          var r = resumes[c.sl];
          if (!r) { missing.push(c.name); }
          else {
            folder.file(safeName(c.name) + "_SL" + c.sl + ".pdf", resumePdf(L.jsPDF, c, r, stamp));
          }
          onStep(++done, total);
          return new Promise(function (res) { setTimeout(res, 0); });
        });
      }, Promise.resolve()).then(function () {
        return zip.generateAsync({ type: "blob", compression: "DEFLATE",
                                   compressionOptions: { level: 6 } });
      }).then(function (blob) {
        return { blob: blob, missing: missing, count: total - missing.length };
      });
    });
  }

  return { build: build, SALARY_COLS: SALARY_COLS, omitted: omitted, loadLibs: loadLibs };
})();
