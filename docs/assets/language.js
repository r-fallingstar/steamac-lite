(() => {
  const root = new URL('../', document.currentScript.src);
  const routes = {ja: '', en: 'en/', ko: 'ko/', 'zh-CN': 'zh-CN/'};
  const storageKey = 'steamac-guide-language';
  const normalize = value => {
    const language = String(value || '').toLowerCase();
    if (/^ja(?:-|$)/.test(language)) return 'ja';
    if (/^en(?:-|$)/.test(language)) return 'en';
    if (/^ko(?:-|$)/.test(language)) return 'ko';
    if (/^zh(?:-|$)/.test(language)) return 'zh-CN';
    return null;
  };
  const remember = language => {
    try { localStorage.setItem(storageKey, language); } catch { /* Private/storage-disabled browsing. */ }
  };
  const atRoot = location.pathname === root.pathname || location.pathname === root.pathname + 'index.html';
  if (atRoot) {
    const requested = normalize(new URLSearchParams(location.search).get('lang'));
    let saved = null;
    try { saved = normalize(localStorage.getItem(storageKey)); } catch { /* Keep navigation working. */ }
    const preferred = requested || saved || (navigator.languages || [navigator.language]).map(normalize).find(Boolean) || 'en';
    if (requested) remember(requested);
    if (preferred !== 'ja') {
      location.replace(new URL(routes[preferred] + location.hash, root).href);
      return;
    }
  } else {
    // A directly opened language-specific URL always wins over saved/browser preferences.
    const language = normalize(document.documentElement.lang);
    if (language) remember(language);
  }
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-language]').forEach(link => {
      link.addEventListener('click', event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        remember(link.dataset.language);
        const target = new URL(link.href);
        target.hash = location.hash;
        link.href = target.href;
      });
    });
  });
})();
