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

  async function refreshProgress() {
    state.offset = 0;
    state.hasMore = true;
    list.innerHTML = '';
    await loadNextPage();
  }

  async function loadNextPage() {
    if (state.loading || !state.hasMore) return;
    state.loading = true;
    setMessage(message, 'Loading...');
    try {
      const data = await apiRequest(`/api/progress?limit=${state.limit}&offset=${state.offset}`);
      state.total = data.total;
      state.hasMore = data.has_more;
      state.offset += data.items.length;
      data.items.forEach(problem => list.appendChild(renderProblem(problem, refreshProgress)));
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

function scoreLabel(solution) {
  const scoreText = solution.score !== undefined && solution.score !== null
    ? `${solution.score}/${solution.max_score || 100}`
    : 'score';
  return scoreText;
}

function createSolutionChip(solution, label, className, options = {}) {
  const chip = document.createElement('span');
  chip.className = 'solution-chip';

  const link = document.createElement('a');
  link.href = `/whiteboard.html?solution_id=${encodeURIComponent(solution.id)}`;
  link.className = className;
  link.textContent = label;
  chip.appendChild(link);

  if (options.onDelete) {
    const deleteButton = document.createElement('button');
    deleteButton.type = 'button';
    deleteButton.className = 'delete-solution';
    deleteButton.setAttribute('aria-label', options.deleteLabel || `Delete ${label}`);
    deleteButton.title = options.deleteTitle || 'Delete';
    deleteButton.textContent = 'x';
    deleteButton.addEventListener('click', async () => {
      if (options.confirmMessage && !window.confirm(options.confirmMessage)) return;
      deleteButton.disabled = true;
      try {
        await apiRequest(`/api/solutions/${encodeURIComponent(solution.id)}`, { method: 'DELETE' });
        await options.onDelete();
      } catch (error) {
        deleteButton.disabled = false;
        window.alert(error.message);
      }
    });
    chip.appendChild(deleteButton);
  }

  return chip;
}

function feedbackLabel(feedback) {
  const rating = feedback.rating === 'right' ? 'right' : 'wrong';
  const text = (feedback.feedback_text || '').trim();
  if (!text) return rating;
  return `${rating}: ${text.length > 48 ? `${text.slice(0, 48)}...` : text}`;
}

function createFeedbackChip(feedback, onRefresh) {
  const chip = document.createElement('span');
  chip.className = `feedback-chip ${feedback.rating === 'right' ? 'feedback-chip-right' : 'feedback-chip-wrong'}`;
  const label = document.createElement('a');
  label.href = `/whiteboard.html?solution_id=${encodeURIComponent(feedback.score_solution_id)}&feedback_id=${encodeURIComponent(feedback.id)}`;
  label.className = 'feedback-label';
  label.title = feedback.feedback_text || feedback.rating;
  label.textContent = feedbackLabel(feedback);
  chip.appendChild(label);

  const deleteButton = document.createElement('button');
  deleteButton.type = 'button';
  deleteButton.className = 'delete-solution delete-feedback';
  deleteButton.setAttribute('aria-label', `Delete ${feedback.rating} feedback`);
  deleteButton.title = 'Delete feedback';
  deleteButton.textContent = 'x';
  deleteButton.addEventListener('click', async () => {
    if (!window.confirm('Delete this feedback?')) return;
    deleteButton.disabled = true;
    try {
      await apiRequest(`/api/score-feedback/${encodeURIComponent(feedback.id)}`, { method: 'DELETE' });
      await onRefresh();
    } catch (error) {
      deleteButton.disabled = false;
      window.alert(error.message);
    }
  });
  chip.appendChild(deleteButton);
  return chip;
}

function createFeedbackRow(score, onRefresh) {
  const row = document.createElement('div');
  row.className = 'solution-row feedback-child-row';
  const label = document.createElement('span');
  label.className = 'solution-label';
  label.textContent = 'feedback';
  row.appendChild(label);

  const feedbackItems = Array.isArray(score.feedback_items) ? score.feedback_items : [];
  if (feedbackItems.length) {
    feedbackItems.forEach(feedback => {
      row.appendChild(createFeedbackChip(feedback, onRefresh));
    });
  } else {
    const empty = document.createElement('span');
    empty.className = 'empty-solution';
    empty.textContent = 'no feedback';
    row.appendChild(empty);
  }
  return row;
}

function renderProblem(problem, onRefresh) {
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

  const draftSolutions = Array.isArray(problem.draft_solutions) ? problem.draft_solutions : [];
  const unattachedScores = Array.isArray(problem.unattached_scores) ? problem.unattached_scores : [];
  const draftTree = document.createElement('div');
  draftTree.className = 'draft-score-tree';

  if (draftSolutions.length) {
    draftSolutions.forEach(draft => {
      const draftGroup = document.createElement('div');
      draftGroup.className = 'draft-score-group';

      const draftRow = document.createElement('div');
      draftRow.className = 'solution-row draft-parent-row';
      const draftLabel = document.createElement('span');
      draftLabel.className = 'solution-label';
      draftLabel.textContent = 'draft';
      draftRow.appendChild(draftLabel);
      draftRow.appendChild(createSolutionChip(
        draft,
        draft.title || draft.id,
        'solution-link draft-solution',
        {
          onDelete: onRefresh,
          deleteLabel: `Delete draft ${draft.title || draft.id}`,
          deleteTitle: 'Delete draft and its scores',
          confirmMessage: 'Delete this draft and all scores that belong to it?',
        },
      ));
      draftGroup.appendChild(draftRow);

      const scores = Array.isArray(draft.score_solutions) ? draft.score_solutions : [];
      const scoreList = document.createElement('div');
      scoreList.className = 'score-list';

      if (scores.length) {
        scores.forEach(score => {
          const scoreGroup = document.createElement('div');
          scoreGroup.className = 'score-feedback-group';
          const scoreLine = document.createElement('div');
          scoreLine.className = 'solution-row score-tree-row';
          const scoreLabelElement = document.createElement('span');
          scoreLabelElement.className = 'solution-label';
          scoreLabelElement.textContent = 'score';
          scoreLine.appendChild(scoreLabelElement);
          scoreLine.appendChild(createSolutionChip(
            score,
            scoreLabel(score),
            'solution-link user-solution',
            {
              onDelete: onRefresh,
              deleteLabel: `Delete score ${scoreLabel(score)}`,
              deleteTitle: 'Delete score',
              confirmMessage: 'Delete this score?',
            },
          ));
          scoreGroup.appendChild(scoreLine);
          scoreGroup.appendChild(createFeedbackRow(score, onRefresh));
          scoreList.appendChild(scoreGroup);
        });
      } else {
        const scoreRow = document.createElement('div');
        scoreRow.className = 'score-tree-row';
        const scoreLabelElement = document.createElement('span');
        scoreLabelElement.className = 'solution-label';
        scoreLabelElement.textContent = 'score';
        scoreRow.appendChild(scoreLabelElement);
        const emptyScore = document.createElement('span');
        emptyScore.className = 'empty-solution';
        emptyScore.textContent = 'no score';
        scoreRow.appendChild(emptyScore);
        scoreList.appendChild(scoreRow);
      }

      draftGroup.appendChild(scoreList);
      draftTree.appendChild(draftGroup);
    });
  } else {
    const emptyDraft = document.createElement('span');
    emptyDraft.className = 'empty-solution solution-row';
    emptyDraft.textContent = 'no draft';
    draftTree.appendChild(emptyDraft);
  }

  if (unattachedScores.length) {
    const orphanRow = document.createElement('div');
    orphanRow.className = 'unattached-score-row';
    const orphanLabel = document.createElement('span');
    orphanLabel.className = 'solution-label';
    orphanLabel.textContent = 'scores without draft';
    orphanRow.appendChild(orphanLabel);
    const scoreList = document.createElement('div');
    scoreList.className = 'score-list';
    unattachedScores.forEach(score => {
      const scoreGroup = document.createElement('div');
      scoreGroup.className = 'score-feedback-group';
      const scoreLine = document.createElement('div');
      scoreLine.className = 'solution-row score-tree-row';
      const scoreLabelElement = document.createElement('span');
      scoreLabelElement.className = 'solution-label';
      scoreLabelElement.textContent = 'score';
      scoreLine.appendChild(scoreLabelElement);
      scoreLine.appendChild(createSolutionChip(
        score,
        scoreLabel(score),
        'solution-link user-solution',
        {
          onDelete: onRefresh,
          deleteLabel: `Delete score ${scoreLabel(score)}`,
          deleteTitle: 'Delete score',
          confirmMessage: 'Delete this score?',
        },
      ));
      scoreGroup.appendChild(scoreLine);
      scoreGroup.appendChild(createFeedbackRow(score, onRefresh));
      scoreList.appendChild(scoreGroup);
    });
    orphanRow.appendChild(scoreList);
    draftTree.appendChild(orphanRow);
  }

  article.appendChild(problemLink);
  article.appendChild(draftTree);
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
