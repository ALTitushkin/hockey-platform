// Hockey Dictionary — app.js
// Loads terms.json and expert_review.json, renders cards, powers Fuse.js search

const FUSE_OPTIONS = {
  keys: [
    { name: 'en', weight: 0.4 },
    { name: 'ru', weight: 0.3 },
    { name: 'abbr', weight: 0.2 },
    { name: 'definition', weight: 0.1 }
  ],
  threshold: 0.35,
  includeMatches: true,
  minMatchCharLength: 2
};

const CATEGORY_LABELS = {
  stat: 'Статистика',
  tactic: 'Тактика',
  rule: 'Правила',
  position: 'Позиции'
};

const CATEGORY_ICONS = {
  stat: '#',
  tactic: '⬡',
  rule: '§',
  position: '◈'
};

let allTerms = [];
let expertTerms = [];
let fuse = null;
let activeFilter = 'all';

// ─── Fetch data ───────────────────────────────────────────────────────────────

async function loadData() {
  const [terms, expert] = await Promise.all([
    fetch('./data/terms.json').then(r => r.json()),
    fetch('./data/expert_review.json').then(r => r.json())
  ]);
  allTerms = terms;
  expertTerms = expert;
  fuse = new Fuse(allTerms, FUSE_OPTIONS);
  render();
}

// ─── Render ───────────────────────────────────────────────────────────────────

function render(query = '', filter = 'all') {
  const container = document.getElementById('terms-container');
  const expertContainer = document.getElementById('expert-container');
  const expertSection = document.getElementById('expert-section');
  const countEl = document.getElementById('search-count');

  let results = allTerms;

  // Search
  if (query.length >= 2) {
    results = fuse.search(query).map(r => r.item);
  }

  // Filter by category
  if (filter !== 'all') {
    results = results.filter(t => t.category === filter);
  }

  // Group by category
  const grouped = {};
  results.forEach(t => {
    if (!grouped[t.category]) grouped[t.category] = [];
    grouped[t.category].push(t);
  });

  // Render main terms
  const categoryOrder = ['stat', 'tactic', 'rule', 'position'];
  let html = '';
  let total = 0;

  categoryOrder.forEach(cat => {
    if (!grouped[cat] || grouped[cat].length === 0) return;
    const terms = grouped[cat];
    total += terms.length;

    html += `
      <h2>
        <span class="ic ${cat}">${CATEGORY_ICONS[cat]}</span>
        ${CATEGORY_LABELS[cat] || cat}
      </h2>
      <p class="sub">${getCategorySubtitle(cat)}</p>
    `;

    terms.forEach(t => {
      html += renderTermCard(t, query);
    });
  });

  if (total === 0) {
    html = `
      <div class="empty">
        <div class="emoji">🏒</div>
        <p>По запросу «${escapeHtml(query)}» ничего не найдено</p>
      </div>
    `;
  }

  container.innerHTML = html;

  // Count
  countEl.textContent = query || filter !== 'all'
    ? `Найдено: ${total} из ${allTerms.length}`
    : `${allTerms.length} терминов`;

  // Expert section — hide during search/filter
  const showExpert = !query && filter === 'all';
  expertSection.style.display = showExpert ? '' : 'none';

  if (showExpert && expertTerms.length > 0) {
    expertContainer.innerHTML = expertTerms.map(t => renderExpertCard(t)).join('');
  }
}

function renderTermCard(t, query = '') {
  const abbrs = t.abbr && t.abbr.length > 0
    ? `<span class="abbr">${escapeHtml(t.abbr.join(' · '))}</span>`
    : '';

  const slang = t.ru_slang
    ? `<div class="sleng"><span class="l">В разговоре</span>${escapeHtml(t.ru_slang)}</div>`
    : '';

  return `
    <div class="term" data-cat="${t.category}" data-id="${t.id}">
      <div class="head">
        <span class="en">${escapeHtml(t.en)}</span>
        ${abbrs}
      </div>
      <div class="ru"><span class="arrow">→</span> ${escapeHtml(t.ru)}</div>
      <div class="def">${escapeHtml(t.definition)}</div>
      ${slang}
    </div>
  `;
}

function renderExpertCard(t) {
  const slang = t.ru_slang
    ? `<div class="ru-sl">«${escapeHtml(t.ru_slang)}»</div>`
    : '';

  return `
    <div class="exp-card">
      <div class="en">${escapeHtml(t.en)}</div>
      <div class="status">⚠ требует проверки с экспертом</div>
      ${slang}
      <div class="guess">${escapeHtml(t.definition)}</div>
    </div>
  `;
}

function getCategorySubtitle(cat) {
  const subtitles = {
    stat: 'То, что видишь в таблицах. Сокращение — чтобы ориентироваться по буквам.',
    tactic: 'Системы и приёмы игры. Понять — значит видеть хоккей иначе.',
    rule: 'Официальные правила и ситуации на льду.',
    position: 'Роли и позиции игроков.'
  };
  return subtitles[cat] || '';
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

// ─── Event listeners ──────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Search input
  const searchInput = document.getElementById('search');
  let debounceTimer;

  searchInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      render(searchInput.value.trim(), activeFilter);
    }, 180);
  });

  // Filter chips
  document.querySelectorAll('.chip[data-filter]').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.chip[data-filter]').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.dataset.filter;
      render(searchInput.value.trim(), activeFilter);
    });
  });

  // Load data
  loadData().catch(err => {
    document.getElementById('terms-container').innerHTML = `
      <div class="empty">
        <div class="emoji">⚠️</div>
        <p>Не удалось загрузить данные. Открой через локальный сервер, не через file://.</p>
      </div>
    `;
    console.error('Failed to load data:', err);
  });
});
