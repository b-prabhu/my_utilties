// Progressive enhancements: test timer + autosave, practice checklist,
// live theme preview, confirm dialogs, JSON file loader.
(function () {
  const csrf = (document.querySelector('meta[name=csrf]') || {}).content;

  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-confirm]');
    if (el && !confirm(el.getAttribute('data-confirm'))) e.preventDefault();
  });

  // ---- Test: autosave and countdown ----
  const form = document.getElementById('test-form');
  if (form) {
    const status = form.querySelector('.save-status');
    let dirty = false; let submitting = false;
    const save = async () => {
      if (!dirty || submitting) return;
      dirty = false;
      const body = new URLSearchParams(new FormData(form));
      try {
        const r = await fetch(form.dataset.save, { method: 'POST', body, headers: { 'x-csrf-token': csrf, accept: 'application/json' } });
        if (!r.ok) throw new Error();
        status.textContent = `Saved ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      } catch { dirty = true; status.textContent = 'Not saved yet – check your connection'; }
    };
    form.addEventListener('input', () => { dirty = true; status.textContent = 'Unsaved changes…'; });
    form.addEventListener('submit', () => { submitting = true; });
    setInterval(save, 15000);
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') save(); });
    window.addEventListener('beforeunload', (e) => { if (dirty && !submitting) { save(); e.preventDefault(); } });

    const timer = document.querySelector('.timer');
    if (timer) {
      const deadline = Number(timer.dataset.deadline);
      const val = timer.querySelector('.timer-val');
      const tick = () => {
        const left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
        val.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
        timer.classList.toggle('low', left < 300);
        if (left === 0 && !submitting) { submitting = true; form.submit(); }
      };
      tick(); setInterval(tick, 1000);
    }
  }

  // ---- Test: photos of handwritten working (resized in the browser) ----
  const resize = (file) => new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, 1600 / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src);
      resolve(c.toDataURL('image/jpeg', 0.82));
    };
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });
  document.querySelectorAll('.photos[data-upload]').forEach((box) => {
    const input = box.querySelector('input[type=file]');
    const post = (url, data) => fetch(url, { method: 'POST', headers: { 'content-type': 'application/json', 'x-csrf-token': csrf }, body: JSON.stringify(data) }).then((r) => r.json());
    const addThumb = (name) => {
      const fig = document.createElement('figure'); fig.className = 'photo';
      fig.innerHTML = `<a href="/uploads/${name}" target="_blank" rel="noopener"><img src="/uploads/${name}" alt="Photo of working"></a><button type="button" class="ghost small photo-remove" data-name="${name}">Remove</button>`;
      box.insertBefore(fig, box.querySelector('.photo-add'));
    };
    if (input) input.addEventListener('change', async () => {
      for (const f of input.files) {
        try {
          const res = await post(box.dataset.upload, { image: await resize(f) });
          if (res.ok) addThumb(res.name); else alert(res.error || 'Upload failed');
        } catch { alert('Could not read that image.'); }
      }
      input.value = '';
    });
    box.addEventListener('click', async (e) => {
      const btn = e.target.closest('.photo-remove');
      if (!btn) return;
      const res = await post(`${box.dataset.upload}/delete`, { name: btn.dataset.name });
      if (res.ok) btn.closest('.photo').remove();
    });
  });

  // ---- Study guide: practice checklist saved to the account ----
  const sec = document.querySelector('[data-section]');
  if (sec) {
    let done = [];
    try { done = JSON.parse(sec.dataset.practiceDone || '[]'); } catch { /* ignore */ }
    const boxes = sec.querySelectorAll('.practice-done');
    boxes.forEach((b) => {
      b.checked = done.includes(Number(b.dataset.index));
      b.addEventListener('change', () => {
        done = [...boxes].filter((x) => x.checked).map((x) => Number(x.dataset.index));
        fetch(`/study/${sec.dataset.section}/progress`, {
          method: 'POST',
          headers: { 'content-type': 'application/x-www-form-urlencoded', 'x-csrf-token': csrf },
          body: new URLSearchParams({ practice: done.join(',') }),
        });
      });
    });
  }

  // ---- Theme picker: live preview, saves instantly ----
  const themeForm = document.getElementById('theme-form');
  if (themeForm) {
    const vars = document.getElementById('theme-vars');
    const picker = themeForm.querySelector('#custom_color');
    const customRadio = themeForm.querySelector('input[value=custom]');
    const statusEl = themeForm.querySelector('.theme-status');
    const apply = (c) => { vars.textContent = `:root{--accent:${c}}`; try { localStorage.setItem('sg-accent', c); } catch { /* ignore */ } };
    const persist = async () => {
      const body = new URLSearchParams(new FormData(themeForm));
      const r = await fetch(themeForm.action, { method: 'POST', body, headers: { 'x-csrf-token': csrf, accept: 'application/json' } });
      statusEl.textContent = r.ok ? 'Saved to your account' : 'Could not save';
    };
    themeForm.addEventListener('change', (e) => {
      if (e.target.name === 'theme') {
        themeForm.querySelectorAll('.swatch').forEach((s) => s.classList.toggle('selected', s.contains(e.target)));
        apply(e.target.value === 'custom' ? picker.value : e.target.dataset.color);
        persist();
      }
    });
    picker.addEventListener('input', () => {
      customRadio.checked = true;
      themeForm.querySelectorAll('.swatch').forEach((s) => s.classList.toggle('selected', s.contains(customRadio)));
      document.getElementById('custom-dot').style.background = picker.value;
      apply(picker.value);
    });
    picker.addEventListener('change', persist);
    themeForm.addEventListener('submit', (e) => { e.preventDefault(); persist(); });
  }

  // ---- Admin: load a JSON file into a textarea ----
  document.querySelectorAll('input[type=file][data-fill]').forEach((inp) => {
    inp.addEventListener('change', async () => {
      const f = inp.files[0];
      if (!f) return;
      document.querySelector(inp.dataset.fill).value = await f.text();
      const name = document.getElementById('file_name');
      if (name && !name.value) name.value = f.name;
    });
  });
})();
