/**
 * Handwriting Board - Portable JS Webapp
 * License: MIT
 * Features:
 * - Pointer events (mouse, touch, pen) with pressure support
 * - Pen and eraser tools
 * - Adjustable color and size
 * - Undo/redo stack
 * - Clear board
 * - Save as PNG / SVG
 * - High-DPI crisp rendering with devicePixelRatio scaling
 * - Responsive canvas that preserves drawing on resize
 */

/* Elements */
const canvas = document.getElementById('board');
const container = document.getElementById('board-container');
const colorInput = document.getElementById('color');
const sizeInput = document.getElementById('size');
const sizeVal = document.getElementById('sizeVal');
const undoBtn = document.getElementById('undo');
const redoBtn = document.getElementById('redo');
const clearBtn = document.getElementById('clear');
const savePngBtn = document.getElementById('savePng');
const saveSvgBtn = document.getElementById('saveSvg');
const analyzeBtn = document.getElementById('analyze-btn');
const toolPen = document.getElementById('tool-pen');
const toolEraser = document.getElementById('tool-eraser');
const bgColorInput = document.getElementById('bgColor');
const ossLink = document.getElementById('ossLink');

// Results panel elements
const resultsPanel = document.getElementById('results-panel');
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

ossLink.href = 'https://opensource.org/license/mit';
ossLink.textContent = 'Open Source (MIT)';

/* Canvas 2D Context */
const ctx = canvas.getContext('2d', { alpha: true, desynchronized: true, willReadFrequently: false });

/* State */
let dpr = Math.max(1, window.devicePixelRatio || 1);
let isDrawing = false;
let lastPoint = null;
let currentStroke = null;
let needsFullRedraw = true;
let bgColor = bgColorInput ? bgColorInput.value : '#ffffff';
canvas.style.backgroundColor = bgColor;

// Fixed canvas dimensions (set once at page load)
let fixedCanvasWidth = 0;
let fixedCanvasHeight = 0;

/* History stacks */
const history = [];      // Array<Stroke>
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

/* Utilities */
function setCanvasSize() {
  // Set fixed dimensions only once at page load
  if (fixedCanvasWidth === 0 || fixedCanvasHeight === 0) {
    const rect = container.getBoundingClientRect();
    fixedCanvasWidth = Math.max(800, Math.floor(rect.width)); // Minimum 800px width
    fixedCanvasHeight = Math.max(600, Math.floor(rect.height)); // Minimum 600px height
  }
  
  dpr = Math.max(1, window.devicePixelRatio || 1);

  // Set canvas to fixed dimensions
  canvas.width = Math.floor(fixedCanvasWidth * dpr);
  canvas.height = Math.floor(fixedCanvasHeight * dpr);
  canvas.style.width = fixedCanvasWidth + 'px';
  canvas.style.height = fixedCanvasHeight + 'px';

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

  if (evt instanceof PointerEvent) {
    x = evt.clientX - rect.left;
    y = evt.clientY - rect.top;
    p = evt.pressure && evt.pressure > 0 ? evt.pressure : (evt.pointerType === 'mouse' ? 0.5 : 0.5);
  } else if (evt.touches && evt.touches[0]) {
    x = evt.touches[0].clientX - rect.left;
    y = evt.touches[0].clientY - rect.top;
    p = 0.5;
  } else {
    x = 0; y = 0; p = 0.5;
  }

  return { x, y, p };
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

  // Redraw all strokes
  for (const stroke of history) {
    drawStroke(stroke, false);
  }
  needsFullRedraw = false;
  updateButtonsState();
}

function startStroke(evt) {
  if (isTextToolActive && isTextToolActive()) {
    return;
  }
  evt.preventDefault();
  canvas.setPointerCapture(evt.pointerId);
  isDrawing = true;
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

function endStroke(evt) {
  if (!isDrawing) return;
  isDrawing = false;
  try {
    canvas.releasePointerCapture(evt.pointerId);
  } catch {}
  if (currentStroke && currentStroke.points.length > 0) {
    history.push(currentStroke);
  }
  currentStroke = null;
  lastPoint = null;
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
  if (history.length === 0) return;
  const s = history.pop();
  redoStack.push(s);
  fullRedraw();
});

redoBtn.addEventListener('click', () => {
  if (redoStack.length === 0) return;
  const s = redoStack.pop();
  history.push(s);
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
  const rect = box.element.getBoundingClientRect();
  const containerRect = container.getBoundingClientRect();
  box.bounds = {
    left: rect.left - containerRect.left,
    top: rect.top - containerRect.top,
    right: rect.right - containerRect.left,
    bottom: rect.bottom - containerRect.top,
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

function createTextBox(x, y) {
  const textarea = document.createElement('textarea');
  textarea.className = 'text-entry';
  textarea.spellcheck = false;
  textarea.value = '';
  textarea.style.position = 'absolute';
  textarea.style.color = colorInput.value;

  const fontPx = Number(sizeInput.value) * 5;
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

  container.appendChild(textarea);
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
  const containerRect = container.getBoundingClientRect();
  targetCtx.save();
  targetCtx.scale(dpr, dpr);
  textBoxes.forEach(box => {
    const el = box.element;
    if (!el) return;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const x = rect.left - containerRect.left;
    const y = rect.top - containerRect.top;
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

clearBtn.addEventListener('click', () => {
  if (history.length === 0 && textBoxes.length === 0) return;
  history.length = 0;
  redoStack.length = 0;
  fullRedraw();
  clearTextBoxes();
});

savePngBtn.addEventListener('click', () => {
  // Create a temporary canvas with background color for PNG
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
  
  // Export as PNG
  const link = document.createElement('a');
  link.download = `handwriting-${Date.now()}.png`;
  link.href = tempCanvas.toDataURL('image/png');
  link.click();
});

saveSvgBtn.addEventListener('click', () => {
  const svg = strokesToSVG(history, canvas.clientWidth, canvas.clientHeight, bgColor);
  const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.download = `handwriting-${Date.now()}.svg`;
  link.href = url;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

// Analyze with AI functionality
analyzeBtn.addEventListener('click', async () => {
  if (history.length === 0 && textBoxes.length === 0) {
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
      body: formData
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

// ESC key to close panel
document.addEventListener('keydown', (e) => {
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

function displayResults(analysis) {
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

/* Keyboard shortcuts */
window.addEventListener('keydown', (e) => {
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
canvas.addEventListener('pointerdown', startStroke);
canvas.addEventListener('pointermove', extendStroke);
// High-frequency updates for supported devices (e.g., pens)
canvas.addEventListener('pointerrawupdate', extendStroke);
canvas.addEventListener('pointerup', endStroke);
canvas.addEventListener('pointercancel', endStroke);
canvas.addEventListener('pointerleave', endStroke);

/* Resize handling removed - canvas now uses fixed dimensions */

/* Initial setup */
setCanvasSize();
updateButtonsState();
updateTextBoxInteractivity();

/* Controls state */
function updateButtonsState() {
  undoBtn.disabled = history.length === 0;
  redoBtn.disabled = redoStack.length === 0;
  clearBtn.disabled = history.length === 0 && textBoxes.length === 0;
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
