const input = document.querySelector('#textInput');
const wordCount = document.querySelector('#wordCount');
const charCount = document.querySelector('#charCount');
const analyzeBtn = document.querySelector('#analyzeBtn');
const clearBtn = document.querySelector('#clearBtn');
const sampleBtn = document.querySelector('#sampleBtn');
const minimum = document.querySelector('.minimum');
const humanizerStyle = document.querySelector('#humanizerStyle');
const humanizerIntensity = document.querySelector('#humanizerIntensity');
const intensityLabel = document.querySelector('#intensityLabel');
const humanizedOutput = document.querySelector('#humanizedOutput');
const humanizeBtn = document.querySelector('#humanizeBtn');
const copyRevisionBtn = document.querySelector('#copyRevisionBtn');
const applyRevisionBtn = document.querySelector('#applyRevisionBtn');
const humanizerContext = document.querySelector('#humanizerContext');
const humanizerStatus = document.querySelector('#humanizerStatus');
const documentInput = document.querySelector('#documentInput');
const uploadBtn = document.querySelector('#uploadBtn');
const uploadBox = document.querySelector('#uploadBox');
const fileStatus = document.querySelector('#fileStatus');

const PDFJS_VERSION = '4.10.38';
const SUPPORTED_EXTENSIONS = new Set(['txt', 'md', 'docx', 'pdf']);
const MAX_HIGHLIGHT_SENTENCES = 300;
let humanizerRequestInFlight = false;

const example = `Perkembangan teknologi kecerdasan buatan telah membawa perubahan signifikan dalam berbagai aspek kehidupan manusia. Teknologi ini tidak hanya meningkatkan efisiensi kerja, tetapi juga membuka peluang baru dalam bidang pendidikan, kesehatan, dan industri. Selain itu, kecerdasan buatan mampu membantu manusia dalam menganalisis data yang kompleks secara cepat dan akurat.

Namun demikian, penerapan kecerdasan buatan juga menghadirkan sejumlah tantangan yang perlu diperhatikan. Privasi data, keamanan informasi, dan potensi bias algoritma merupakan isu penting yang harus ditangani secara bertanggung jawab. Oleh karena itu, kolaborasi antara pemerintah, perusahaan, dan masyarakat sangat diperlukan untuk memastikan bahwa teknologi ini digunakan secara etis dan memberikan manfaat yang merata bagi semua pihak.`;

function wordsOf(text) {
  return text.toLowerCase().match(/[a-zà-ÿ0-9]+(?:['’-][a-zà-ÿ]+)*/gi) || [];
}

function updateCount() {
  const count = wordsOf(input.value).length;
  wordCount.textContent = count.toLocaleString('id-ID');
  charCount.textContent = input.value.length.toLocaleString('id-ID');
  analyzeBtn.disabled = count < 10;
  minimum.classList.toggle('ready', count >= 50);
  minimum.querySelector('span').textContent = count >= 50
    ? `Siap dianalisis · tanpa batas kata${count >= 10000 ? ' · dokumen panjang' : ''}`
    : 'Tanpa batas kata · minimal 50 kata disarankan';
}

function extensionOf(filename) {
  return filename.includes('.') ? filename.split('.').pop().toLowerCase() : '';
}

function setFileStatus(message, type = 'success') {
  fileStatus.textContent = message;
  fileStatus.classList.remove('hidden', 'error');
  if (type === 'error') fileStatus.classList.add('error');
}

async function extractPdf(file) {
  const pdfjsLib = await import(`https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}/pdf.min.mjs`);
  pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}/pdf.worker.min.mjs`;
  const pdf = await pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
  const pages = [];
  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    setFileStatus(`Membaca ${file.name} · halaman ${pageNumber}/${pdf.numPages}...`);
    const page = await pdf.getPage(pageNumber);
    const content = await page.getTextContent();
    pages.push(content.items.map(item => item.str).join(' ').replace(/\s+/g, ' ').trim());
  }
  return pages.filter(Boolean).join('\n\n');
}

async function extractDocument(file) {
  const extension = extensionOf(file.name);
  if (!SUPPORTED_EXTENSIONS.has(extension)) throw new Error('Format belum didukung. Gunakan TXT, MD, DOCX, atau PDF.');
  if (extension === 'txt' || extension === 'md') return file.text();
  if (extension === 'docx') {
    if (!window.mammoth) throw new Error('Pembaca DOCX gagal dimuat. Periksa koneksi lalu coba lagi.');
    const result = await window.mammoth.extractRawText({ arrayBuffer: await file.arrayBuffer() });
    return result.value;
  }
  return extractPdf(file);
}

async function loadDocument(file) {
  if (!file) return;
  uploadBtn.disabled = true;
  setFileStatus(`Membaca ${file.name}...`);
  try {
    const text = (await extractDocument(file)).replace(/\r\n/g, '\n').trim();
    if (!text) throw new Error('Tidak ada teks yang dapat diekstrak. PDF hasil scan mungkin memerlukan OCR.');
    input.value = text;
    updateCount();
    setFileStatus(`${file.name} berhasil dimuat · ${wordsOf(text).length.toLocaleString('id-ID')} kata · ${(file.size / 1024).toLocaleString('id-ID', { maximumFractionDigits: 1 })} KB`);
    input.focus();
  } catch (error) {
    setFileStatus(error.message || 'Dokumen gagal dibaca.', 'error');
  } finally {
    uploadBtn.disabled = false;
    documentInput.value = '';
  }
}

function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }
function variance(values) {
  if (!values.length) return 0;
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  return values.reduce((sum, n) => sum + Math.pow(n - avg, 2), 0) / values.length;
}

function uniformity(values, scale = 1, fallback = .35) {
  if (values.length < 2) return fallback;
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  return 1 - clamp(Math.sqrt(variance(values)) / Math.max(avg * scale, 1), 0, 1);
}

function windowRates(words, vocabulary, windows = 4) {
  if (!words.length) return [0];
  const size = Math.max(1, Math.ceil(words.length / windows));
  const rates = [];
  for (let i = 0; i < words.length; i += size) {
    const chunk = words.slice(i, i + size);
    rates.push(chunk.filter(word => vocabulary.has(word)).length / chunk.length);
  }
  return rates;
}

function splitSentences(text) {
  const matches = text.match(/[^.!?]+(?:[.!?]+|$)/g) || [];
  return matches.map(sentence => sentence.trim()).filter(Boolean);
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  })[char]);
}

function analyzeText(text) {
  const words = wordsOf(text);
  let sentences = text.split(/(?<=[.!?])\s+/).map(s => s.trim()).filter(Boolean);
  if (sentences.length < 2) sentences = text.split(/[.!?]+/).map(s => s.trim()).filter(Boolean);
  const paragraphs = text.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean);
  const sentenceLengths = sentences.map(s => wordsOf(s).length).filter(Boolean);
  const paragraphLengths = paragraphs.map(p => wordsOf(p).length);
  const commas = sentences.map(sentence => (sentence.match(/,/g) || []).length);
  const closureRate = sentences.filter(sentence => /[.!?]$/.test(sentence.trim())).length / Math.max(sentences.length, 1);
  const functionWords = new Set(['yang','dan','di','ke','dari','untuk','dengan','pada','dalam','oleh','karena','agar','tetapi','juga','atau','sebagai','itu','ini']);
  const functionRates = windowRates(words, functionWords);
  const size = Math.max(1, Math.ceil(words.length / 4));
  const lexicalRates = [];
  for (let i = 0; i < words.length; i += size) {
    const chunk = words.slice(i, i + size);
    lexicalRates.push(new Set(chunk).size / Math.max(chunk.length, 1));
  }

  const feature = {
    sentenceUniformity: uniformity(sentenceLengths, .72),
    paragraphUniformity: uniformity(paragraphLengths, .85),
    sentenceClosure: clamp((closureRate - .45) / .55, 0, 1),
    commaUniformity: uniformity(commas, 1.15),
    functionStability: uniformity(functionRates, 2.1),
    lexicalStability: uniformity(lexicalRates, 2.0),
    digitDensity: clamp([...text].filter(char => /\p{Nd}/u.test(char)).length / Math.max(text.length, 1) * 35, 0, 1),
    quoteDensity: clamp([...text].filter(char => '"“”‘’'.includes(char)).length / Math.max(text.length, 1) * 55, 0, 1)
  };
  const rawScore = feature.sentenceUniformity * .26 + feature.paragraphUniformity * .10 +
    feature.sentenceClosure * .18 + feature.commaUniformity * .12 +
    feature.functionStability * .15 + feature.lexicalStability * .09 -
    feature.digitDensity * .05 - feature.quoteDensity * .05;
  const frozenThreshold = .5435406480407824;
  const score = Math.floor(clamp(100 / (1 + Math.exp(-12 * (rawScore - frozenThreshold))), 1, 99));

  return {
    score,
    wordLength: words.length,
    signals: [
      { icon: '≈', title: 'Keseragaman kalimat', detail: `${sentences.length} kalimat · pola panjang ${feature.sentenceUniformity.toFixed(2)}`, value: feature.sentenceUniformity },
      { icon: '¶', title: 'Keseragaman paragraf', detail: `${paragraphs.length} paragraf · indeks ${feature.paragraphUniformity.toFixed(2)}`, value: feature.paragraphUniformity },
      { icon: '∎', title: 'Penutupan kalimat', detail: `${Math.round(closureRate * 100)}% kalimat bertanda akhir`, value: feature.sentenceClosure },
      { icon: ',', title: 'Ritme klausa', detail: `Keseragaman penggunaan koma ${feature.commaUniformity.toFixed(2)}`, value: feature.commaUniformity },
      { icon: '∴', title: 'Stabilitas kata fungsi', detail: `Konsistensi antarbagi teks ${feature.functionStability.toFixed(2)}`, value: feature.functionStability },
      { icon: 'Aa', title: 'Stabilitas leksikal', detail: `Konsistensi keragaman kata ${feature.lexicalStability.toFixed(2)}`, value: feature.lexicalStability }
    ]
  };
}

function analyzeSentenceContexts(text) {
  const sentences = splitSentences(text);
  if (sentences.length < 2) return [];
  const sampled = sentences.length <= MAX_HIGHLIGHT_SENTENCES
    ? sentences.map((sentence, index) => ({ sentence, index }))
    : Array.from({ length: MAX_HIGHLIGHT_SENTENCES }, (_, position) => {
        const index = Math.floor(position * (sentences.length - 1) / (MAX_HIGHLIGHT_SENTENCES - 1));
        return { sentence: sentences[index], index };
      });
  return sampled.map(({ sentence, index }) => {
    const context = sentences.slice(Math.max(0, index - 1), index + 2).join(' ');
    const contextScore = analyzeText(context).score;
    const sentenceWords = wordsOf(sentence);
    const reasons = [];
    if (/[.!?]$/.test(sentence) && sentenceWords.length >= 12) reasons.push('struktur lengkap');
    if ((sentence.match(/,/g) || []).length >= 2) reasons.push('ritme klausa teratur');
    const functionWords = new Set(['yang','dan','di','ke','dari','untuk','dengan','pada','dalam','oleh','karena','agar','tetapi','juga','atau','sebagai','itu','ini']);
    const functionRate = sentenceWords.filter(word => functionWords.has(word)).length / Math.max(sentenceWords.length, 1);
    if (functionRate >= .16) reasons.push('kata fungsi padat');
    if (new Set(sentenceWords).size / Math.max(sentenceWords.length, 1) >= .82 && sentenceWords.length >= 14) reasons.push('leksikal konsisten');
    return {
      text: sentence,
      score: contextScore,
      level: contextScore >= 65 ? 'high' : contextScore >= 50 ? 'medium' : 'low',
      reason: reasons.slice(0, 2).join(' · ') || 'pola konteks sekitar'
    };
  });
}

function humanizeText(text, style = 'natural', intensity = 2) {
  const replacements = {
    natural: [['Namun demikian,','Namun,'],['Oleh karena itu,','Karena itu,'],['Secara keseluruhan,','Singkatnya,'],['merupakan','adalah'],['senantiasa','selalu'],['guna','untuk']],
    concise: [['Namun demikian,','Namun,'],['Oleh karena itu,','Jadi,'],['Secara keseluruhan,',''],['pada dasarnya',''],['yang sangat','yang'],['dapat digunakan untuk','bisa']],
    formal: [['Namun demikian,','Meski demikian,'],['Oleh karena itu,','Dengan demikian,'],['Secara keseluruhan,','Secara ringkas,'],['merupakan','menjadi'],['saat ini','kini']]
  };
  let result = text;
  replacements[style].slice(0, intensity * 2).forEach(([from, to]) => {
    result = result.replace(new RegExp(from, 'gi'), match => {
      if (!to) return '';
      return match === match.toUpperCase() && /[A-ZÀ-Ÿ]/.test(match) ? to.toUpperCase() : to;
    });
  });
  let sentences = splitSentences(result);
  if (intensity >= 2) sentences = sentences.flatMap(sentence => {
    const words = wordsOf(sentence);
    if (words.length < 28) return [sentence];
    const comma = sentence.indexOf(',', Math.floor(sentence.length * .35));
    if (comma < 0 || comma > sentence.length * .78) return [sentence];
    const first = sentence.slice(0, comma).trim();
    let second = sentence.slice(comma + 1).trim();
    second = second.charAt(0).toUpperCase() + second.slice(1);
    return [`${first}.`, second];
  });
  if (intensity >= 3) sentences = sentences.map((sentence, index) => {
    if (index % 4 !== 3 || wordsOf(sentence).length < 12) return sentence;
    return sentence.replace(/^Selain itu,\s*/i, '').replace(/^Dengan demikian,\s*/i, '');
  });
  return sentences.join(' ').replace(/\s{2,}/g, ' ').replace(/\s+([,.!?])/g, '$1').trim();
}

function setHumanizerStatus(message, type = '') {
  humanizerStatus.textContent = message;
  humanizerStatus.classList.remove('ready', 'error');
  if (type) humanizerStatus.classList.add(type);
}

async function checkHumanizerHealth() {
  try {
    const response = await fetch('/api/health', { cache: 'no-store' });
    if (!response.ok) throw new Error('Backend editor tidak tersedia');
    const health = await response.json();
    setHumanizerStatus(health.llmConfigured
      ? `Editor LLM siap · ${health.model}`
      : 'Backend aktif, tetapi API key belum dikonfigurasi. Fallback editor lokal tersedia.',
    health.llmConfigured ? 'ready' : 'error');
  } catch (_) {
    setHumanizerStatus('Mode lokal aktif. Jalankan server.py untuk menggunakan editor LLM berbasis konteks.', 'error');
  }
}

function renderResult(result) {
  const { score, signals, wordLength } = result;
  document.querySelector('#scoreValue').textContent = score;
  document.querySelector('#scoreRing').style.setProperty('--score', `${score * 3.6}deg`);
  document.querySelector('#meterFill').style.width = `${score}%`;
  document.querySelector('#meterPin').style.left = `calc(${score}% - 1px)`;

  let verdict = 'Cenderung tulisan manusia';
  let confidence = 'Sinyal AI rendah';
  if (score >= 50) { verdict = 'Kemungkinan besar AI'; confidence = 'Beberapa pola AI terdeteksi kuat'; }
  else if (score >= 35) { verdict = 'Hasil tidak pasti'; confidence = 'Terdapat campuran sinyal manusia dan AI'; }
  document.querySelector('#verdict').textContent = verdict;
  document.querySelector('#confidence').textContent = `${confidence}${wordLength < 50 ? ' · sampel pendek' : ''}`;

  const detected = signals.filter(s => s.value >= .5).length;
  document.querySelector('#signalCount').textContent = `${detected}/${signals.length} terdeteksi`;
  document.querySelector('#signalList').innerHTML = signals.map(signal => {
    const label = signal.value >= .7 ? 'Tinggi' : signal.value >= .4 ? 'Sedang' : 'Rendah';
    return `<div class="signal">
      <span class="signal-icon">${signal.icon}</span>
      <div><h4>${signal.title}</h4><p>${signal.detail}</p></div>
      <span class="signal-level ${signal.value >= .7 ? 'high' : ''}">${label}</span>
    </div>`;
  }).join('');

  const sentenceResults = analyzeSentenceContexts(input.value);
  const marked = sentenceResults.filter(item => item.level !== 'low');
  const totalSentences = splitSentences(input.value).length;
  document.querySelector('#sentenceCount').textContent = `${marked.length}/${sentenceResults.length} sampel ditandai`;
  document.querySelector('#sentenceHighlights').innerHTML = sentenceResults.length
    ? sentenceResults.map((item, index) => `<span class="sentence-mark ${item.level}" tabindex="0">
        ${escapeHtml(item.text)}
        ${item.level !== 'low' ? `<small>Kalimat ${index + 1} · skor konteks ${item.score} · ${escapeHtml(item.reason)}</small>` : ''}
      </span>`).join(' ')
    : '<p class="sentence-empty">Teks memerlukan sedikitnya dua kalimat untuk sorotan kontekstual.</p>';
  if (totalSentences > sentenceResults.length) {
    document.querySelector('#sentenceHighlights').insertAdjacentHTML('afterbegin', `<p class="sentence-empty">Menampilkan ${sentenceResults.length} sampel merata dari ${totalSentences} kalimat agar halaman tetap responsif.</p>`);
  }
}

input.addEventListener('input', updateCount);
uploadBtn.addEventListener('click', () => documentInput.click());
documentInput.addEventListener('change', () => loadDocument(documentInput.files[0]));
['dragenter', 'dragover'].forEach(eventName => uploadBox.addEventListener(eventName, event => {
  event.preventDefault(); uploadBox.classList.add('dragging');
}));
['dragleave', 'drop'].forEach(eventName => uploadBox.addEventListener(eventName, event => {
  event.preventDefault(); uploadBox.classList.remove('dragging');
}));
uploadBox.addEventListener('drop', event => loadDocument(event.dataTransfer.files[0]));
clearBtn.addEventListener('click', () => {
  input.value = '';
  updateCount();
  document.querySelector('#resultState').classList.add('hidden');
  document.querySelector('#loadingState').classList.add('hidden');
  document.querySelector('#emptyState').classList.remove('hidden');
  fileStatus.classList.add('hidden');
  input.focus();
});
sampleBtn.addEventListener('click', () => {
  input.value = example;
  updateCount();
  input.focus();
});
analyzeBtn.addEventListener('click', () => {
  document.querySelector('#emptyState').classList.add('hidden');
  document.querySelector('#resultState').classList.add('hidden');
  document.querySelector('#loadingState').classList.remove('hidden');
  analyzeBtn.disabled = true;
  window.setTimeout(() => {
    renderResult(analyzeText(input.value));
    document.querySelector('#loadingState').classList.add('hidden');
    document.querySelector('#resultState').classList.remove('hidden');
    analyzeBtn.disabled = false;
  }, 850);
});

humanizerIntensity.addEventListener('input', () => {
  intensityLabel.textContent = ['','Ringan','Sedang','Aktif'][humanizerIntensity.value];
});
humanizeBtn.addEventListener('click', async () => {
  if (humanizerRequestInFlight) return;
  if (wordsOf(input.value).length < 10) { input.focus(); return; }
  humanizerRequestInFlight = true;
  humanizeBtn.disabled = true;
  humanizeBtn.innerHTML = '<span>Menyunting...</span><b>⋯</b>';
  setHumanizerStatus('LLM sedang membaca konteks dan menyunting tulisan...');
  let revised = '';
  try {
    const response = await fetch('/api/humanize', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: input.value, style: humanizerStyle.value,
        intensity: Number(humanizerIntensity.value), context: humanizerContext.value.trim() })
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || `Editor LLM gagal (HTTP ${response.status})`);
    revised = result.text;
    setHumanizerStatus(`Revisi LLM selesai · ${result.model} · ${result.chunks} bagian`, 'ready');
  } catch (error) {
    revised = humanizeText(input.value, humanizerStyle.value, Number(humanizerIntensity.value));
    setHumanizerStatus(`${error.message} Fallback lokal diterapkan.`, 'error');
  } finally {
    humanizerRequestInFlight = false;
    humanizeBtn.disabled = false;
    humanizeBtn.innerHTML = 'Revisi dengan LLM <b>↗</b>';
  }
  humanizedOutput.value = revised;
  const before = wordsOf(input.value).length, after = wordsOf(revised).length;
  document.querySelector('#revisionStats').textContent = `${before} → ${after} kata`;
  copyRevisionBtn.disabled = applyRevisionBtn.disabled = !revised;
});
copyRevisionBtn.addEventListener('click', async () => {
  await navigator.clipboard.writeText(humanizedOutput.value);
  copyRevisionBtn.textContent = 'Tersalin';
  window.setTimeout(() => { copyRevisionBtn.textContent = 'Salin hasil'; }, 1200);
});
applyRevisionBtn.addEventListener('click', () => {
  input.value = humanizedOutput.value;
  updateCount(); input.focus();
  document.querySelector('#detector').scrollIntoView({ behavior:'smooth' });
});

updateCount();
checkHumanizerHealth();
