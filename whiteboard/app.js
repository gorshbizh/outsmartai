/**
 * Handwriting Board - Portable JS Webapp
 * License: MIT
 * Features:
 * - Pointer events (mouse, touch, pen) with pressure support
 * - Pen and eraser tools
 * - Adjustable color and size
 * - Undo/redo stack
 * - Clear board
 * - Save drafts to server
 * - High-DPI crisp rendering with devicePixelRatio scaling
 * - Responsive canvas that preserves drawing on resize
 */

/* Elements */
const canvas = document.getElementById('board');
const container = document.getElementById('board-container');
const boardSurface = document.getElementById('board-surface');
const floatingToolbar = document.getElementById('floating-toolbar');
const toolbarDragHandle = document.getElementById('toolbar-drag-handle');
const toolbarCollapseBtn = document.getElementById('toolbar-collapse');
const toolbarContent = document.getElementById('toolbar-content');
const colorInput = document.getElementById('color');
const sizeInput = document.getElementById('size');
const sizeVal = document.getElementById('sizeVal');
const undoBtn = document.getElementById('undo');
const redoBtn = document.getElementById('redo');
const clearBtn = document.getElementById('clear');
const saveToServerBtn = document.getElementById('saveToServer');
const gradeSolutionBtn = document.getElementById('gradeSolution');
const analyzeBtn = document.getElementById('analyze-btn');
const toolPen = document.getElementById('tool-pen');
const toolEraser = document.getElementById('tool-eraser');
const bgColorInput = document.getElementById('bgColor');
const ossLink = document.getElementById('ossLink');
const logoutBtn = document.getElementById('logoutBtn');
const contextTitle = document.getElementById('context-title');
const problemReference = document.getElementById('problem-reference');
const problemImage = document.getElementById('problem-image');
const solutionReferencePanel = document.getElementById('solution-reference-panel');
const solutionImage = document.getElementById('solution-image');

// Results panel elements
const resultsPanel = document.getElementById('results-panel');
const resultsTitle = document.getElementById('results-title');
const closeResultsBtn = document.getElementById('close-results');
const resultsLoading = document.getElementById('results-loading');
const resultsData = document.getElementById('results-data');
const resultsError = document.getElementById('results-error');
const textRecognition = document.getElementById('text-recognition');
const visualElements = document.getElementById('visual-elements');
const contentAnalysis = document.getElementById('content-analysis');
const suggestionsList = document.getElementById('suggestions-list');
const confidenceFill = document.getElementById('confidence-fill');
const confidenceText = document.getElementById('confidence-text');
const gradingDialog = document.getElementById('grading-dialog');
const gradingBackdrop = document.getElementById('grading-backdrop');
const gradingScore = document.getElementById('grading-score');
const gradingSummary = document.getElementById('grading-summary');
const gradingMajorList = document.getElementById('grading-major-list');
const gradingMinorList = document.getElementById('grading-minor-list');
const gradingStepList = document.getElementById('grading-step-list');
const gradingConfidenceFill = document.getElementById('grading-confidence-fill');
const gradingConfidenceText = document.getElementById('grading-confidence-text');
const gradingStream = document.getElementById('grading-stream');
const scoreFeedbackHistory = document.getElementById('score-feedback-history');
const rightGradingBtn = document.getElementById('right-grading-btn');
const wrongGradingBtn = document.getElementById('wrong-grading-btn');
const scoreFeedbackForm = document.getElementById('score-feedback-form');
const scoreFeedbackText = document.getElementById('score-feedback-text');
const scoreFeedbackMessage = document.getElementById('score-feedback-message');
const solutionBrowser = document.getElementById('solution-browser');
const whiteboardDraftList = document.getElementById('whiteboard-draft-list');
const whiteboardFinalList = document.getElementById('whiteboard-final-list');
const saveDraftDialog = document.getElementById('save-draft-dialog');
const closeSaveDraftBtn = document.getElementById('close-save-draft');
const cancelSaveDraftBtn = document.getElementById('cancel-save-draft');
const saveDraftForm = document.getElementById('save-draft-form');
const draftNameInput = document.getElementById('draft-name-input');
const saveDraftHelper = document.getElementById('save-draft-helper');

ossLink.href = 'https://opensource.org/license/mit';
ossLink.textContent = 'Open Source (MIT)';

/* Canvas 2D Context */
const ctx = canvas.getContext('2d', { alpha: true, desynchronized: true, willReadFrequently: false });

/* State */
let dpr = Math.max(1, window.devicePixelRatio || 1);
let isDrawing = false;
let activeDrawingPointerId = null;
let activeDrawingPointerType = null;
let lastPenInputAt = 0;
let lastPoint = null;
let currentStroke = null;
let needsFullRedraw = true;
let bgColor = bgColorInput ? bgColorInput.value : '#ffffff';
canvas.style.backgroundColor = bgColor;
let currentProblem = null;
let currentSolution = null;
let currentUserSolutionId = null;
let selectedGradedSolution = null;
let availableSolutions = [];
let availableDraftSolutions = [];
let availableFinalSolutions = [];
let isSavingSolution = false;
let isSubmittingGrade = false;
let readOnlyMode = false;
let paperImage = null;
let paperImageSource = null;
let gradingLiveLine = null;
let activeScoreSolution = null;
let pendingScoreFeedbackRating = null;
let scoreInteractionLog = [];
let requestedFeedbackId = null;
let boardDisplayScale = 1;

// Fixed canvas dimensions (set once at page load)
let fixedCanvasWidth = 0;
let fixedCanvasHeight = 0;

/* History stacks */
const strokeHistory = [];      // Array<Stroke>
const redoStack = [];    // Array<Stroke>
const textBoxes = [];

/* Stroke structure:
{
  tool: 'pen' | 'eraser',
  color: string,
  size: number,
  points: Array<{x:number,y:number,p:number}> // x/y in CSS pixels, p = pressure (0..1)
}
*/

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'include',
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = { success: false, error: `Request failed with ${response.status}` };
  }
  if (response.status === 401) {
    window.location.href = '/';
    throw new Error('Authentication required');
  }
  if (!response.ok || payload.success === false) {
    throw new Error(payload.error || `Request failed with ${response.status}`);
  }
  return payload;
}

if (logoutBtn) {
  logoutBtn.addEventListener('click', async () => {
    await apiRequest('/api/auth/logout', { method: 'POST' });
    window.location.href = '/';
  });
}

/* Utilities */
function getCanvasViewportSize() {
  const rect = container.getBoundingClientRect();
  return {
    width: Math.max(1, Math.floor(rect.width) || 800),
    height: Math.max(1, Math.floor(rect.height) || 600),
  };
}

function getAdaptivePaperSize(img) {
  const maxLongEdge = 1600;
  const longEdge = Math.max(img.naturalWidth, img.naturalHeight);
  const scale = longEdge > maxLongEdge ? maxLongEdge / longEdge : 1;
  return {
    width: Math.max(1, Math.round(img.naturalWidth * scale)),
    height: Math.max(1, Math.round(img.naturalHeight * scale)),
  };
}

function updateBoardSurfaceScale() {
  if (!fixedCanvasWidth || !fixedCanvasHeight || !boardSurface) return;
  const viewportSize = getCanvasViewportSize();
  boardDisplayScale = Math.min(
    viewportSize.width / fixedCanvasWidth,
    viewportSize.height / fixedCanvasHeight
  ) || 1;

  const displayWidth = fixedCanvasWidth * boardDisplayScale;
  const displayHeight = fixedCanvasHeight * boardDisplayScale;
  boardSurface.style.width = `${fixedCanvasWidth}px`;
  boardSurface.style.height = `${fixedCanvasHeight}px`;
  boardSurface.style.transform = `translate(${Math.max(0, (viewportSize.width - displayWidth) / 2)}px, ${Math.max(0, (viewportSize.height - displayHeight) / 2)}px) scale(${boardDisplayScale})`;
}

function setCanvasSize(force = false) {
  // Set fixed dimensions only once at page load
  if (force || fixedCanvasWidth === 0 || fixedCanvasHeight === 0) {
    if (!paperImage) {
      const viewportSize = getCanvasViewportSize();
      fixedCanvasWidth = viewportSize.width;
      fixedCanvasHeight = viewportSize.height;
    }
  }
  
  dpr = Math.max(1, window.devicePixelRatio || 1);

  // Set canvas to fixed dimensions
  canvas.width = Math.floor(fixedCanvasWidth * dpr);
  canvas.height = Math.floor(fixedCanvasHeight * dpr);
  canvas.style.width = fixedCanvasWidth + 'px';
  canvas.style.height = fixedCanvasHeight + 'px';
  updateBoardSurfaceScale();

  ctx.setTransform(1, 0, 0, 1, 0, 0); // reset
  ctx.scale(dpr, dpr);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  fullRedraw();
  textBoxes.forEach(updateTextBoxBounds);
}

function getPos(evt) {
  const rect = canvas.getBoundingClientRect();
  let x, y, p = 0.5;

  if (typeof PointerEvent !== 'undefined' && evt instanceof PointerEvent) {
    x = (evt.clientX - rect.left) * (fixedCanvasWidth / rect.width);
    y = (evt.clientY - rect.top) * (fixedCanvasHeight / rect.height);
    p = evt.pressure && evt.pressure > 0 ? evt.pressure : (evt.pointerType === 'mouse' ? 0.5 : 0.5);
  } else if (evt.touches && evt.touches[0]) {
    x = (evt.touches[0].clientX - rect.left) * (fixedCanvasWidth / rect.width);
    y = (evt.touches[0].clientY - rect.top) * (fixedCanvasHeight / rect.height);
    p = 0.5;
  } else {
    x = 0; y = 0; p = 0.5;
  }

  return { x, y, p };
}

function preventCanvasGesture(evt) {
  if (evt.cancelable) {
    evt.preventDefault();
  }
}

function getPointerType(evt) {
  return evt.pointerType || 'mouse';
}

function isLikelyPalmTouch(evt) {
  if (getPointerType(evt) !== 'touch') return false;
  const contactSize = Math.max(Number(evt.width) || 0, Number(evt.height) || 0);
  return contactSize >= 28;
}

function shouldSuppressTouchForPen(evt) {
  if (getPointerType(evt) !== 'touch') return false;
  return isDrawing && activeDrawingPointerType === 'pen';
}

function resetActivePointer() {
  activeDrawingPointerId = null;
  activeDrawingPointerType = null;
}

function replaceBrowserUrl(url) {
  try {
    if (window.History?.prototype?.replaceState) {
      window.History.prototype.replaceState.call(window.history, null, '', url);
    } else {
      window.history.replaceState(null, '', url);
    }
  } catch (error) {
    console.warn('Draft saved, but the browser URL could not be updated.', error);
  }
}

function clampToolbarPosition(left, top) {
  if (!floatingToolbar) return { left, top };
  const rect = floatingToolbar.getBoundingClientRect();
  const margin = 8;
  const maxLeft = Math.max(margin, window.innerWidth - rect.width - margin);
  const maxTop = Math.max(margin, window.innerHeight - rect.height - margin);
  return {
    left: Math.min(Math.max(margin, left), maxLeft),
    top: Math.min(Math.max(margin, top), maxTop),
  };
}

function setToolbarPosition(left, top, persist = false) {
  if (!floatingToolbar) return;
  const next = clampToolbarPosition(left, top);
  floatingToolbar.style.left = `${next.left}px`;
  floatingToolbar.style.top = `${next.top}px`;
  floatingToolbar.style.right = 'auto';
  floatingToolbar.style.bottom = 'auto';
  if (persist) {
    localStorage.setItem('whiteboardToolbarPosition', JSON.stringify(next));
  }
}

function setToolbarCollapsed(collapsed, persist = false) {
  if (!floatingToolbar || !toolbarCollapseBtn || !toolbarContent) return;
  floatingToolbar.classList.toggle('is-collapsed', collapsed);
  toolbarCollapseBtn.textContent = collapsed ? 'Show' : 'Hide';
  toolbarCollapseBtn.setAttribute('aria-expanded', String(!collapsed));
  toolbarContent.setAttribute('aria-hidden', String(collapsed));
  if (persist) {
    localStorage.setItem('whiteboardToolbarCollapsed', collapsed ? 'true' : 'false');
  }
  window.requestAnimationFrame(() => {
    const rect = floatingToolbar.getBoundingClientRect();
    setToolbarPosition(rect.left, rect.top);
  });
}

function setupFloatingToolbar() {
  if (!floatingToolbar || !toolbarDragHandle || !toolbarCollapseBtn) return;

  const storedCollapsed = localStorage.getItem('whiteboardToolbarCollapsed');
  const defaultCollapsed = window.matchMedia('(max-width: 640px)').matches;
  setToolbarCollapsed(storedCollapsed === null ? defaultCollapsed : storedCollapsed === 'true');

  const storedPosition = localStorage.getItem('whiteboardToolbarPosition');
  if (storedPosition) {
    try {
      const position = JSON.parse(storedPosition);
      window.requestAnimationFrame(() => setToolbarPosition(Number(position.left) || 16, Number(position.top) || 86));
    } catch {
      localStorage.removeItem('whiteboardToolbarPosition');
    }
  }

  toolbarCollapseBtn.addEventListener('click', () => {
    setToolbarCollapsed(!floatingToolbar.classList.contains('is-collapsed'), true);
  });

  let isDraggingToolbar = false;
  let dragOffsetX = 0;
  let dragOffsetY = 0;

  toolbarDragHandle.addEventListener('pointerdown', (event) => {
    if (typeof event.button === 'number' && event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const rect = floatingToolbar.getBoundingClientRect();
    isDraggingToolbar = true;
    dragOffsetX = event.clientX - rect.left;
    dragOffsetY = event.clientY - rect.top;
    try {
      toolbarDragHandle.setPointerCapture(event.pointerId);
    } catch {}
  });

  toolbarDragHandle.addEventListener('pointermove', (event) => {
    if (!isDraggingToolbar) return;
    event.preventDefault();
    setToolbarPosition(event.clientX - dragOffsetX, event.clientY - dragOffsetY);
  });

  const finishToolbarDrag = (event) => {
    if (!isDraggingToolbar) return;
    isDraggingToolbar = false;
    try {
      toolbarDragHandle.releasePointerCapture(event.pointerId);
    } catch {}
    const rect = floatingToolbar.getBoundingClientRect();
    setToolbarPosition(rect.left, rect.top, true);
  };

  toolbarDragHandle.addEventListener('pointerup', finishToolbarDrag);
  toolbarDragHandle.addEventListener('pointercancel', finishToolbarDrag);

  const clampCurrentPosition = () => {
    if (!floatingToolbar.style.left || !floatingToolbar.style.top) return;
    const rect = floatingToolbar.getBoundingClientRect();
    setToolbarPosition(rect.left, rect.top, true);
  };
  window.addEventListener('resize', clampCurrentPosition);
  window.addEventListener('orientationchange', clampCurrentPosition);
}

function lerp(a, b, t) { return a + (b - a) * t; }

/* Smoothing: simple moving average with window=2 using lastPoint */
function smoothedPoint(prev, curr) {
  if (!prev) return curr;
  return {
    x: lerp(prev.x, curr.x, 0.5),
    y: lerp(prev.y, curr.y, 0.5),
    p: lerp(prev.p, curr.p, 0.5),
  };
}

/* Draw a stroke incrementally or full */
function drawStroke(stroke, incremental = false) {
  if (!stroke || stroke.points.length < 1) return;

  const isEraser = stroke.tool === 'eraser';
  ctx.save();
  ctx.globalCompositeOperation = isEraser ? 'destination-out' : 'source-over';
  ctx.strokeStyle = isEraser ? 'rgba(0,0,0,1)' : stroke.color;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  // Variable width by pressure
  const pressureWidth = (pt) => Math.max(0.5, stroke.size * (0.3 + 0.7 * (pt.p || 0.5)));

  if (stroke.points.length === 1) {
    const pt = stroke.points[0];
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, pressureWidth(pt) / 2, 0, Math.PI * 2);
    ctx.fillStyle = isEraser ? 'rgba(0,0,0,1)' : stroke.color;
    ctx.fill();
    ctx.restore();
    return;
  }

  if (incremental) {
    const n = stroke.points.length;
    if (n < 2) { ctx.restore(); return; }
    const a = stroke.points[n - 2];
    const b = stroke.points[n - 1];

    const sa = smoothedPoint(null, a);
    const sb = smoothedPoint(a, b);

    ctx.beginPath();
    ctx.moveTo(sa.x, sa.y);
    ctx.lineWidth = pressureWidth(sb);
    // Quadratic curve between points for smoother line
    const cx = (sa.x + sb.x) / 2;
    const cy = (sa.y + sb.y) / 2;
    ctx.quadraticCurveTo(sa.x, sa.y, cx, cy);
    ctx.quadraticCurveTo(cx, cy, sb.x, sb.y);
    ctx.stroke();
    ctx.restore();
    return;
  }

  // Full redraw for the stroke
  let prev = null;
  for (let i = 0; i < stroke.points.length; i++) {
    const curr = stroke.points[i];
    const sCurr = smoothedPoint(prev, curr);
    if (prev) {
      ctx.beginPath();
      ctx.moveTo(prev.x, prev.y);
      ctx.lineWidth = pressureWidth(sCurr);
      const cx = (prev.x + sCurr.x) / 2;
      const cy = (prev.y + sCurr.y) / 2;
      ctx.quadraticCurveTo(prev.x, prev.y, cx, cy);
      ctx.quadraticCurveTo(cx, cy, sCurr.x, sCurr.y);
      ctx.stroke();
    }
    prev = sCurr;
  }

  ctx.restore();
}

function fullRedraw() {
  // Clear
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.restore();

  // Re-apply scale
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  drawPaperImage();

  // Redraw all strokes
  for (const stroke of strokeHistory) {
    drawStroke(stroke, false);
  }
  needsFullRedraw = false;
  updateButtonsState();
}

function cancelActiveStroke() {
  if (!isDrawing) return;
  try {
    if (activeDrawingPointerId !== null) {
      canvas.releasePointerCapture(activeDrawingPointerId);
    }
  } catch {}
  isDrawing = false;
  currentStroke = null;
  lastPoint = null;
  resetActivePointer();
  fullRedraw();
}

function appendStrokePointFromEvent(evt) {
  const { x, y, p } = getPos(evt);

  // Previous point in the current stroke
  const prev = currentStroke.points[currentStroke.points.length - 1];

  // If no previous point (edge case), start with this one
  if (!prev) {
    const first = { x, y, p };
    currentStroke.points.push(first);
    drawStroke(currentStroke, true);
    lastPoint = first;
    return;
  }

  const dx = x - prev.x;
  const dy = y - prev.y;
  const dist = Math.hypot(dx, dy);
  if (dist < 0.05) {
    return;
  }

  // Densify points based on brush size to keep lines continuous even with low event rates
  const spacing = Math.max(0.5, currentStroke.size * 0.35);
  const steps = Math.floor(dist / spacing);

  if (steps > 0) {
    for (let i = 1; i <= steps; i++) {
      const t = i / (steps + 1);
      const ipt = { x: prev.x + dx * t, y: prev.y + dy * t, p: lerp(prev.p, p, t) };
      currentStroke.points.push(ipt);
      // Draw each interpolated segment to avoid gaps
      drawStroke(currentStroke, true);
    }
  }

  const pt = { x, y, p };
  currentStroke.points.push(pt);
  drawStroke(currentStroke, true);
  lastPoint = pt;
}

function appendFinalStrokePoint(evt) {
  if (!currentStroke || !currentStroke.points.length) return;
  appendStrokePointFromEvent(evt);
  if (currentStroke.points.length === 1) {
    drawStroke(currentStroke, true);
  }
}

function startStroke(evt) {
  if (isTextToolActive && isTextToolActive()) {
    return;
  }
  if (typeof evt.button === 'number' && evt.button !== 0) {
    return;
  }
  const pointerType = getPointerType(evt);
  preventCanvasGesture(evt);

  if (isDrawing && activeDrawingPointerId !== evt.pointerId) {
    if (pointerType === 'pen' && activeDrawingPointerType !== 'pen') {
      cancelActiveStroke();
    } else {
      return;
    }
  }

  if (shouldSuppressTouchForPen(evt)) {
    return;
  }

  try {
    canvas.setPointerCapture(evt.pointerId);
  } catch {}
  isDrawing = true;
  activeDrawingPointerId = evt.pointerId;
  activeDrawingPointerType = pointerType;
  if (pointerType === 'pen') {
    lastPenInputAt = Date.now();
  }
  redoStack.length = 0; // invalidate redo on new action

  const { x, y, p } = getPos(evt);
  lastPoint = { x, y, p };
  currentStroke = {
    tool: toolEraser.checked ? 'eraser' : 'pen',
    color: colorInput.value,
    size: Number(sizeInput.value),
    points: [lastPoint],
  };
  drawStroke(currentStroke, true);
}

function extendStroke(evt) {
  if (!isDrawing || !currentStroke) return;
  if (evt.pointerId !== activeDrawingPointerId) {
    if (getPointerType(evt) === 'touch') {
      preventCanvasGesture(evt);
    }
    return;
  }
  preventCanvasGesture(evt);
  if (activeDrawingPointerType === 'pen') {
    lastPenInputAt = Date.now();
  }

  const events = typeof evt.getCoalescedEvents === 'function' ? evt.getCoalescedEvents() : [evt];
  events.forEach(pointerEvent => appendStrokePointFromEvent(pointerEvent));
}

function endStroke(evt) {
  if (!isDrawing) return;
  if (evt.pointerId !== activeDrawingPointerId) {
    if (getPointerType(evt) === 'touch') {
      preventCanvasGesture(evt);
    }
    return;
  }
  preventCanvasGesture(evt);
  isDrawing = false;
  try {
    canvas.releasePointerCapture(evt.pointerId);
  } catch {}
  if (currentStroke && currentStroke.points.length > 0) {
    appendFinalStrokePoint(evt);
    strokeHistory.push(currentStroke);
  }
  currentStroke = null;
  lastPoint = null;
  resetActivePointer();
  updateButtonsState();
}

/* UI wiring */
sizeVal.textContent = `${sizeInput.value} px`;
sizeInput.addEventListener('input', () => {
  sizeVal.textContent = `${sizeInput.value} px`;
});

// Background color control
if (bgColorInput) {
  bgColorInput.addEventListener('input', () => {
    bgColor = bgColorInput.value;
    canvas.style.backgroundColor = bgColor;
    fullRedraw();
  });
}

undoBtn.addEventListener('click', () => {
  if (strokeHistory.length === 0) return;
  const s = strokeHistory.pop();
  redoStack.push(s);
  fullRedraw();
});

redoBtn.addEventListener('click', () => {
  if (redoStack.length === 0) return;
  const s = redoStack.pop();
  strokeHistory.push(s);
  fullRedraw();
});

/* ========== Typing Tool ========== */
const textToolLabel = document.createElement('label');
textToolLabel.innerHTML = '<input type="radio" name="tool" value="text" id="tool-text">Text';
document.querySelector('.toolbar .tool-group').appendChild(textToolLabel);

const toolTextInput = document.getElementById('tool-text');
let activeTextBox = null;
let textBoxCounter = 0;
let textBoxZIndex = 50;
const textMeasureCanvas = document.createElement('canvas');
const textMeasureCtx = textMeasureCanvas.getContext('2d');

// Create warning sound using Web Audio API
let audioContext = null;
function playWarningSound() {
  try {
    if (!audioContext) {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    
    // Create a brief warning beep
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    // High-pitched beep sound
    oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
    oscillator.frequency.setValueAtTime(600, audioContext.currentTime + 0.1);
    
    // Quick fade out
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.15);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.15);
  } catch (error) {
    // Fallback: system beep (if available)
    console.beep?.() || console.log('Text box boundary reached');
  }
}

function isTextToolActive() {
  return Boolean(toolTextInput && toolTextInput.checked);
}

function bringTextBoxToFront(box) {
  textBoxZIndex += 1;
  box.z = textBoxZIndex;
  box.element.style.zIndex = String(box.z);
}

function updateTextBoxBounds(box) {
  const left = parseFloat(box.element.style.left) || 0;
  const top = parseFloat(box.element.style.top) || 0;
  box.bounds = {
    left,
    top,
    right: left + box.element.offsetWidth,
    bottom: top + box.element.offsetHeight,
  };
}

function autoSizeTextBox(box) {
  const el = box.element;
  const style = window.getComputedStyle(el);

  el.style.height = 'auto';
  el.style.width = 'auto';

  const paddingX = (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0);
  const paddingY = (parseFloat(style.paddingTop) || 0) + (parseFloat(style.paddingBottom) || 0);
  const borderX = (parseFloat(style.borderLeftWidth) || 0) + (parseFloat(style.borderRightWidth) || 0);
  const baseFontSize = parseFloat(style.fontSize) || 16;
  const minWidth = box.minWidth || 80;
  const minHeight = box.minHeight || baseFontSize * 1.25 + paddingY;

  // Get fixed canvas dimensions and text box position
  const boxLeft = parseFloat(el.style.left) || 0;
  const boxTop = parseFloat(el.style.top) || 0;
  const maxWidth = fixedCanvasWidth - boxLeft - 10; // 10px margin from edge
  const maxHeight = fixedCanvasHeight - boxTop - 10; // 10px margin from edge

  let contentWidth = 0;
  if (textMeasureCtx) {
    const font = style.font || `${style.fontStyle} ${style.fontVariant} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`.trim();
    textMeasureCtx.font = font;
    const letterSpacing = parseFloat(style.letterSpacing) || 0;
    const lines = el.value.split(/\r?\n/);
    for (const line of lines) {
      const text = line === '' ? ' ' : line;
      const metrics = textMeasureCtx.measureText(text);
      const lineWidth = metrics.width + Math.max(0, text.length - 1) * letterSpacing;
      if (lineWidth > contentWidth) {
        contentWidth = lineWidth;
      }
    }
  } else {
    contentWidth = el.scrollWidth;
  }

  // Calculate desired dimensions
  const desiredWidth = Math.max(minWidth, Math.ceil(contentWidth + paddingX + borderX + 2));
  const desiredHeight = Math.max(minHeight, el.scrollHeight);

  // Constrain to canvas bounds
  const width = Math.min(desiredWidth, maxWidth);
  const height = Math.min(desiredHeight, maxHeight);

  el.style.height = `${height}px`;
  el.style.width = `${width}px`;

  // Store original and constrained sizes for input validation
  box._maxWidth = maxWidth;
  box._maxHeight = maxHeight;
  box._isConstrainedWidth = width < desiredWidth;
  box._isConstrainedHeight = height < desiredHeight;

  updateTextBoxBounds(box);
}

function setActiveTextBox(box) {
  if (activeTextBox && activeTextBox !== box) {
    activeTextBox.element.classList.remove('text-entry--active');
  }
  activeTextBox = box;
  if (box) {
    box.element.classList.add('text-entry--active');
    bringTextBoxToFront(box);
  }
}

function focusTextBox(box, moveCaretToEnd = false) {
  setActiveTextBox(box);
  box.element.focus();
  if (moveCaretToEnd) {
    const len = box.element.value.length;
    box.element.setSelectionRange(len, len);
  }
}

function updateTextBoxInteractivity() {
  const interactive = isTextToolActive();
  textBoxes.forEach(box => {
    box.element.classList.toggle('text-entry--interactive', interactive);
    box.element.classList.toggle('text-entry--readonly', !interactive);
  });
  canvas.style.cursor = interactive ? 'text' : 'crosshair';
}

function createTextBox(x, y, options = {}) {
  const textarea = document.createElement('textarea');
  textarea.className = 'text-entry';
  textarea.spellcheck = false;
  textarea.value = options.value || '';
  textarea.style.position = 'absolute';
  textarea.style.color = options.color || colorInput.value;

  const fontPx = options.fontSizePx || Number(sizeInput.value) * 5;
  textarea.style.fontSize = `${fontPx}px`;
  
  // Calculate minimum dimensions for the text box
  const minWidth = 80;
  const minHeight = Math.max(fontPx * 1.5, 32); // Ensure at least 32px height for typing
  const margin = 10; // Safety margin from canvas edges
  
  // Check if canvas is large enough for minimum text box size
  if (fixedCanvasWidth < minWidth + (margin * 2) || fixedCanvasHeight < minHeight + (margin * 2)) {
    console.warn('Canvas too small for text box minimum dimensions');
    // Use smaller margins if canvas is very small
    const adaptiveMargin = Math.min(margin, Math.floor(Math.min(fixedCanvasWidth, fixedCanvasHeight) * 0.05));
    const adaptiveMinWidth = Math.min(minWidth, fixedCanvasWidth - (adaptiveMargin * 2));
    const adaptiveMinHeight = Math.min(minHeight, fixedCanvasHeight - (adaptiveMargin * 2));
    
    const adjustedX = Math.min(x, fixedCanvasWidth - adaptiveMinWidth - adaptiveMargin);
    const adjustedY = Math.min(y, fixedCanvasHeight - adaptiveMinHeight - adaptiveMargin);
    const finalX = Math.max(adaptiveMargin, adjustedX);
    const finalY = Math.max(adaptiveMargin, adjustedY);
    
    textarea.style.left = `${finalX}px`;
    textarea.style.top = `${finalY}px`;
  } else {
    // Normal case: canvas is large enough
    const adjustedX = Math.min(x, fixedCanvasWidth - minWidth - margin);
    const adjustedY = Math.min(y, fixedCanvasHeight - minHeight - margin);
    
    // Ensure position is not negative
    const finalX = Math.max(margin, adjustedX);
    const finalY = Math.max(margin, adjustedY);
    
    // Additional check: if click is very close to bottom, move text box up more aggressively
    const distanceFromBottom = fixedCanvasHeight - y;
    const requiredSpace = minHeight + margin;
    
    let adjustedFinalY = finalY;
    if (distanceFromBottom < requiredSpace) {
      // Move text box up to ensure full height is available
      adjustedFinalY = Math.max(margin, fixedCanvasHeight - minHeight - margin);
    }
    
    textarea.style.left = `${finalX}px`;
    textarea.style.top = `${adjustedFinalY}px`;
  }

  const box = {
    id: `textbox-${++textBoxCounter}`,
    element: textarea,
    minWidth: minWidth,
    minHeight: minHeight,
    bounds: null,
    z: 0,
    _previousValue: '',
    _maxWidth: Infinity,
    _maxHeight: Infinity,
    _isConstrainedWidth: false,
    _isConstrainedHeight: false,
  };

  textarea.dataset.boxId = box.id;
  box._previousValue = textarea.value;

  textarea.addEventListener('input', (e) => {
    if (textarea.value.length === 0) {
      removeTextBox(box);
      return;
    }
    
    // Store current value before auto-sizing
    const currentValue = textarea.value;
    autoSizeTextBox(box);
    
    // Check if the text box hit size constraints and revert if necessary
    if (box._isConstrainedWidth || box._isConstrainedHeight) {
      // Get the content that would fit
      const style = window.getComputedStyle(textarea);
      const paddingY = (parseFloat(style.paddingTop) || 0) + (parseFloat(style.paddingBottom) || 0);
      const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.2;
      const maxLines = Math.floor((box._maxHeight - paddingY) / lineHeight);
      
      // If content doesn't fit, revert to previous value
      if (textarea.scrollWidth > textarea.clientWidth || textarea.scrollHeight > textarea.clientHeight) {
        e.preventDefault();
        playWarningSound();
        textarea.value = box._previousValue || '';
        autoSizeTextBox(box);
        return;
      }
      
      // For height constraint, limit number of lines
      if (box._isConstrainedHeight) {
        const lines = currentValue.split('\n');
        if (lines.length > maxLines) {
          playWarningSound();
          textarea.value = box._previousValue || '';
          autoSizeTextBox(box);
          return;
        }
      }
    }
    
    // Store valid value for future reference
    box._previousValue = textarea.value;
  });

  textarea.addEventListener('keydown', (e) => {
    // Allow navigation and deletion keys
    const allowedKeys = ['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'Tab'];
    if (allowedKeys.includes(e.key) || e.ctrlKey || e.metaKey) {
      return;
    }
    
    // Check if we're at size limits before allowing input
    autoSizeTextBox(box);
    if (box._isConstrainedWidth || box._isConstrainedHeight) {
      const style = window.getComputedStyle(textarea);
      const paddingY = (parseFloat(style.paddingTop) || 0) + (parseFloat(style.paddingBottom) || 0);
      const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.2;
      const maxLines = Math.floor((box._maxHeight - paddingY) / lineHeight);
      
      // Prevent typing if at width limit (except newlines)
      if (box._isConstrainedWidth && e.key !== 'Enter') {
        const testValue = textarea.value + e.key;
        const tempTextarea = document.createElement('textarea');
        tempTextarea.style.cssText = textarea.style.cssText;
        tempTextarea.style.position = 'absolute';
        tempTextarea.style.visibility = 'hidden';
        tempTextarea.value = testValue;
        document.body.appendChild(tempTextarea);
        
        if (tempTextarea.scrollWidth > box._maxWidth) {
          e.preventDefault();
          playWarningSound();
          document.body.removeChild(tempTextarea);
          return;
        }
        document.body.removeChild(tempTextarea);
      }
      
      // Prevent new lines if at height limit
      if (box._isConstrainedHeight && e.key === 'Enter') {
        const currentLines = textarea.value.split('\n').length;
        if (currentLines >= maxLines) {
          e.preventDefault();
          playWarningSound();
          return;
        }
      }
    }
  });

  textarea.addEventListener('focus', () => {
    setActiveTextBox(box);
  });

  textarea.addEventListener('blur', () => {
    if (activeTextBox === box) {
      activeTextBox = null;
    }
    textarea.classList.remove('text-entry--active');
  });

  textarea.addEventListener('pointerdown', () => {
    bringTextBoxToFront(box);
  });

  boardSurface.appendChild(textarea);
  textBoxes.push(box);
  bringTextBoxToFront(box);
  updateTextBoxInteractivity();
  autoSizeTextBox(box);
  updateButtonsState();
  return box;
}

function findTextBoxAt(x, y) {
  if (!textBoxes.length) return null;
  let candidate = null;
  let highestZ = -Infinity;
  for (const box of textBoxes) {
    updateTextBoxBounds(box);
    if (
      x >= box.bounds.left &&
      x <= box.bounds.right &&
      y >= box.bounds.top &&
      y <= box.bounds.bottom
    ) {
      if (box.z > highestZ) {
        highestZ = box.z;
        candidate = box;
      }
    }
  }
  return candidate;
}

if (toolTextInput) {
  toolTextInput.addEventListener('change', updateTextBoxInteractivity);
}
if (toolPen) {
  toolPen.addEventListener('change', updateTextBoxInteractivity);
}
if (toolEraser) {
  toolEraser.addEventListener('change', updateTextBoxInteractivity);
}

container.addEventListener('pointerdown', (evt) => {
  if (!isTextToolActive()) return;
  if (typeof evt.button === 'number' && evt.button !== 0) return;

  const pos = getPos(evt);
  const existing = findTextBoxAt(pos.x, pos.y);

  if (existing) {
    focusTextBox(existing);
    return;
  }

  if (evt.target !== canvas) return;

  // Check if canvas has enough space for a text box
  const fontPx = Number(sizeInput.value) * 5;
  const minRequiredWidth = 80 + 20; // min width + margins
  const minRequiredHeight = Math.max(fontPx * 1.5, 32) + 20; // min height + margins (ensure typing space)
  
  if (fixedCanvasWidth < minRequiredWidth || fixedCanvasHeight < minRequiredHeight) {
    console.warn('Canvas too small to create text boxes');
    return;
  }
  
  // Check if click position is too close to bottom edge for proper text box creation
  const minHeightNeeded = Math.max(fontPx * 1.5, 32);
  const marginNeeded = 10;
  const totalSpaceNeeded = minHeightNeeded + marginNeeded;
  
  if (pos.y > fixedCanvasHeight - totalSpaceNeeded) {
    console.log('Click too close to bottom edge - text box creation blocked');
    return;
  }
  
  // Check if click position is too close to right edge
  const minWidthNeeded = 80;
  const totalWidthNeeded = minWidthNeeded + marginNeeded;
  
  if (pos.x > fixedCanvasWidth - totalWidthNeeded) {
    console.log('Click too close to right edge - text box creation blocked');
    return;
  }

  evt.preventDefault();
  const newBox = createTextBox(pos.x, pos.y);
  focusTextBox(newBox, true);
});

function removeTextBox(box) {
  if (!box) return;
  const idx = textBoxes.indexOf(box);
  if (idx !== -1) {
    textBoxes.splice(idx, 1);
  }
  if (box.element && box.element.parentNode) {
    box.element.parentNode.removeChild(box.element);
  }
  if (activeTextBox === box) {
    activeTextBox = null;
  }
  updateTextBoxInteractivity();
  updateButtonsState();
}

function clearTextBoxes() {
  while (textBoxes.length) {
    removeTextBox(textBoxes[textBoxes.length - 1]);
  }
}

function resolveLineHeight(value, fontSizePx) {
  const size = Number.isFinite(fontSizePx) && fontSizePx > 0 ? fontSizePx : 16;
  if (!value || value === 'normal') {
    return size * 1.2;
  }
  if (value.endsWith('px')) {
    const px = parseFloat(value);
    return Number.isFinite(px) ? px : size * 1.2;
  }
  if (value.endsWith('%')) {
    const percent = parseFloat(value);
    return Number.isFinite(percent) ? size * (percent / 100) : size * 1.2;
  }
  if (value.endsWith('em')) {
    const em = parseFloat(value);
    return Number.isFinite(em) ? size * em : size * 1.2;
  }
  const numeric = parseFloat(value);
  if (Number.isFinite(numeric)) {
    if (value.trim() === `${numeric}`) {
      return size * numeric;
    }
    return numeric;
  }
  return size * 1.2;
}

function renderTextBoxesToContext(targetCtx) {
  if (!textBoxes.length) return;
  targetCtx.save();
  targetCtx.scale(dpr, dpr);
  textBoxes.forEach(box => {
    const el = box.element;
    if (!el) return;
    const style = window.getComputedStyle(el);
    const x = parseFloat(el.style.left) || 0;
    const y = parseFloat(el.style.top) || 0;
    const paddingLeft = parseFloat(style.paddingLeft) || 0;
    const paddingTop = parseFloat(style.paddingTop) || 0;
    const font = style.font || `${style.fontStyle || 'normal'} ${style.fontWeight || '400'} ${style.fontSize || '16px'} ${style.fontFamily || 'sans-serif'}`;
    targetCtx.font = font;
    targetCtx.fillStyle = style.color || '#000000';
    targetCtx.textBaseline = 'top';
    const fontSizePx = parseFloat(style.fontSize) || 16;
    const lineHeight = resolveLineHeight(style.lineHeight || '', fontSizePx);
    const lines = el.value.split('\n');
    lines.forEach((line, index) => {
      targetCtx.fillText(line, x + paddingLeft, y + paddingTop + index * lineHeight);
    });
  });
  targetCtx.restore();
}

function exportBoardDataUrl() {
  const tempCanvas = document.createElement('canvas');
  const tempCtx = tempCanvas.getContext('2d');
  tempCanvas.width = canvas.width;
  tempCanvas.height = canvas.height;
  tempCtx.fillStyle = bgColor || '#ffffff';
  tempCtx.fillRect(0, 0, tempCanvas.width, tempCanvas.height);
  tempCtx.drawImage(canvas, 0, 0);
  renderTextBoxesToContext(tempCtx);
  return tempCanvas.toDataURL('image/png', 0.9);
}

function serializeTextBoxes() {
  return textBoxes.map(box => {
    const el = box.element;
    const style = window.getComputedStyle(el);
    return {
      id: box.id,
      value: el.value,
      x: parseFloat(el.style.left) || 0,
      y: parseFloat(el.style.top) || 0,
      color: style.color || '#000000',
      font_size_px: parseFloat(style.fontSize) || 16,
      z: box.z,
    };
  });
}

function serializeCanvasData() {
  return {
    strokes: strokeHistory,
    text_boxes: serializeTextBoxes(),
    bg_color: bgColor,
    canvas_width: fixedCanvasWidth,
    canvas_height: fixedCanvasHeight,
    paper_image_source: paperImageSource,
  };
}

function scoreFromGradingPayload(solution, gradingResult = null) {
  const source = gradingResult?.result || gradingResult?.score || gradingResult || {};
  const score = source.total_score ?? source.total_points ?? source.score ?? solution?.score;
  const maxScore = source.max_score ?? source.max_points ?? solution?.max_score ?? (score !== undefined ? 100 : null);
  return { score, maxScore };
}

function isFinalSolution(solution = currentSolution) {
  return Boolean(solution && solution.solution_type === 'graded');
}

function updateSolutionActionState() {
  const isFinal = isFinalSolution();
  if (saveToServerBtn) {
    saveToServerBtn.disabled = !currentProblem || isSavingSolution || isSubmittingGrade;
    saveToServerBtn.textContent = isSavingSolution ? 'Saving...' : 'Save Draft';
  }
  if (gradeSolutionBtn) {
    gradeSolutionBtn.disabled = isSavingSolution || isSubmittingGrade || isFinal;
    gradeSolutionBtn.textContent = isSubmittingGrade ? 'Submitting...' : 'Submit for Grading';
  }
}

function solutionDisplayName(solution) {
  return solution?.title || solution?.id || 'Untitled';
}

function renderSolutionBrowser() {
  if (!solutionBrowser || !whiteboardDraftList || !whiteboardFinalList) return;
  whiteboardDraftList.innerHTML = '';
  whiteboardFinalList.innerHTML = '';

  const renderGroup = (container, solutions, emptyMessage) => {
    if (!Array.isArray(solutions) || solutions.length === 0) {
      const empty = document.createElement('span');
      empty.className = 'empty-solution';
      empty.textContent = emptyMessage;
      container.appendChild(empty);
      return;
    }

    solutions.forEach(solution => {
      const link = document.createElement('a');
      link.href = `/whiteboard.html?solution_id=${encodeURIComponent(solution.id)}`;
      link.className = `solution-link ${solution.solution_type === 'draft' ? 'draft-solution' : 'user-solution'}`;
      if (currentSolution && solution.id === currentSolution.id) {
        link.classList.add('active');
      }
      const scoreText = solution.solution_type === 'graded' && solution.score !== undefined && solution.score !== null
        ? ` (${solution.score}/${solution.max_score || 100})`
        : '';
      link.textContent = `${solutionDisplayName(solution)}${scoreText}`;
      container.appendChild(link);
    });
  };

  renderGroup(whiteboardDraftList, availableDraftSolutions, 'No drafts yet.');
  renderGroup(whiteboardFinalList, availableFinalSolutions, 'No finals yet.');
}

function currentDraftName() {
  return solutionDisplayName(currentSolution) || `Draft for ${currentProblem?.title || currentProblem?.id || 'problem'}`;
}

function openSaveDraftDialog() {
  if (!saveDraftDialog || !draftNameInput) return;
  const defaultName = currentDraftName();
  draftNameInput.value = defaultName;
  if (saveDraftHelper) {
    saveDraftHelper.textContent = isFinalSolution()
      ? 'This will create a new draft branched from the current final solution.'
      : 'Leave the name unchanged to overwrite the current draft. Change it to create a new draft branch.';
  }
  saveDraftDialog.classList.remove('hidden');
  setTimeout(() => {
    draftNameInput.focus();
    draftNameInput.select();
  }, 0);
}

function hideSaveDraftDialog() {
  if (saveDraftDialog) {
    saveDraftDialog.classList.add('hidden');
  }
}

function shouldBranchDraft(title) {
  if (isFinalSolution()) {
    return true;
  }
  if (!currentSolution || currentSolution.solution_type !== 'draft') {
    return false;
  }
  return title.trim() !== currentDraftName().trim();
}

function setReadOnlyMode(enabled) {
  readOnlyMode = Boolean(enabled);
  canvas.style.pointerEvents = readOnlyMode ? 'none' : 'auto';
  [
    undoBtn,
    redoBtn,
    clearBtn,
    toolPen,
    toolEraser,
    colorInput,
    sizeInput,
    bgColorInput,
  ].forEach(element => {
    if (element) element.disabled = readOnlyMode;
  });
  textBoxes.forEach(box => {
    if (box?.element) box.element.disabled = readOnlyMode;
  });
}

function resetBoardState() {
  strokeHistory.length = 0;
  redoStack.length = 0;
  clearTextBoxes();
  setReadOnlyMode(false);
  bgColor = bgColorInput ? bgColorInput.value : '#ffffff';
  if (bgColorInput) bgColorInput.value = bgColor;
  canvas.style.backgroundColor = bgColor;
  fullRedraw();
  updateButtonsState();
}

function loadPaperImage(imageUrl) {
  return new Promise((resolve, reject) => {
    if (!imageUrl) {
      paperImage = null;
      paperImageSource = null;
      setCanvasSize(true);
      resolve();
      return;
    }

    const img = new Image();
    img.onload = () => {
      paperImage = img;
      paperImageSource = imageUrl;
      const paperSize = getAdaptivePaperSize(img);
      fixedCanvasWidth = paperSize.width;
      fixedCanvasHeight = paperSize.height;
      setCanvasSize(true);
      resolve();
    };
    img.onerror = () => reject(new Error('Failed to load problem image'));
    img.src = imageUrl;
  });
}

function restoreCanvasData(canvasData) {
  if (!canvasData) return;
  const sourceWidth = Number(canvasData.canvas_width) || fixedCanvasWidth || 1;
  const sourceHeight = Number(canvasData.canvas_height) || fixedCanvasHeight || 1;
  const scaleX = fixedCanvasWidth / sourceWidth;
  const scaleY = fixedCanvasHeight / sourceHeight;
  const scaleStrokeSize = Math.max(0.1, (scaleX + scaleY) / 2);

  strokeHistory.length = 0;
  redoStack.length = 0;
  clearTextBoxes();
  if (canvasData.bg_color) {
    bgColor = canvasData.bg_color;
    if (bgColorInput) bgColorInput.value = bgColor;
    canvas.style.backgroundColor = bgColor;
  }
  if (Array.isArray(canvasData.strokes)) {
    canvasData.strokes.forEach(stroke => {
      strokeHistory.push({
        ...stroke,
        size: Number(stroke.size) ? Number(stroke.size) * scaleStrokeSize : stroke.size,
        points: Array.isArray(stroke.points)
          ? stroke.points.map(point => ({
              x: Number(point.x || 0) * scaleX,
              y: Number(point.y || 0) * scaleY,
              p: point.p,
            }))
          : [],
      });
    });
  }
  fullRedraw();
  if (Array.isArray(canvasData.text_boxes)) {
    canvasData.text_boxes.forEach(snapshot => {
      const x = Number(snapshot.x || 10) * scaleX;
      const y = Number(snapshot.y || 10) * scaleY;
      const fontSizePx = Number(snapshot.font_size_px);
      const box = createTextBox(x, y, {
        value: snapshot.value || '',
        color: snapshot.color || colorInput.value,
        fontSizePx: fontSizePx ? fontSizePx * scaleStrokeSize : undefined,
      });
      if (box) {
        box.element.style.left = `${x}px`;
        box.element.style.top = `${y}px`;
        box.z = Number(snapshot.z) || box.z;
        box.element.style.zIndex = String(box.z);
        autoSizeTextBox(box);
      }
    });
  }
  updateTextBoxInteractivity();
  updateButtonsState();
}

function drawPaperImage() {
  if (!paperImage) return;
  ctx.save();
  ctx.globalCompositeOperation = 'source-over';
  ctx.drawImage(paperImage, 0, 0, fixedCanvasWidth, fixedCanvasHeight);
  ctx.restore();
}

async function renderWhiteboardContext(problem, selectedSolution, draftSolutions = [], finalSolutions = []) {
  currentProblem = problem || null;
  currentSolution = selectedSolution || null;
  currentUserSolutionId = currentSolution && currentSolution.solution_type === 'draft' ? currentSolution.id : null;
  selectedGradedSolution = currentSolution && currentSolution.solution_type === 'graded' ? currentSolution : null;
  availableDraftSolutions = Array.isArray(draftSolutions) ? draftSolutions : [];
  availableFinalSolutions = Array.isArray(finalSolutions) ? finalSolutions : [];
  availableSolutions = [
    ...availableDraftSolutions,
    ...availableFinalSolutions,
  ];

  if (contextTitle) {
    contextTitle.textContent = problem?.id || 'Whiteboard';
  }
  renderSolutionBrowser();
  updateSolutionActionState();

  if (problemReference) problemReference.classList.add('hidden');
  if (problemImage) problemImage.removeAttribute('src');
  if (solutionReferencePanel) solutionReferencePanel.classList.add('hidden');
  if (solutionImage) solutionImage.removeAttribute('src');

  resetBoardState();
  const paperSource = currentSolution?.canvas_data?.paper_image_source
    || (currentSolution && currentSolution.image_url && !currentSolution.canvas_data ? currentSolution.image_url : null)
    || (problem ? problem.image_url : null);
  await loadPaperImage(paperSource);
  if (currentSolution && currentSolution.canvas_data) {
    restoreCanvasData(currentSolution.canvas_data);
  }
  setReadOnlyMode(isFinalSolution());
  updateSolutionActionState();
}

async function loadWhiteboardContext() {
  const params = new URLSearchParams(window.location.search);
  const solutionId = params.get('solution_id');
  const problemId = params.get('problem_id');
  requestedFeedbackId = params.get('feedback_id');
  if (!solutionId && !problemId) {
    window.location.href = '/progress.html';
    return;
  }

  const query = solutionId
    ? `solution_id=${encodeURIComponent(solutionId)}`
    : `problem_id=${encodeURIComponent(problemId)}`;

  try {
    const data = await apiRequest(`/api/whiteboard/context?${query}`);
    await renderWhiteboardContext(
      data.problem,
      data.solution,
      data.draft_solutions,
      data.final_solutions,
    );
    if (data.solution && data.solution.solution_type === 'graded') {
      displayGradingResults(
        data.solution.grading_result,
        data.solution.grading_steps,
        data.solution,
        { focusFeedbackId: requestedFeedbackId },
      );
    }
  } catch (error) {
    if (contextTitle) contextTitle.textContent = error.message;
  }
}

clearBtn.addEventListener('click', () => {
  if (strokeHistory.length === 0 && textBoxes.length === 0) return;
  strokeHistory.length = 0;
  redoStack.length = 0;
  fullRedraw();
  clearTextBoxes();
});

async function saveCurrentSolution({ saveAs = false, titleOverride = null } = {}) {
  if (!currentProblem) {
    throw new Error('Open a problem from progress before saving.');
  }
  if (isFinalSolution() && !saveAs) {
    throw new Error('This solution is final. Save Draft to branch it into a new draft.');
  }
  isSavingSolution = true;
  updateSolutionActionState();

  try {
    const sourceSolutionId = currentSolution ? currentSolution.id : null;
    const title = (titleOverride || '').trim() || currentDraftName();
    const data = await apiRequest('/api/solutions', {
      method: 'POST',
      body: JSON.stringify({
        problem_id: currentProblem.id,
        solution_id: saveAs ? sourceSolutionId : currentUserSolutionId,
        source_solution_id: saveAs ? sourceSolutionId : null,
        save_as: saveAs,
        title,
        canvas_data: serializeCanvasData(),
        image_data: exportBoardDataUrl(),
      }),
    });
    currentSolution = data.solution;
    currentUserSolutionId = data.solution.id;
    selectedGradedSolution = null;
    availableDraftSolutions = [
      data.solution,
      ...availableDraftSolutions.filter(item => item.id !== data.solution.id),
    ];
    availableSolutions = [...availableDraftSolutions, ...availableFinalSolutions];
    setReadOnlyMode(false);
    hideGradingDialog();
    hideSaveDraftDialog();
    if (problemReference) problemReference.classList.add('hidden');
    if (problemImage) problemImage.removeAttribute('src');
    if (solutionReferencePanel) solutionReferencePanel.classList.add('hidden');
    if (solutionImage) solutionImage.removeAttribute('src');
    renderSolutionBrowser();
    replaceBrowserUrl(`/whiteboard.html?solution_id=${encodeURIComponent(data.solution.id)}`);
    return data.solution;
  } finally {
    isSavingSolution = false;
    updateSolutionActionState();
  }
}

if (saveToServerBtn) {
  saveToServerBtn.addEventListener('click', () => {
    openSaveDraftDialog();
  });
}

if (closeSaveDraftBtn) {
  closeSaveDraftBtn.addEventListener('click', () => {
    hideSaveDraftDialog();
  });
}

if (cancelSaveDraftBtn) {
  cancelSaveDraftBtn.addEventListener('click', () => {
    hideSaveDraftDialog();
  });
}

if (saveDraftForm) {
  saveDraftForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const title = (draftNameInput?.value || '').trim();
    if (!title) {
      if (draftNameInput) draftNameInput.focus();
      return;
    }

    try {
      const saveAs = shouldBranchDraft(title);
      await saveCurrentSolution({ saveAs, titleOverride: title });
    } catch (error) {
      alert(error.message);
    }
  });
}

async function gradeSolutionWithStream(solutionId) {
  resetGradingDialogForStream();
  const response = await fetch(`/api/solutions/${encodeURIComponent(solutionId)}/grade/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grading_mode: 'simple_llm' }),
  });

  if (response.status === 401) {
    window.location.href = '/';
    throw new Error('Authentication required');
  }
  if (!response.ok || !response.body) {
    throw new Error(`Request failed with ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let completedPayload = null;

  const processEventBlock = (block) => {
    const lines = block.split('\n');
    let eventName = 'message';
    const dataLines = [];
    lines.forEach(line => {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart());
      }
    });
    if (!dataLines.length) return;
    const payload = JSON.parse(dataLines.join('\n'));
    if (eventName === 'error') {
      recordScoreInteraction('grading_error', payload);
      throw new Error(payload.error || 'Grading failed');
    }
    if (eventName === 'status' || eventName === 'log') {
      recordScoreInteraction(eventName, { message: payload.message });
      appendGradingStreamLine(payload.message);
      if (gradingSummary && payload.message) {
        gradingSummary.textContent = payload.message;
      }
      return;
    }
    if (eventName === 'llm_delta') {
      recordScoreInteraction('llm_delta', { text: payload.text });
      appendGradingToken(payload.text);
      return;
    }
    if (eventName === 'complete') {
      recordScoreInteraction('grading_complete', { solution_id: payload.solution?.id });
      completedPayload = payload;
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() || '';
    for (const block of blocks) {
      if (block.trim()) {
        processEventBlock(block);
      }
    }
    if (done) break;
  }
  if (buffer.trim()) {
    processEventBlock(buffer);
  }
  if (!completedPayload) {
    throw new Error('Grading ended before returning a score');
  }
  return completedPayload;
}

if (gradeSolutionBtn) {
  gradeSolutionBtn.addEventListener('click', async () => {
    try {
      isSubmittingGrade = true;
      updateSolutionActionState();
      const solution = await saveCurrentSolution({ saveAs: false, titleOverride: currentDraftName() });

      const data = await gradeSolutionWithStream(solution.id);
      currentSolution = data.solution;
      currentUserSolutionId = null;
      selectedGradedSolution = data.solution;
      setReadOnlyMode(true);
      availableFinalSolutions = [data.solution, ...availableFinalSolutions.filter(item => item.id !== data.solution.id)];
      availableSolutions = [...availableDraftSolutions, ...availableFinalSolutions];
      renderSolutionBrowser();
      if (problemReference) problemReference.classList.add('hidden');
      if (problemImage) problemImage.removeAttribute('src');
      if (solutionReferencePanel) solutionReferencePanel.classList.add('hidden');
      if (solutionImage) solutionImage.removeAttribute('src');
      displayGradingResults(data.grading_result, data.grading_steps, data.solution);
    } catch (error) {
      alert(error.message);
    } finally {
      isSubmittingGrade = false;
      updateSolutionActionState();
    }
  });
}

// Analyze with AI functionality
if (analyzeBtn) {
  analyzeBtn.addEventListener('click', async () => {
    if (strokeHistory.length === 0 && textBoxes.length === 0) {
      alert('Please add drawings or text on the whiteboard first!');
      return;
    }
  
  try {
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Analyzing...';
    
    // Show results panel and loading state
    showResultsPanel();
    showLoading();
    
    // Create a temporary canvas with background color (same as Save PNG)
    const tempCanvas = document.createElement('canvas');
    const tempCtx = tempCanvas.getContext('2d');
    
    // Set canvas size to match original
    tempCanvas.width = canvas.width;
    tempCanvas.height = canvas.height;
    
    // Fill with background color
    tempCtx.fillStyle = bgColor || '#ffffff';
    tempCtx.fillRect(0, 0, tempCanvas.width, tempCanvas.height);
    
    // Draw the original canvas on top
    tempCtx.drawImage(canvas, 0, 0);
    renderTextBoxesToContext(tempCtx);
    
    // Convert to blob
    const blob = await new Promise(resolve => {
      tempCanvas.toBlob(resolve, 'image/png', 0.9);
    });
    
    // Create FormData and send to server
    const formData = new FormData();
    formData.append('image', blob, `whiteboard-${Date.now()}.png`);
    
    const response = await fetch('/api/process-image', {
      method: 'POST',
      body: formData,
      credentials: 'include'
    });
    
    if (!response.ok) {
      throw new Error(`Server error: ${response.status}`);
    }
    
    const result = await response.json();
    
    if (result.success) {
      displayResults(result.analysis);
    } else {
      throw new Error(result.error || 'Unknown error occurred');
    }
    
  } catch (error) {
    console.error('Analysis error:', error);
    showError();
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = 'Analyze with AI';
  }
  });
}

// Results panel management
closeResultsBtn.addEventListener('click', () => {
  hideResultsPanel();
});
// Close panel when clicking outside
resultsPanel.addEventListener('click', (e) => {
  if (e.target === resultsPanel) {
    hideResultsPanel();
  }
});
if (saveDraftDialog) {
  saveDraftDialog.addEventListener('click', (e) => {
    if (e.target === saveDraftDialog) {
      hideSaveDraftDialog();
    }
  });
}

// ESC key to close panel
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && saveDraftDialog && !saveDraftDialog.classList.contains('hidden')) {
    hideSaveDraftDialog();
    return;
  }
  if (e.key === 'Escape' && gradingDialog && !gradingDialog.classList.contains('hidden')) {
    return;
  }
  if (e.key === 'Escape' && !resultsPanel.classList.contains('hidden')) {
    hideResultsPanel();
  }
});

function showResultsPanel() {
  resultsPanel.classList.remove('hidden');
}

function hideResultsPanel() {
  resultsPanel.classList.add('hidden');
  hideLoading();
  hideResults();
  hideError();
}

function showLoading() {
  hideResults();
  hideError();
  resultsLoading.classList.remove('hidden');
}

function hideLoading() {
  resultsLoading.classList.add('hidden');
}

function showResults() {
  hideLoading();
  hideError();
  resultsData.classList.remove('hidden');
}

function hideResults() {
  resultsData.classList.add('hidden');
}

function showError() {
  hideLoading();
  hideResults();
  resultsError.classList.remove('hidden');
}

function hideError() {
  resultsError.classList.add('hidden');
}

function showGradingDialog() {
  if (gradingDialog) {
    gradingDialog.classList.remove('hidden');
  }
  if (gradingBackdrop) {
    gradingBackdrop.classList.remove('hidden');
  }
  recordScoreInteraction('score_dialog_opened', { solution_id: activeScoreSolution?.id || null });
}

function hideGradingDialog() {
  if (gradingDialog) {
    gradingDialog.classList.add('hidden');
  }
  if (gradingBackdrop) {
    gradingBackdrop.classList.add('hidden');
  }
  recordScoreInteraction('score_dialog_closed', { solution_id: activeScoreSolution?.id || null });
}

function recordScoreInteraction(type, payload = {}) {
  scoreInteractionLog.push({
    type,
    payload,
    timestamp: new Date().toISOString(),
  });
  if (scoreInteractionLog.length > 500) {
    scoreInteractionLog = scoreInteractionLog.slice(-500);
  }
}

function appendGradingStreamLine(message) {
  if (!gradingStream || !message) return;
  gradingStream.classList.remove('hidden');
  const line = document.createElement('div');
  line.className = 'grading-stream-line';
  line.textContent = message;
  gradingStream.appendChild(line);
  gradingStream.scrollTop = gradingStream.scrollHeight;
}

function appendGradingToken(text) {
  if (!gradingStream || !text) return;
  gradingStream.classList.remove('hidden');
  if (!gradingLiveLine) {
    gradingLiveLine = document.createElement('div');
    gradingLiveLine.className = 'grading-stream-line grading-live-llm';
    gradingLiveLine.textContent = 'LLM response:\n';
    gradingStream.appendChild(gradingLiveLine);
  }
  gradingLiveLine.textContent += text;
  gradingStream.scrollTop = gradingStream.scrollHeight;
}

function resetGradingDialogForStream() {
  hideResultsPanel();
  gradingLiveLine = null;
  activeScoreSolution = null;
  pendingScoreFeedbackRating = null;
  scoreInteractionLog = [];
  if (gradingStream) {
    gradingStream.innerHTML = '';
    gradingStream.classList.remove('hidden');
  }
  if (scoreFeedbackForm) scoreFeedbackForm.classList.add('hidden');
  if (scoreFeedbackText) scoreFeedbackText.value = '';
  if (scoreFeedbackMessage) scoreFeedbackMessage.textContent = '';
  if (rightGradingBtn) rightGradingBtn.disabled = true;
  if (wrongGradingBtn) wrongGradingBtn.disabled = true;
  if (gradingScore) gradingScore.textContent = 'Grading...';
  if (gradingSummary) gradingSummary.textContent = 'Waiting for the grader to start.';
  setIssueList(gradingMajorList, [], 'No major deductions have been reported yet.');
  setIssueList(gradingMinorList, [], 'No minor deductions have been reported yet.');
  setIssueList(gradingStepList, [], 'The grading transcript will update as work completes.');
  if (gradingConfidenceFill) gradingConfidenceFill.style.width = '0%';
  if (gradingConfidenceText) gradingConfidenceText.textContent = 'Running';
  appendGradingStreamLine('Submitting the saved whiteboard for grading...');
  showGradingDialog();
}

function setIssueList(listElement, items, emptyMessage) {
  if (!listElement) return;
  listElement.innerHTML = '';
  if (Array.isArray(items) && items.length) {
    items.forEach(item => {
      const li = document.createElement('li');
      if (typeof item === 'string') {
        li.textContent = item;
      } else {
        const points = item.points_taken ?? item.deducted_points ?? item.points_deducted;
        const reason = item.reason || item.deduction_reason || item.description || item.content || 'Saved detail';
        const step = item.step || item.deduction_step || item.step_number || item.step_id;
        const confidence = item.confidence ?? item.deduction_confidence_score ?? item.confidence_score;
        const segments = [];
        if (points !== undefined && points !== null && points !== '') {
          segments.push(`-${points} pts`);
        }
        segments.push(reason);
        if (step !== undefined && step !== null && step !== '') {
          segments.push(`(${step})`);
        }
        if (confidence !== undefined && confidence !== null && confidence !== '') {
          const percent = Math.round(Number(confidence) * 100);
          if (!Number.isNaN(percent)) {
            segments.push(`[${percent}% confidence]`);
          }
        }
        li.textContent = segments.join(' ');
      }
      listElement.appendChild(li);
    });
    return;
  }
  const li = document.createElement('li');
  li.textContent = emptyMessage;
  listElement.appendChild(li);
}

function renderScoreFeedbackHistory(items = [], focusFeedbackId = null) {
  if (!scoreFeedbackHistory) return;
  scoreFeedbackHistory.innerHTML = '';
  if (!Array.isArray(items) || items.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'empty-solution';
    empty.textContent = 'No feedback has been recorded yet.';
    scoreFeedbackHistory.appendChild(empty);
    return;
  }

  let focusElement = null;
  items.forEach(item => {
    const row = document.createElement('article');
    row.className = `score-feedback-history-item ${item.rating === 'right' ? 'feedback-history-right' : 'feedback-history-wrong'}`;
    row.dataset.feedbackId = String(item.id);

    const header = document.createElement('div');
    header.className = 'score-feedback-history-header';
    const rating = document.createElement('strong');
    rating.textContent = item.rating === 'right' ? 'Right Grading' : 'Wrong Grading';
    const time = document.createElement('time');
    time.textContent = item.created_at ? new Date(item.created_at).toLocaleString() : '';
    header.appendChild(rating);
    header.appendChild(time);

    const text = document.createElement('p');
    text.textContent = item.feedback_text || '(No written feedback)';

    row.appendChild(header);
    row.appendChild(text);
    scoreFeedbackHistory.appendChild(row);

    if (focusFeedbackId && String(item.id) === String(focusFeedbackId)) {
      focusElement = row;
    }
  });

  const target = focusElement || scoreFeedbackHistory.firstElementChild;
  if (target) {
    target.classList.add('feedback-history-focused');
    target.scrollIntoView({ block: 'nearest' });
  }
}

async function loadScoreFeedbackHistory(scoreSolutionId, focusFeedbackId = null) {
  if (!scoreFeedbackHistory || !scoreSolutionId) return;
  scoreFeedbackHistory.innerHTML = '<p class="empty-solution">Loading feedback...</p>';
  try {
    const data = await apiRequest(`/api/solutions/${encodeURIComponent(scoreSolutionId)}/feedback`);
    renderScoreFeedbackHistory(data.feedback_items, focusFeedbackId);
  } catch (error) {
    scoreFeedbackHistory.innerHTML = '';
    const message = document.createElement('p');
    message.className = 'empty-solution';
    message.textContent = error.message;
    scoreFeedbackHistory.appendChild(message);
  }
}

function beginScoreFeedback(rating) {
  if (!activeScoreSolution) return;
  pendingScoreFeedbackRating = rating;
  recordScoreInteraction('score_feedback_rating_selected', {
    solution_id: activeScoreSolution.id,
    rating,
  });
  if (scoreFeedbackForm) scoreFeedbackForm.classList.remove('hidden');
  if (scoreFeedbackMessage) {
    scoreFeedbackMessage.textContent = rating === 'right'
      ? 'Optional: tell us what made this grading useful.'
      : 'Optional: tell us what the grader missed or got wrong.';
  }
  if (scoreFeedbackText) {
    scoreFeedbackText.focus();
  }
}

if (rightGradingBtn) {
  rightGradingBtn.addEventListener('click', () => beginScoreFeedback('right'));
}

if (wrongGradingBtn) {
  wrongGradingBtn.addEventListener('click', () => beginScoreFeedback('wrong'));
}

if (scoreFeedbackForm) {
  scoreFeedbackForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!activeScoreSolution || !pendingScoreFeedbackRating) return;
    const feedbackText = (scoreFeedbackText?.value || '').trim();
    recordScoreInteraction('score_feedback_confirmed', {
      solution_id: activeScoreSolution.id,
      rating: pendingScoreFeedbackRating,
      has_feedback_text: Boolean(feedbackText),
    });
    recordScoreInteraction('score_dialog_closed_after_feedback', {
      solution_id: activeScoreSolution.id,
    });
    try {
      if (scoreFeedbackMessage) scoreFeedbackMessage.textContent = 'Saving feedback...';
      await apiRequest(`/api/solutions/${encodeURIComponent(activeScoreSolution.id)}/feedback`, {
        method: 'POST',
        body: JSON.stringify({
          rating: pendingScoreFeedbackRating,
          feedback_text: feedbackText,
          interaction_log: scoreInteractionLog,
        }),
      });
      await loadScoreFeedbackHistory(activeScoreSolution.id);
      hideGradingDialog();
    } catch (error) {
      if (scoreFeedbackMessage) scoreFeedbackMessage.textContent = error.message;
    }
  });
}

function displayResults(analysis) {
  hideGradingDialog();
  if (resultsTitle) resultsTitle.textContent = 'AI Analysis Results';
  // Update text content
  textRecognition.textContent = analysis.text_recognition || 'No text detected';
  visualElements.textContent = analysis.visual_elements || 'No visual elements detected';
  contentAnalysis.textContent = analysis.content_analysis || 'No analysis available';
  
  // Update suggestions list
  suggestionsList.innerHTML = '';
  if (analysis.suggestions && Array.isArray(analysis.suggestions)) {
    analysis.suggestions.forEach(suggestion => {
      const li = document.createElement('li');
      li.textContent = suggestion;
      suggestionsList.appendChild(li);
    });
  } else {
    const li = document.createElement('li');
    li.textContent = 'No suggestions available';
    suggestionsList.appendChild(li);
  }
  
  // Update confidence bar
  const confidence = Math.round((analysis.confidence || 0) * 100);
  confidenceFill.style.width = `${confidence}%`;
  confidenceText.textContent = `${confidence}%`;

  showResults();
}

function displayGradingResults(gradingResult, gradingSteps = [], gradedSolution = null, options = {}) {
  hideResultsPanel();
  activeScoreSolution = gradedSolution || activeScoreSolution;
  pendingScoreFeedbackRating = null;
  if (scoreFeedbackForm) scoreFeedbackForm.classList.add('hidden');
  if (scoreFeedbackText) scoreFeedbackText.value = '';
  if (scoreFeedbackMessage) scoreFeedbackMessage.textContent = '';
  if (rightGradingBtn) rightGradingBtn.disabled = !activeScoreSolution;
  if (wrongGradingBtn) wrongGradingBtn.disabled = !activeScoreSolution;
  recordScoreInteraction('score_result_displayed', { solution_id: activeScoreSolution?.id || null });
  const result = gradingResult?.result || gradingResult?.score || gradingResult || {};
  const { score, maxScore } = scoreFromGradingPayload(gradedSolution, gradingResult);
  const summary = result.summary || gradingResult?.summary || gradingResult?.score?.summary || 'The grading result has been saved.';
  const confidence = Number(
    result.confidence_score
      ?? result.confidence
      ?? gradingResult?.confidence
      ?? gradingResult?.result?.confidence_score
      ?? 0
  );
  const steps = Array.isArray(gradingSteps) && gradingSteps.length
    ? gradingSteps
    : (Array.isArray(result.steps) ? result.steps : []);
  const majorPoints = gradedSolution?.major_points
    || gradedSolution?.points_taken?.major
    || result.major_issues
    || [];
  const minorPoints = gradedSolution?.minor_points
    || gradedSolution?.points_taken?.minor
    || result.minor_issues
    || [];

  if (gradingScore) {
    gradingScore.textContent = score !== undefined && score !== null
      ? `${score} / ${maxScore || 100}`
      : 'Saved with this submission';
  }
  if (gradingSummary) {
    gradingSummary.textContent = summary;
  }

  setIssueList(gradingMajorList, majorPoints, 'No major deductions were recorded.');
  setIssueList(gradingMinorList, minorPoints, 'No minor deductions were recorded.');
  setIssueList(
    gradingStepList,
    steps.map(step => {
      const stepNumber = step.step_number || step.step_id || '';
      const content = step.content || step.raw_text || step.normalized_text || JSON.stringify(step);
      const validity = step.is_valid === false ? 'issue found' : '';
      return stepNumber ? `Step ${stepNumber}: ${content}${validity ? ` (${validity})` : ''}` : `${content}${validity ? ` (${validity})` : ''}`;
    }),
    'Detailed grading steps are stored with this submission.',
  );

  const confidencePercent = Math.round(Math.max(0, Math.min(1, confidence || 0)) * 100);
  if (gradingConfidenceFill) {
    gradingConfidenceFill.style.width = `${confidencePercent}%`;
  }
  if (gradingConfidenceText) {
    gradingConfidenceText.textContent = confidencePercent ? `${confidencePercent}%` : 'Saved';
  }

  showGradingDialog();
  if (activeScoreSolution) {
    loadScoreFeedbackHistory(activeScoreSolution.id, options.focusFeedbackId);
  } else {
    renderScoreFeedbackHistory([]);
  }
}

/* Keyboard shortcuts */
window.addEventListener('keydown', (e) => {
  if (gradingDialog && !gradingDialog.classList.contains('hidden')) {
    return;
  }
  // Undo: Ctrl+Z, Redo: Ctrl+Y or Ctrl+Shift+Z
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key.toLowerCase() === 'z') {
    e.preventDefault();
    if (e.shiftKey) {
      redoBtn.click();
    } else {
      undoBtn.click();
    }
  } else if (ctrl && e.key.toLowerCase() === 'y') {
    e.preventDefault();
    redoBtn.click();
  }
});

/* Pointer events */
const canvasPointerOptions = { passive: false };
canvas.addEventListener('pointerdown', startStroke, canvasPointerOptions);
canvas.addEventListener('pointermove', extendStroke, canvasPointerOptions);
// High-frequency updates for supported devices (e.g., pens)
canvas.addEventListener('pointerrawupdate', extendStroke, canvasPointerOptions);
canvas.addEventListener('pointerup', endStroke, canvasPointerOptions);
canvas.addEventListener('pointercancel', endStroke, canvasPointerOptions);
canvas.addEventListener('pointerleave', endStroke, canvasPointerOptions);

/* Keep the same drawing coordinates while fitting the visible board to the device. */
if (window.ResizeObserver) {
  const boardResizeObserver = new ResizeObserver(() => updateBoardSurfaceScale());
  boardResizeObserver.observe(container);
} else {
  window.addEventListener('resize', updateBoardSurfaceScale);
  window.addEventListener('orientationchange', updateBoardSurfaceScale);
}

/* Initial setup */
setupFloatingToolbar();
setCanvasSize();
updateButtonsState();
updateTextBoxInteractivity();
loadWhiteboardContext();

/* Controls state */
function updateButtonsState() {
  undoBtn.disabled = strokeHistory.length === 0;
  redoBtn.disabled = redoStack.length === 0;
  clearBtn.disabled = strokeHistory.length === 0 && textBoxes.length === 0;
}

/* SVG Export */
function strokesToSVG(strokes, width, height, backgroundColor = '#ffffff') {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  const pathForStroke = (stroke) => {
    if (!stroke.points.length) return '';
    const pts = stroke.points;
    const d = [];
    let prev = null;

    for (let i = 0; i < pts.length; i++) {
      const curr = pts[i];
      const sCurr = smoothedPoint(prev, curr);
      if (i === 0) {
        d.push(`M ${sCurr.x.toFixed(2)} ${sCurr.y.toFixed(2)}`);
      } else {
        const cx = ((prev.x + sCurr.x) / 2).toFixed(2);
        const cy = ((prev.y + sCurr.y) / 2).toFixed(2);
        d.push(`Q ${prev.x.toFixed(2)} ${prev.y.toFixed(2)} ${cx} ${cy}`);
        d.push(`Q ${cx} ${cy} ${sCurr.x.toFixed(2)} ${sCurr.y.toFixed(2)}`);
      }
      prev = sCurr;
    }

    // approximate pressure width by average
    const avgP = pts.reduce((a, p) => a + (p.p || 0.5), 0) / pts.length || 0.5;
    const widthPx = Math.max(0.5, stroke.size * (0.3 + 0.7 * avgP));

    if (stroke.tool === 'eraser') {
      // Eraser via mask: represent as white stroke with 'destination-out'-like effect is not directly in plain SVG.
      // Instead, we emulate by using 'mix-blend-mode: destination-out' which is not standard in all renderers.
      // For portability, export eraser as transparent stroke on a mask group. Simplify: skip eraser strokes in SVG.
      // Alternatively draw eraser as white path with stroke-opacity to visually indicate. We'll skip for true transparency.
      return ''; // skipping eraser strokes ensures they don't add ink in exported SVG
    }

    return `<path d="${esc(d.join(' '))}" fill="none" stroke="${esc(stroke.color)}" stroke-width="${widthPx.toFixed(2)}" stroke-linecap="round" stroke-linejoin="round" />`;
  };

  const paths = strokes.map(pathForStroke).filter(Boolean).join('\n  ');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs></defs>
  ${backgroundColor ? `<rect width="100%" height="100%" fill="${esc(backgroundColor)}"/>` : ''}
  ${paths}
</svg>`;
}
