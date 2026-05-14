/**
 * Hexo Agent Widget 插件
 * 
 * 将 CSS 和 JS 文件注入到 Hexo 页面中
 */

// 注入 CSS
hexo.extend.helper.register('agent_widget_css', function() {
    return `<link rel="stylesheet" href="/css/agent-widget.css">`;
});

// 注入 JS
hexo.extend.helper.register('agent_widget_js', function() {
    return `<script src="/js/agent-widget.js"></script>`;
});

// 注入到页面
hexo.extend.filter.register('after_render', function(content) {
    const css = '<link rel="stylesheet" href="/css/agent-widget.css">';
    const js = '<script src="/js/agent-widget.js"></script>';
    
    // 在 </head> 前注入 CSS
    content = content.replace('</head>', `${css}\n</head>`);
    
    // 在 </body> 前注入 JS
    content = content.replace('</body>', `${js}\n</body>`);
    
    return content;
});
