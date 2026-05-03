const pageName = document.body.dataset.page;

async function apiRequest(path, options = {}) {
  const headers = options.headers || {};
  const response = await fetch(path, {
    credentials: 'include',
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = { success: false, error: `Request failed with ${response.status}` };
  }
  if (response.status === 401 && pageName !== 'login') {
    window.location.href = '/';
    return Promise.reject(new Error('Authentication required'));
  }
  if (!response.ok || payload.success === false) {
    throw new Error(payload.error || `Request failed with ${response.status}`);
  }
  return payload;
}

function setMessage(element, message, tone = '') {
  if (!element) return;
  element.textContent = message || '';
  element.dataset.tone = tone;
}

async function requireUser() {
  const data = await apiRequest('/api/auth/me');
  return data.user;
}

function setupLogout() {
  const logoutBtn = document.getElementById('logoutBtn');
  if (!logoutBtn) return;
  logoutBtn.addEventListener('click', async () => {
    await apiRequest('/api/auth/logout', { method: 'POST' });
    window.location.href = '/';
  });
}

function setupLoginPage() {
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  const message = document.getElementById('authMessage');
  const tabs = Array.from(document.querySelectorAll('.auth-tab'));

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const mode = tab.dataset.authMode;
      tabs.forEach(item => item.classList.toggle('active', item === tab));
      loginForm.classList.toggle('hidden', mode !== 'login');
      registerForm.classList.toggle('hidden', mode !== 'register');
      setMessage(message, '');
    });
  });

  loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setMessage(message, 'Signing in...');
    try {
      await apiRequest('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          username: document.getElementById('loginUsername').value,
          password: document.getElementById('loginPassword').value,
        }),
      });
      window.location.href = '/home.html';
    } catch (error) {
      setMessage(message, error.message, 'error');
    }
  });

  registerForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setMessage(message, 'Creating account...');
    try {
      await apiRequest('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          username: document.getElementById('registerUsername').value,
          display_name: document.getElementById('registerDisplayName').value,
          email: document.getElementById('registerEmail').value,
          password: document.getElementById('registerPassword').value,
        }),
      });
      window.location.href = '/home.html';
    } catch (error) {
      setMessage(message, error.message, 'error');
    }
  });

  apiRequest('/api/auth/me')
    .then(() => {
      window.location.href = '/home.html';
    })
    .catch(() => {});
}

async function setupHomePage() {
  setupLogout();
  const user = await requireUser();
  const welcome = document.getElementById('welcomeTitle');
  welcome.textContent = `Welcome, ${user.display_name || user.username}`;
}

async function setupUserInfoPage() {
  setupLogout();
  const user = await requireUser();
  const form = document.getElementById('userInfoForm');
  const message = document.getElementById('profileMessage');
  document.getElementById('profileUsername').value = user.username || '';
  document.getElementById('profileDisplayName').value = user.display_name || '';
  document.getElementById('profileEmail').value = user.email || '';

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    setMessage(message, 'Saving...');
    try {
      const data = await apiRequest('/api/user', {
        method: 'PUT',
        body: JSON.stringify({
          display_name: document.getElementById('profileDisplayName').value,
          email: document.getElementById('profileEmail').value,
        }),
      });
      document.getElementById('profileDisplayName').value = data.user.display_name || '';
      document.getElementById('profileEmail').value = data.user.email || '';
      setMessage(message, 'Saved.', 'success');
    } catch (error) {
      setMessage(message, error.message, 'error');
    }
  });
}

async function setupProgressPage() {
  setupLogout();
  await requireUser();

  const list = document.getElementById('progressList');
  const count = document.getElementById('progressCount');
  const message = document.getElementById('progressMessage');
  const loadMore = document.getElementById('loadMoreProgress');
  const sentinel = document.getElementById('progressSentinel');
  const state = { offset: 0, limit: 12, loading: false, hasMore: true, total: 0 };

  async function loadNextPage() {
    if (state.loading || !state.hasMore) return;
    state.loading = true;
    setMessage(message, 'Loading...');
    try {
      const data = await apiRequest(`/api/progress?limit=${state.limit}&offset=${state.offset}`);
      state.total = data.total;
      state.hasMore = data.has_more;
      state.offset += data.items.length;
      data.items.forEach(problem => list.appendChild(renderProblem(problem)));
      count.textContent = `${state.offset} of ${state.total} problems loaded`;
      loadMore.classList.toggle('hidden', !state.hasMore);
      setMessage(message, state.offset ? '' : 'No problems are available yet.');
    } catch (error) {
      setMessage(message, error.message, 'error');
    } finally {
      state.loading = false;
    }
  }

  loadMore.addEventListener('click', loadNextPage);
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        loadNextPage();
      }
    }, { rootMargin: '300px' });
    observer.observe(sentinel);
  }

  await loadNextPage();
}

function renderProblem(problem) {
  const article = document.createElement('article');
  article.className = 'problem-item';

  const problemLink = document.createElement('a');
  problemLink.className = 'problem-main-link';
  problemLink.href = `/whiteboard.html?problem_id=${encodeURIComponent(problem.id)}`;

  const image = document.createElement('img');
  image.src = problem.image_url;
  image.alt = '';
  const text = document.createElement('span');
  const title = document.createElement('strong');
  title.textContent = problem.title || problem.id;
  const meta = document.createElement('small');
  meta.textContent = problem.category || 'problem';
  text.appendChild(title);
  text.appendChild(meta);
  problemLink.appendChild(image);
  problemLink.appendChild(text);

  const draftRow = document.createElement('div');
  draftRow.className = 'solution-row';
  const draftLabel = document.createElement('span');
  draftLabel.className = 'solution-label';
  draftLabel.textContent = 'drafts:';
  draftRow.appendChild(draftLabel);

  const draftSolutions = Array.isArray(problem.draft_solutions) ? problem.draft_solutions : [];
  if (draftSolutions.length) {
    draftSolutions.forEach(solution => {
      const draftLink = document.createElement('a');
      draftLink.href = `/whiteboard.html?solution_id=${encodeURIComponent(solution.id)}`;
      draftLink.className = 'solution-link draft-solution';
      draftLink.textContent = solution.title || solution.id;
      draftRow.appendChild(draftLink);
    });
  } else {
    const emptyDraft = document.createElement('span');
    emptyDraft.className = 'empty-solution';
    emptyDraft.textContent = 'no draft';
    draftRow.appendChild(emptyDraft);
  }

  const solutions = document.createElement('div');
  solutions.className = 'solution-row';
  const label = document.createElement('span');
  label.className = 'solution-label';
  label.textContent = 'scores:';
  solutions.appendChild(label);

  const gradedSolutions = Array.isArray(problem.final_solutions) ? problem.final_solutions : [];
  if (!gradedSolutions.length) {
    const empty = document.createElement('span');
    empty.className = 'empty-solution';
    empty.textContent = 'no score';
    solutions.appendChild(empty);
  } else {
    gradedSolutions.forEach(solution => {
      const link = document.createElement('a');
      link.href = `/whiteboard.html?solution_id=${encodeURIComponent(solution.id)}`;
      const scoreText = solution.score !== undefined && solution.score !== null
        ? ` (${solution.score}/${solution.max_score || 100})`
        : '';
      link.textContent = `${solution.title || solution.id}${scoreText}`;
      link.className = solution.source_kind === 'user' ? 'solution-link user-solution' : 'solution-link';
      solutions.appendChild(link);
    });
  }

  article.appendChild(problemLink);
  article.appendChild(draftRow);
  article.appendChild(solutions);
  return article;
}

const setupByPage = {
  login: setupLoginPage,
  home: setupHomePage,
  user_info: setupUserInfoPage,
  progress: setupProgressPage,
};

if (setupByPage[pageName]) {
  setupByPage[pageName]().catch(error => {
    const message = document.querySelector('.form-message');
    setMessage(message, error.message, 'error');
  });
}
