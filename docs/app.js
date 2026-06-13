// Hockey Dictionary — app.js · Sprint 4
// Fuse.js fuzzy search + rendering for новый дизайн «программка матча»

const FUSE_OPTIONS = {
  keys: [
    { name: 'en',         weight: 0.4 },
    { name: 'ru',         weight: 0.3 },
    { name: 'abbr',       weight: 0.2 },
    { name: 'definition', weight: 0.1 }
  ],
  threshold: 0.35,
  includeMatches: true,
  minMatchCharLength: 2
};

const CATEGORY_LABELS = {
  stat:     'Статистика',
  tactic:   'Тактика',
  rule:     'Правила',
  position: 'Позиции'
};

let allTerms   = [];
let expertTerms = [];
let fuse       = null;
let activeFilter = 'all';

// ─── Fetch ────────────────────────────────────────────────────────────────────

async function loadData() {
  const [terms, expert] = await Promise.all([
    fetch('./data/terms.json').then(r => r.json()),
    fetch('./data/expert_review.json').then(r => r.json())
  ]);
  allTerms    = terms;
  expertTerms = expert;
  fuse = new Fuse(allTerms, FUSE_OPTIONS);
  render();
}

// ─── Render ───────────────────────────────────────────────────────────────────

function render(query = '', filter = 'all') {
  const container     = document.getElementById('terms-container');
  const expertCont    = document.getElementById('expert-container');
  const expertSection = document.getElementById('expert-section');
  const countEl       = document.getElementById('search-count');

  // Поиск
  let results = allTerms;
  if (query.length >= 2) {
    results = fuse.search(query).map(r => r.item);
  }

  // Фильтр по категории
  if (filter !== 'all') {
    results = results.filter(t => t.category === filter);
  }

  // Рендер карточек
  if (results.length === 0) {
    container.innerHTML = `
      <div class="search-empty">
        <div class="search-empty__icon">🏒</div>
        <p>По запросу «${escapeHtml(query)}» ничего не найдено</p>
      </div>`;
  } else {
    container.innerHTML = results.map((t, i) => renderTermCard(t, i)).join('');
  }

  // Счётчик
  if (query || filter !== 'all') {
    countEl.textContent = `найдено ${results.length} из ${allTerms.length} терминов`;
  } else {
    countEl.textContent = `${allTerms.length} терминов · 4 категории`;
  }

  // Секция «На выверке» — скрыть при поиске/фильтре
  const showExpert = !query && filter === 'all';
  expertSection.style.display = showExpert ? '' : 'none';
  if (showExpert) {
    expertCont.innerHTML = expertTerms.map(t => renderExpertCard(t)).join('');
  }
}

// ─── Карточка термина ─────────────────────────────────────────────────────────

function renderTermCard(t, index) {
  const num      = String(index + 1).padStart(2, '0');
  const catLabel = CATEGORY_LABELS[t.category] || t.category;
  const catClass = `term-card__cat--${t.category}`;

  const abbrs = t.abbr && t.abbr.length > 0
    ? `<div class="term-card__abbrs">${t.abbr.map(a => `<span class="abbr">${escapeHtml(a)}</span>`).join('')}</div>`
    : '';

  const slang = t.ru_slang
    ? `<div class="term-card__slang"><span class="label">Сленг</span><span>${escapeHtml(t.ru_slang)}</span></div>`
    : '';

  return `
    <article class="term-card" data-cat="${t.category}" data-id="${t.id}">
      <div class="term-card__meta">
        <span class="term-card__num">№ ${num}</span>
        <span class="term-card__cat ${catClass}">${catLabel}</span>
      </div>
      <div class="term-card__titles">
        <span class="term-card__en">${escapeHtml(t.en)}</span>
        <span class="term-card__ru">${escapeHtml(t.ru)}</span>
      </div>
      ${abbrs}
      <p class="term-card__def">${escapeHtml(t.definition)}</p>
      ${slang}
    </article>`;
}

// ─── Карточка «На выверке» ────────────────────────────────────────────────────

function renderExpertCard(t) {
  const slang = t.ru_slang
    ? `<div class="term-card__slang"><span class="label">Сленг</span><span>${escapeHtml(t.ru_slang)}</span></div>`
    : '';

  return `
    <article class="term-card term-card--unverified" data-cat="${t.category}" data-id="${t.id}">
      <span class="stamp">Требует проверки экспертом</span>
      <div class="term-card__titles">
        <span class="term-card__en">${escapeHtml(t.en)}</span>
        <span class="term-card__ru">${escapeHtml(t.ru)}</span>
      </div>
      <p class="term-card__def">${escapeHtml(t.definition)}</p>
      ${slang}
    </article>`;
}

// ─── Utils ────────────────────────────────────────────────────────────────────

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ─── Events ───────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const searchInput = document.getElementById('search');
  let debounceTimer;

  searchInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      render(searchInput.value.trim(), activeFilter);
    }, 180);
  });

  document.querySelectorAll('.chip[data-filter]').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.chip[data-filter]').forEach(c => c.classList.remove('is-active'));
      chip.classList.add('is-active');
      activeFilter = chip.dataset.filter;
      render(searchInput.value.trim(), activeFilter);
    });
  });

  loadData().catch(() => {
    document.getElementById('terms-container').innerHTML = `
      <div class="search-empty">
        <div class="search-empty__icon">⚠️</div>
        <p>Не удалось загрузить данные. Открой через локальный сервер, не через file://.</p>
      </div>`;
  });
});
