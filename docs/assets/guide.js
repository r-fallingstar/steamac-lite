(() => {
  const root = document.documentElement;
  const themeBtn = document.querySelector('#theme-toggle');
  const moonIcon = document.querySelector('#theme-icon-moon');
  const sunIcon = document.querySelector('#theme-icon-sun');
  const themeMeta = document.querySelector('#theme-color-meta');

  const syncTheme = (theme, persist) => {
    const next = theme === 'dark' ? 'dark' : 'light';
    root.setAttribute('data-theme', next);
    if (themeMeta) themeMeta.setAttribute('content', next === 'dark' ? '#100B1C' : '#FCF9FF');
    if (moonIcon && sunIcon) {
      moonIcon.style.display = next === 'light' ? 'block' : 'none';
      sunIcon.style.display = next === 'dark' ? 'block' : 'none';
    }
    if (themeBtn) themeBtn.setAttribute('aria-pressed', String(next === 'dark'));
    if (persist) {
      try {
        localStorage.setItem('steamac-guide-theme', next);
        localStorage.setItem('rf-theme', next);
      } catch (_) { /* Storage may be disabled in private browsing. */ }
    }
  };

  syncTheme(root.getAttribute('data-theme'), false);
  if (themeBtn) {
    themeBtn.addEventListener('click', () => {
      const current = root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      syncTheme(current === 'light' ? 'dark' : 'light', true);
    });
  }

  // Close language picker dropdown on outside click or Escape.
  const langPicker = document.querySelector('.language-picker');
  if (langPicker) {
    document.addEventListener('click', event => {
      if (langPicker.open && !langPicker.contains(event.target)) {
        langPicker.open = false;
      }
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && langPicker.open) {
        langPicker.open = false;
      }
    });
  }

  // Screenshot lightbox dialog.
  const dialog = document.querySelector('#photo-dialog');
  const zoomLabel = root.dataset.photoZoom;
  const fitLabel = root.dataset.photoFit;
  if (dialog && typeof dialog.showModal === 'function') {
    const photo = document.querySelector('#photo-full');
    const title = document.querySelector('#photo-title');
    const scale = document.querySelector('#photo-scale');
    document.querySelectorAll('a[data-zoom]').forEach(link => {
      link.addEventListener('click', event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        photo.src = link.href;
        photo.alt = link.querySelector('img').alt;
        title.textContent = link.closest('figure').querySelector('figcaption').textContent;
        photo.classList.remove('is-zoomed');
        scale.setAttribute('aria-pressed', 'false');
        scale.textContent = zoomLabel;
        dialog.showModal();
        dialog.scrollTop = 0;
        dialog.scrollLeft = 0;
      });
    });
    scale.addEventListener('click', () => {
      const expanded = photo.classList.toggle('is-zoomed');
      scale.setAttribute('aria-pressed', String(expanded));
      scale.textContent = expanded ? fitLabel : zoomLabel;
    });
    document.querySelector('#photo-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    });
  }

  // Highlight active TOC item while scrolling.
  if ('IntersectionObserver' in window) {
    const links = [...document.querySelectorAll('.contents nav a')];
    const observer = new IntersectionObserver(entries => {
      const current = entries.filter(entry => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (!current) return;
      links.forEach(link => {
        if (link.hash === '#' + current.target.id) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      });
    }, {rootMargin: '-12% 0px -62% 0px', threshold: 0});
    document.querySelectorAll('.step').forEach(section => observer.observe(section));
  }

  // Progressive scroll reveal.
  const reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if ('IntersectionObserver' in window && !reducedMotion && !root.classList.contains('no-reveal')) {
    const targets = [...document.querySelectorAll('.requirements, .step, .japanese-section, .display-section, .faq-section, .end-download')];
    if (targets.length) {
      targets.forEach(el => el.classList.add('reveal-target'));
      root.classList.add('js-reveal');
      const revealObserver = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            revealObserver.unobserve(entry.target);
          }
        });
      }, {rootMargin: '0px 0px -6% 0px', threshold: 0.04});
      targets.forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.top < window.innerHeight * 0.96) el.classList.add('is-visible');
        else revealObserver.observe(el);
      });
    }
  }

  // Subtle cursor spotlight on fine-pointer devices.
  if (window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    document.querySelectorAll('.step, .requirements, .end-download').forEach(card => {
      card.addEventListener('pointermove', event => {
        const rect = card.getBoundingClientRect();
        card.style.setProperty('--mx', (event.clientX - rect.left) + 'px');
        card.style.setProperty('--my', (event.clientY - rect.top) + 'px');
      });
    });
  }
})();
