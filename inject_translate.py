#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inject Google Translate button + JS into ai_weekly_report.html
方案 A: 浏览器端翻译，不占用 Python 时间
"""

HTML = r'C:\Users\Administrator\Desktop\ai_weekly_report_v2\ai_weekly_report.html'
OUT  = r'C:\Users\Administrator\Desktop\ai_weekly_report_v2\ai_weekly_report_v3.html'

# ── 1. Google Translate JS (inject before </body>) ─────────────
TRANSLATE_JS = """
<!-- Google Translate Element -->
<div id="google_translate_element" style="display:none"></div>
<script>
function googleTranslateElementInit(){
  new google.translate.TranslateElement({
    pageLanguage: 'en',
    includedLanguages: 'zh-CN,en',
    layout: google.translate.TranslateElement.InlineLayout.SIMPLE
  }, 'google_translate_element');
}
</script>
<script src="https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>

<script>
/*
 * 方案 A: 浏览器端翻译
 * - 英文文章 → 显示中文翻译（行内）
 * - 中文文章 → 显示英文翻译（行内）
 * 使用 Google Translate 公共接口（无需 API key）
 */
let translateCache = {};

async function translateText(text, targetLang) {
  if (!text || text.length < 5) return text;
  const cacheKey = targetLang + '|' + text.substring(0, 80);
  if (translateCache[cacheKey]) return translateCache[cacheKey];
  const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=${targetLang}&dt=t&q=` + encodeURIComponent(text.substring(0, 4000));
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(5000) });
    const d = await r.json();
    const result = (d[0] || []).map(s => s[0]).join('');
    translateCache[cacheKey] = result;
    return result;
  } catch(e) {
    return text;  // 翻译失败返回原文
  }
}

async function translateArticle(btn, articleId) {
  const card = btn.closest('.card');
  if (!card) return;
  const h3 = card.querySelector('h3');
  const p  = card.querySelector('p');
  if (!h3) return;

  btn.disabled = true;
  btn.textContent = '翻译中...';

  const isChinese = /[\u4e00-\u9fff]/.test(h3.textContent);
  const targetLang = isChinese ? 'en' : 'zh-CN';

  const [tTitle, tSummary] = await Promise.all([
    translateText(h3.textContent, targetLang),
    p ? translateText(p.textContent, targetLang) : ''
  ]);

  if (!card.dataset.origTitle) {
    card.dataset.origTitle = h3.textContent;
    card.dataset.origSummary = p ? p.textContent : '';
  }
  h3.textContent = tTitle;
  if (p) p.textContent = tSummary;

  btn.textContent = '显示原文';
  btn.classList.add('active-trans');
  btn.onclick = () => restoreArticle(btn, articleId);
  btn.disabled = false;
}

function restoreArticle(btn, articleId) {
  const card = btn.closest('.card');
  if (!card || !card.dataset.origTitle) return;
  const h3 = card.querySelector('h3');
  const p  = card.querySelector('p');
  h3.textContent = card.dataset.origTitle;
  if (p) p.textContent = card.dataset.origSummary;
  btn.textContent = '翻译';
  btn.classList.remove('active-trans');
  btn.onclick = () => translateArticle(btn, articleId);
}

/* 批量翻译当前可见新闻 */
let batchTranslating = false;
async function translateVisible() {
  if (batchTranslating) return;
  batchTranslating = true;
  const btn = document.getElementById('btnBatchTranslate');
  if (btn) { btn.disabled = true; btn.textContent = '批量翻译中...'; }
  const cards = document.querySelectorAll('#newsGrid .card');
  for (const card of cards) {
    const b = card.querySelector('.btn-trans');
    if (b && !b.classList.contains('active-trans')) {
      await translateArticle(b, 0);
      await new Promise(r => setTimeout(r, 300));  // 节流
    }
  }
  if (btn) { btn.disabled = false; btn.textContent = '批量翻译'; }
  batchTranslating = false;
}

/* 初始化：给每张卡片加翻译按钮 */
function initTranslateButtons() {
  document.querySelectorAll('#newsGrid .card').forEach((card, i) => {
    if (card.querySelector('.btn-trans')) return;  // 已添加
    const meta = card.querySelector('.meta');
    if (!meta) return;
    const btn = document.createElement('button');
    btn.className = 'btn-trans';
    btn.textContent = '翻译';
    btn.style.cssText = 'margin-left:8px;padding:2px 10px;border-radius:6px;border:1px solid rgba(59,130,246,0.4);background:rgba(59,130,246,0.1);color:#93c5fd;font-size:.72rem;cursor:pointer';
    btn.onclick = () => translateArticle(btn, i);
    meta.appendChild(btn);
  });
}
</script>
"""

# ── 2. 操作栏加「批量翻译」按钮 ─────────────────────────
BATCH_BTN = '<button id="btnBatchTranslate" onclick="translateVisible()" style="padding:7px 18px;border-radius:8px;border:1px solid rgba(139,92,246,0.4);background:rgba(139,92,246,0.12);color:#c4b5fd;font-size:.82rem;cursor:pointer;margin-left:8px">批量翻译</button>'

# ── 3. 在 renderNews() 末尾调用 initTranslateButtons ───────
def inject():
    with open(HTML, 'r', encoding='utf-8') as f:
        s = f.read()

    # ① 注入 translate JS 到 </body> 前
    s = s.replace('</body>', TRANSLATE_JS + '\n</body>', 1)

    # ② 在操作栏最后加「批量翻译」按钮
    #    找到 act-bar 的最后一个 </div>（hero 结尾），在 </header> 前插入
    #    更简单：在 showTab 按钮组里加
    #    实际：在 act-bar 的 HTML 里直接替换
    act_bar_old = '<button onclick="openModal(\'emailModal\')">邮件推送</button>'
    act_bar_new = '<button onclick="openModal(\'emailModal\')">邮件推送</button>' + '\n        ' + BATCH_BTN
    s = s.replace(act_bar_old, act_bar_new, 1)

    # ③ 在 renderAll() 或 filterArticles() 后调用 initTranslateButtons
    #    renderNews() 调用后加一行
    s = s.replace(
        '  renderNews(arts);\n',
        '  renderNews(arts);\n  setTimeout(initTranslateButtons, 200);\n',
        1  # 只替换第一个（renderAll 里的）
    )

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(s)
    print('Done →', OUT)
    print('Size:', len(s), 'bytes')

if __name__ == '__main__':
    inject()
