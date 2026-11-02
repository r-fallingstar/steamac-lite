(() => {
  const dialog = document.querySelector('#photo-dialog');
  const zoomLabel = document.documentElement.dataset.photoZoom;
  const fitLabel = document.documentElement.dataset.photoFit;
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
  if ('IntersectionObserver' in window) {
    const links = [...document.querySelectorAll('.contents nav a')];
    const observer = new IntersectionObserver(entries => {
      const current = entries.filter(entry => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (!current) return;
      links.forEach(link => {
        if (link.hash === '#' + current.target.id) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      });
    }, {rootMargin: '-5% 0px -65% 0px', threshold: 0});
    document.querySelectorAll('.step').forEach(section => observer.observe(section));
  }
})();
