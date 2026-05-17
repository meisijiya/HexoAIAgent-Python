/**
 * Hexo Agent Widget 插件
 * 
 * 将 CSS 和 JS 文件注入到 Hexo 页面中
 * URL 带内容哈希参数 ?v=<sha256>，内容不变时浏览器走缓存
 */

const fs = require('fs');
const path = require('path');

function getCacheBust() {
    try {
        const versionPath = path.join(__dirname, 'version.json');
        const data = JSON.parse(fs.readFileSync(versionPath, 'utf8'));
        return data.hash || 'v0';
    } catch (e) {
        return 'v0';
    }
}

// 注入 CSS
hexo.extend.helper.register('agent_widget_css', function() {
    const v = getCacheBust();
    return `<link rel="stylesheet" href="/css/agent-widget.css?v=${v}">`;
});

// 注入 JS
hexo.extend.helper.register('agent_widget_js', function() {
    const v = getCacheBust();
    return `<script src="/js/agent-widget.js?v=${v}"></script>`;
});

// 注入到页面
hexo.extend.filter.register('after_render', function(content) {
    const v = getCacheBust();
    const css = `<link rel="stylesheet" href="/css/agent-widget.css?v=${v}">`;
    const js = `<script src="/js/agent-widget.js?v=${v}"></script>`;
    
    // 在 </head> 前注入 CSS
    content = content.replace('</head>', `${css}\n</head>`);
    
    // 在 </body> 前注入 JS
    content = content.replace('</body>', `${js}\n</body>`);
    
    return content;
});
