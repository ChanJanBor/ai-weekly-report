#!/usr/bin/env node
/**
 * 本地翻译代理服务器 v2
 * 多重翻译源备选，解决 translate.googleapis.com 在中国大陆无法访问的问题
 * 
 * 用法: node translate_proxy.js
 */

const http = require('http');
const https = require('https');
const url = require('url');

const PORT = 3456;
const TIMEOUT = 10000;
const cache = new Map();
const MAX_CACHE = 2000;

// 检测文本语言（简单规则）
function detectLang(text) {
  // 中文字符比例
  const cjkCount = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]/g) || []).length;
  const totalChars = text.replace(/\s/g, '').length;
  if (totalChars === 0) return 'en';
  const cjkRatio = cjkCount / totalChars;
  if (cjkRatio > 0.25) return 'zh-CN';
  // 日文假名
  if (/[\u3040-\u309f\u30a0-\u30ff]/.test(text)) return 'ja';
  return 'en';
}

function httpGet(urlStr, opts = {}) {
  return new Promise((resolve, reject) => {
    const parsed = url.parse(urlStr);
    const options = {
      hostname: parsed.hostname,
      port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
      path: parsed.path,
      method: 'GET',
      headers: Object.assign({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en,zh-CN;q=0.9',
      }, opts.headers || {}),
      timeout: TIMEOUT,
    };
    const req = https.request(options, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() });
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    req.end();
  });
}

// 方案1: Microsoft Translator (Edge API, 免费)
async function translateMicrosoft(text, from, to) {
  const encoded = encodeURIComponent(text.substring(0, 1000));
  const apiUrl = `https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&from=${from}&to=${to}`;
  // 这个需要 API Key，大概率不可用，作为备选
  throw new Error('Microsoft Translator 需要 API Key');
}

// 方案2: MyMemory (免费, 需要明确源语言)
async function translateMyMemory(text, from, to) {
  const encoded = encodeURIComponent(text.substring(0, 500));
  const fromLang = from === 'auto' ? detectLang(text) : from;
  const langPair = `${fromLang}|${to}`;
  const apiUrl = `https://api.mymemory.translated.net/get?q=${encoded}&langpair=${langPair}&de=someone%40example.com`;
  
  const { status, body } = await httpGet(apiUrl);
  const data = JSON.parse(body);
  if (data.responseStatus === 200 && data.responseData?.translatedText) {
    return data.responseData.translatedText;
  }
  throw new Error('MyMemory: ' + (data.responseDetails || 'unknown error'));
}

// 方案3: LibreTranslate (需要自建或公共实例)
async function translateLibre(text, from, to) {
  const instances = [
    'https://translate.argosopentech.com',
    'https://libretranslate.de',
  ];
  const fromLang = from === 'auto' ? detectLang(text) : from;
  
  for (const base of instances) {
    try {
      const apiUrl = `${base}/translate`;
      const parsed = url.parse(apiUrl);
      const postData = JSON.stringify({
        q: text.substring(0, 1000),
        source: fromLang,
        target: to,
        format: 'text',
      });
      
      const result = await new Promise((resolve, reject) => {
        const options = {
          hostname: parsed.hostname,
          port: 443,
          path: parsed.path,
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(postData),
            'User-Agent': 'Mozilla/5.0',
          },
          timeout: TIMEOUT,
        };
        const req = https.request(options, (res) => {
          const chunks = [];
          res.on('data', (c) => chunks.push(c));
          res.on('end', () => {
            try {
              const data = JSON.parse(Buffer.concat(chunks).toString());
              resolve(data.translatedText || null);
            } catch (e) { resolve(null); }
          });
        });
        req.on('error', () => resolve(null));
        req.on('timeout', () => { req.destroy(); resolve(null); });
        req.write(postData);
        req.end();
      });
      
      if (result) return result;
    } catch (e) {}
  }
  throw new Error('LibreTranslate 所有实例不可用');
}

// 方案4: Lingva Translate (Google 翻译的隐私代理，可能没被墙)
async function translateLingva(text, from, to) {
  const instances = [
    'https://lingva.ml',
    'https://translate.plausibility.cloud',
    'https://lingva.lunar.icu',
  ];
  const fromLang = from === 'auto' ? 'auto' : from;
  
  for (const base of instances) {
    try {
      const apiUrl = `${base}/api/v1/${fromLang}/${to}/${encodeURIComponent(text.substring(0, 2000))}`;
      const { status, body } = await httpGet(apiUrl, { headers: { 'Accept': 'application/json' } });
      const data = JSON.parse(body);
      if (data.translation) return data.translation;
    } catch (e) {}
  }
  throw new Error('Lingva 所有实例不可用');
}

// 方案5: Google Translate (直接调用，有时可通)
async function translateGoogle(text, from, to) {
  const encoded = encodeURIComponent(text.substring(0, 4000));
  const apiUrl = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=${to}&dt=t&q=${encoded}`;
  
  const { status, body } = await httpGet(apiUrl, {
    headers: {
      'Referer': 'https://translate.google.com/',
      'Origin': 'https://translate.google.com',
    }
  });
  
  if (status !== 200) throw new Error('Google: HTTP ' + status);
  const data = JSON.parse(body);
  const result = (data[0] || []).map(s => s[0]).join('');
  if (result) return result;
  throw new Error('Google: empty result');
}

// 翻译主函数：依次尝试多种方案
async function doTranslate(text, targetLang, sourceLang) {
  const cacheKey = `${sourceLang || 'auto'}|${targetLang}|${text.substring(0, 120)}`;
  if (cache.has(cacheKey)) return cache.get(cacheKey);

  const translators = [
    { name: 'Lingva', fn: () => translateLingva(text, sourceLang, targetLang) },
    { name: 'Google', fn: () => translateGoogle(text, sourceLang, targetLang) },
    { name: 'MyMemory', fn: () => translateMyMemory(text, sourceLang, targetLang) },
    { name: 'LibreTranslate', fn: () => translateLibre(text, sourceLang, targetLang) },
  ];

  for (const t of translators) {
    try {
      const result = await t.fn();
      if (result && result !== text) {
        if (cache.size >= MAX_CACHE) {
          const firstKey = cache.keys().next().value;
          cache.delete(firstKey);
        }
        cache.set(cacheKey, result);
        return { translatedText: result, source: t.name };
      }
    } catch (e) {
      console.log(`  [${t.name}] 不可用: ${e.message.substring(0, 80)}`);
    }
  }

  return { translatedText: text, error: '所有翻译源不可用' };
}

// HTTP Server
const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204); res.end(); return;
  }

  const parsed = url.parse(req.url, true);
  const pathname = parsed.pathname;

  if (pathname === '/translate' || pathname === '/api/translate') {
    const text = parsed.query.text || '';
    const tl = parsed.query.tl || 'zh-CN';
    const sl = parsed.query.sl || 'auto';

    if (!text) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'text required' }));
      return;
    }

    console.log(`[翻译] ${tl} ← ${text.substring(0, 60)}...`);
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    const result = await doTranslate(text, tl, sl);
    console.log(`  结果: ${(result.source || 'FAIL')} → ${(result.translatedText || '').substring(0, 80)}`);
    res.end(JSON.stringify(result, null, 2));
    return;
  }

  if (pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', cacheSize: cache.size }));
    return;
  }

  if (pathname === '/') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>翻译代理 v2</title>
<style>body{font-family:sans-serif;padding:40px;background:#0a0e1a;color:#e2e8f0}
a{color:#93c5fd;text-decoration:none}a:hover{text-decoration:underline}
pre{background:#111827;padding:12px;border-radius:8px;overflow-x:auto;font-size:14px}
code{background:#1e293b;padding:2px 6px;border-radius:4px}
</style></head><body>
<h2>🌐 翻译代理服务 v2</h2>
<p>状态: <span style="color:#10b981">● 运行中</span> | 缓存: ${cache.size} 条</p>
<p>翻译源: Lingva → Google → MyMemory → LibreTranslate</p>
<h3>API</h3>
<pre>GET /translate?text=&lt;文本&gt;&tl=zh-CN&sl=auto</pre>
<p>测试: <a href="/translate?text=Artificial%20Intelligence%20is%20changing%20the%20world&tl=zh-CN">英文 → 中文</a></p>
<p>测试: <a href="/translate?text=%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD%E6%AD%A3%E5%9C%A8%E6%94%B9%E5%8F%98%E4%B8%96%E7%95%8C&tl=en">中文 → 英文</a></p>
<p><a href="/health">健康检查</a></p>
</body></html>`);
    return;
  }

  res.writeHead(404);
  res.end('Not found');
});

server.on('error', (e) => console.error('服务器错误:', e.message));

server.listen(PORT, () => {
  console.log(`\n翻译代理 v2 已启动: http://localhost:${PORT}`);
  console.log(`翻译源: Lingva → Google → MyMemory → LibreTranslate`);
  console.log(`API: GET http://localhost:${PORT}/translate?text=hello&tl=zh-CN`);
  console.log('按 Ctrl+C 停止\n');
});

process.on('SIGINT', () => {
  server.close(() => process.exit(0));
});