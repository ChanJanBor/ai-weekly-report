#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix translation button + print CSS for ai_weekly_report.html
"""
import re

HTML = r'C:\Users\Administrator\Desktop\ai_weekly_report_v2\ai_weekly_report.html'
OUT  = HTML  # 直接覆盖

with open(HTML, 'r', encoding='utf-8') as f:
    s = f.read()

# ── 修复 1: renderNews() 模板里加翻译按钮 ───────────────────────
# 找到 meta div 的结尾，在 </a></div> 前插入翻译按钮
old_meta = """'<div class="meta"><span>'+(a.published||'').substring(0,16)+' · '+esc(a.source)+'</span>'+
      '<a href="'+esc(a.url)+'" target="_blank" rel="noopener">打开原文</a></div></div>'"""

new_meta = """'<div class="meta"><span>'+(a.published||'').substring(0,16)+' · '+esc(a.source)+'</span>'+
      '<button class="btn-trans" onclick="toggleTranslate(this,'+JSON.stringify(a.id)+')" style="margin-left:8px;padding:2px 10px;border-radius:6px;border:1px solid rgba(59,130,246,0.4);background:rgba(59,130,246,0.1);color:#93c5fd;font-size:.72rem;cursor:pointer">翻译</button>'+
      '<a href="'+esc(a.url)+'" target="_blank" rel="noopener">打开原文</a></div></div>'"""

if old_meta in s:
    s = s.replace(old_meta, new_meta, 1)
    print('  [OK] renderNews() 模板已加翻译按钮')
else:
    # 尝试模糊匹配（可能有空格差异）
    # 用正则找 renderNews 里的 .meta div 结尾
    pat = r"""('<div class="meta">.*?</a></div></div>')"""
    m = re.search(pat, s, re.DOTALL)
    if m:
        old = m.group(1)
        # 在 <a href=...>打开原文</a> 前面插入按钮
        new = old.replace("'>打开原文</a></div>'", 
                       """+ '<button class="btn-trans" onclick="toggleTranslate(this,\''+a.id+'\')" style="margin-left:8px;padding:2px 10px;border-radius:6px;border:1px solid rgba(59,130,246,0.4);background:rgba(59,130,246,0.1);color:#93c5fd;font-size:.72rem;cursor:pointer">翻译</button>' + '<a href="'+esc(a.url)+'" target="_blank" rel="noopener">打开原文</a></div>'""")
        s = s[:m.start()] + new + s[m.end():]
        print('  [OK] renderNews() 模板已加翻译按钮（正则匹配）')
    else:
        print('  [WARN] 未找到 meta div，手动检查')

# ── 修复 2: 添加 toggleTranslate() 函数 ────────────────────────
# 在 esc() 函数前插入
toggle_fn = """
/* 翻译按钮：英文→中文，中文→英文，支持恢复原文 */
const _txCache = {};
async function toggleTranslate(btn, articleId) {
  const card = btn.closest('.card');
  if (!card) return;
  const h3 = card.querySelector('h3');
  const p  = card.querySelector('p');
  if (!h3) return;

  // 如果已翻译，恢复原文
  if (card.dataset.origTitle) {
    h3.textContent = card.dataset.origTitle;
    if (p) p.textContent = card.dataset.origSummary || '';
    btn.textContent = '翻译';
    delete card.dataset.origTitle;
    delete card.dataset.origSummary;
    return;
  }

  // 保存原文
  card.dataset.origTitle = h3.textContent;
  card.dataset.origSummary = p ? p.textContent : '';

  const isZh = /[\u4e00-\u9fff]/.test(h3.textContent);
  const target = isZh ? 'en' : 'zh-CN';

  btn.disabled = true;
  btn.textContent = '翻译中...';

  try {
    const [tTitle, tSummary] = await Promise.all([
      translateText(h3.textContent, target),
      p ? translateText(p.textContent, target) : Promise.resolve('')
    ]);
    h3.textContent = tTitle || h3.textContent;
    if (p) p.textContent = tSummary || p.textContent;
    btn.textContent = '原文';
  } catch(e) {
    btn.textContent = '翻译失败';
  }
  btn.disabled = false;
}

async function translateText(text, targetLang) {
  if (!text || text.length < 3) return text;
  const key = targetLang + '|' + text.substring(0, 60);
  if (_txCache[key]) return _txCache[key];
  const url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=' + targetLang + '&dt=t&q=' + encodeURIComponent(text.substring(0, 4000));
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(8000) });
    const d = await r.json();
    const result = (d[0]||[]).map(s => s[0]).join('');
    _txCache[key] = result;
    return result;
  } catch(e) {
    return text;
  }
}
"""

# 插入到 <script> 后的第一个函数前
insert_after = '<script>'
if insert_after in s and 'function esc(' in s:
    idx = s.index('function esc(')
    s = s[:idx] + toggle_fn + '\n' + s[idx:]
    print('  [OK] toggleTranslate() 函数已插入')
else:
    print('  [WARN] 未找到插入点，手动检查')

# ── 修复 3: 修改 @media print CSS（保留彩色）────────────────
# 替换现有的 @media print 块
old_print = """@media print{
  *{background:#fff!important;color:#000!important;box-shadow:none!important;text-shadow:none!important}
  .act-bar,.tab-bar,.fb,.ft,.modal,#sb{display:none!important}
  .tab-content{display:block!important}
  .card,.tc,.tl-i,.dc,.cg-card,.kpi-card{break-inside:avoid;page-break-inside:avoid}
  a[href]:after{content:" (" attr(href) ")";font-size:9px;color:#555}
  .hero{background:#fff!important;color:#000!important;padding:20px!important}
  .hero h1{background:none!important;-webkit-text-fill-color:#000!important;color:#000!important}
  .kpi-card .num{background:none!important;-webkit-text-fill-color:#000!important;color:#000!important}
  .tag,.sent-bull,.sent-bear,.sent-neu,.sig,.sb,.sn,.sr{background:#f0f0f0!important;color:#000!important;border:1px solid #ccc!important}
  .tl::before,.ti::before{background:#000!important}
}"""

new_print = """@media print{
  /* 保留彩色，只调整可读性 */
  body{background:#fff!important;color:#000!important}
  .act-bar,.tab-bar,.fb,.ft,.modal,#sb,.wl-chips{display:none!important}
  .tab-content{display:block!important}
  .card,.tc,.tl-i,.dc,.cg-card,.kpi-card{break-inside:avoid;page-break-inside:avoid;background:#fff!important;color:#000!important;border:1px solid #ddd!important}
  .hero{background:linear-gradient(135deg,#60a5fa,#a78bfa,#34d399)!important;color:#fff!important;padding:20px!important;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}
  .hero h1{color:#fff!important;-webkit-text-fill-color:#fff!important;background:none!important}
  .tag,.sent-bull,.sent-bear,.sent-neu,.sig{solid;border-width:1px!important;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}
  .sent-bull{background:rgba(16,185,129,0.15)!important;color:#059669!important}
  .sent-bear{background:rgba(239,68,68,0.15)!important;color:#dc2626!important}
  .sent-neu{background:rgba(245,158,11,0.15)!important;color:#d97706!important}
  .kpi-card .num{background:linear-gradient(135deg,#3b82f6,#8b5cf6)!important;-webkit-text-fill-color:transparent!important;-webkit-background-clip:text!important}
  a[href]:after{content:" (" attr(href) ")";font-size:9px;color:#555}
  /* 确保背景色被打印 */
  *{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}
}"""

if old_print in s:
    s = s.replace(old_print, new_print, 1)
    print('  [OK] @media print CSS 已更新（保留彩色）')
else:
    print('  [WARN] 未找到旧 print CSS，尝试追加')
    # 在 </style> 前追加
    s = s.replace('</style>', new_print + '\n  </style>', 1)
    print('  [OK] @media print CSS 已追加')

# ── 修复 4: 在 "批量翻译" 按钮 onclick 里也要处理 ─────────
# 确保 translateVisible() 函数存在且正确
if 'function translateVisible' not in s:
    tx_visible = """
async function translateVisible() {
  const btns = document.querySelectorAll('#newsGrid .btn-trans');
  const btnBatch = document.getElementById('btnBatchTranslate');
  if (btnBatch) { btnBatch.disabled = true; btnBatch.textContent = '批量翻译中...'; }
  for (const btn of btns) {
    if (btn.textContent === '翻译') {
      await toggleTranslate(btn, 0);
      await new Promise(r => setTimeout(r, 500));
    }
  }
  if (btnBatch) { btnBatch.disabled = false; btnBatch.textContent = '批量翻译'; }
}
"""
    # 插入到 toggleTranslate 后面
    idx = s.index('// 保存原文')
    s = s[:idx] + tx_visible + '\n' + s[idx:]
    print('  [OK] translateVisible() 函数已插入')

# ── 写入 ────────────────────────────────────────────────────────
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(s)
print(f'\nDone! {len(s):,} bytes written to')
print(OUT)
