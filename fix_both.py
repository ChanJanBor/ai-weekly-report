#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix both issues: translate button + print CSS"""

HTML = r'C:\Users\Administrator\Desktop\ai_weekly_report_v2\ai_weekly_report.html'

with open(HTML, 'r', encoding='utf-8') as f:
    s = f.read()

# ── Fix 1: Add translate button to renderNews() card template ──
# The card template ends with the meta div containing just a span and an anchor.
# We'll add a translate button before the anchor.

# Use regex to find the exact block (safer than exact string matching)
import re

# Find the renderNews function and add translate button to card template
old_line = "'<a href=\"'+esc(a.url)+'\" target=\"_blank\" rel=\"noopener\">打开原文</a></div></div>';\n"
new_line = (
    "'<button class=\"btn-trans\" onclick=\"translateArticle(this)\" "
    "style=\"margin-left:8px;padding:2px 10px;border-radius:6px;"
    "border:1px solid rgba(59,130,246,0.4);background:rgba(59,130,246,0.12);"
    "color:#93c5fd;font-size:.72rem;cursor:pointer\">翻译</button>'\n      +"
    "'<a href=\"'+esc(a.url)+'\" target=\"_blank\" rel=\"noopener\">打开原文</a></div></div>';\n"
)

# Only replace the FIRST occurrence (in renderNews)
if old_line in s:
    s = s.replace(old_line, new_line, 1)
    print('[OK] Translate button added to renderNews() template')
else:
    # Try with \n
    alt_old = "'<a href=\"'+esc(a.url)+'\" target=\"_blank\" rel=\"noopener\">打开原文</a></div></div>';"
    if alt_old in s:
        s = s.replace(alt_old, new_line.rstrip('\n'), 1)
        print('[OK] Translate button added (alt match)')
    else:
        print('[FAIL] Could not find card template in renderNews()')

# ── Fix 2: Update @media print CSS (preserve colors) ──
old_print = ("@media print{\n"
             "  *{background:#fff!important;color:#000!important;box-shadow:none!important;text-shadow:none!important}\n"
             "  .act-bar,.tab-bar,.fb,.ft,.modal,#sb{display:none!important}\n"
             "  .tab-content{display:block!important}\n"
             "  .card,.tc,.tl-i,.dc,.cg-card,.kpi-card{break-inside:avoid;page-break-inside:avoid}\n"
             "  a[href]:after{content:\" (\" attr(href) \")\";font-size:9px;color:#555}\n"
             "  .hero{background:#fff!important;color:#000!important;padding:20px!important}\n"
             "  .hero h1{background:none!important;-webkit-text-fill-color:#000!important;color:#000!important}\n"
             "  .kpi-card .num{background:none!important;-webkit-text-fill-color:#000!important;color:#000!important}\n"
             "  .tag,.sent-bull,.sent-bear,.sent-neu,.sig,.sb,.sn,.sr{background:#f0f0f0!important;color:#000!important;border:1px solid #ccc!important}\n"
             "  .tl::before,.ti::before{background:#000!important}\n"
             "}")

new_print = ("@media print{\n"
             "  .act-bar,.tab-bar,.fb,.ft,.modal,#sb,.wl-chips{display:none!important}\n"
             "  .tab-content{display:block!important}\n"
             "  .card,.tc,.tl-i,.dc,.cg-card,.kpi-card{break-inside:avoid;page-break-inside:avoid}\n"
             "  a[href]:after{content:\" (\" attr(href) \")\";font-size:9px;color:#555}\n"
             "  .hero{padding:20px!important}\n"
             "  *{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}\n"
             "}")

if old_print in s:
    s = s.replace(old_print, new_print, 1)
    print('[OK] Print CSS updated (preserves colors)')
else:
    print('[FAIL] Could not find @media print block')

# ── Save ──
with open(HTML, 'w', encoding='utf-8') as f:
    f.write(s)

print(f'Done! Size: {len(s):,} bytes')

# ── Quick validation ──
btn_count = s.count('translateArticle(this)')
print(f'translateArticle(this) occurrences: {btn_count}')
if '-webkit-print-color-adjust' in s:
    print('Print color-adjust: OK')
