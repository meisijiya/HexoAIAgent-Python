/**
 * Hexo Agent Widget
 * 
 * 功能：
 * - 小人图标 + 拖拽
 * - 对话弹窗
 * - 消息列表
 * - 流式输出（SSE）
 * - 位置记忆（localStorage）
 * - Markdown 渲染
 * - 暗色模式适配
 */
(function() {
    'use strict';

    // ==================== 配置 ====================
    const CONFIG = {
        API_BASE: 'http://localhost:8001',
        STORAGE_KEY: 'hexo-agent-widget',
        MAX_MESSAGES: 100
    };

    // ==================== 状态管理 ====================
    const state = {
        token: null,
        sessionId: null,
        isOpen: false,
        isDragging: false,
        isProcessing: false,
        messages: [],
        position: { x: null, y: null }
    };

    // ==================== 工具函数 ====================
    function $(selector) {
        return document.querySelector(selector);
    }

    function saveState() {
        try {
            localStorage.setItem(CONFIG.STORAGE_KEY, JSON.stringify({
                token: state.token,
                sessionId: state.sessionId,
                position: state.position
            }));
        } catch (e) {}
    }

    function loadState() {
        try {
            const saved = localStorage.getItem(CONFIG.STORAGE_KEY);
            if (saved) {
                const data = JSON.parse(saved);
                state.token = data.token || null;
                state.sessionId = data.sessionId || null;
                state.position = data.position || { x: null, y: null };
            }
        } catch (e) {}
    }

    // ==================== Markdown 渲染 ====================
    function renderMarkdown(text) {
        if (typeof marked === 'undefined') {
            return escapeHtml(text);
        }
        
        try {
            marked.setOptions({
                breaks: true,
                gfm: true,
                highlight: function(code, lang) {
                    if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
                        try {
                            return hljs.highlight(code, { language: lang }).value;
                        } catch (e) {}
                    }
                    return code;
                }
            });
            
            return marked.parse(text);
        } catch (e) {
            return escapeHtml(text);
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ==================== 暗色模式检测 ====================
    function isDarkMode() {
        // 检测 Chic 主题的暗色模式
        if (document.body.classList.contains('dark-theme')) {
            return true;
        }
        
        // 检测系统暗色模式
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return true;
        }
        
        return false;
    }

    function updateTheme() {
        const widget = $('.hexo-agent-widget');
        if (widget) {
            widget.classList.toggle('dark-mode', isDarkMode());
        }
    }

    // ==================== API 调用 ====================
    async function apiRequest(endpoint, options = {}) {
        const url = `${CONFIG.API_BASE}${endpoint}`;
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        return response;
    }

    async function anonymousLogin() {
        const response = await apiRequest('/api/auth/anonymous', { method: 'POST' });
        const data = await response.json();
        state.token = data.token;
        saveState();
        return data;
    }

    async function sendMessage(message) {
        const response = await apiRequest('/api/chat', {
            method: 'POST',
            body: JSON.stringify({
                message: message,
                session_id: state.sessionId,
                token: state.token
            })
        });
        return response;
    }

    // ==================== UI 组件 ====================
    function createWidget() {
        const container = document.createElement('div');
        container.className = 'hexo-agent-widget';
        container.innerHTML = `
            <div class="hexo-agent-trigger" id="agentTrigger">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/>
                </svg>
            </div>
            
            <div class="hexo-agent-popup" id="agentPopup">
                <div class="hexo-agent-header">
                    <span class="hexo-agent-header-title">🤖 AI 助手</span>
                    <button class="hexo-agent-header-close" id="agentClose">&times;</button>
                </div>
                
                <div class="hexo-agent-status">
                    <span>
                        <span class="hexo-agent-status-dot" id="statusDot"></span>
                        <span id="statusText">未连接</span>
                    </span>
                    <span id="userInfo"></span>
                </div>
                
                <div class="hexo-agent-messages" id="agentMessages">
                    <div class="hexo-agent-message system">
                        欢迎使用 AI 助手！请先登录。
                    </div>
                </div>
                
                <div class="hexo-agent-typing" id="agentTyping">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
                
                <div class="hexo-agent-login" id="agentLogin">
                    <button class="hexo-agent-login-btn github" id="btnGithub">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="white">
                            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
                        </svg>
                        GitHub 登录
                    </button>
                    <button class="hexo-agent-login-btn anonymous" id="btnAnonymous">
                        匿名体验
                    </button>
                </div>
                
                <div class="hexo-agent-input-area" id="agentInputArea" style="display:none;">
                    <textarea class="hexo-agent-input" id="agentInput" placeholder="输入消息..." rows="1" disabled></textarea>
                    <button class="hexo-agent-send-btn" id="agentSend" disabled>➤</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(container);
        return container;
    }

    // ==================== 消息管理 ====================
    function addMessage(role, content, extra = {}) {
        const messagesEl = $('#agentMessages');
        const messageEl = document.createElement('div');
        
        let className = `hexo-agent-message ${role}`;
        if (extra.className) className += ` ${extra.className}`;
        
        messageEl.className = className;
        
        // 使用 Markdown 渲染助手消息
        if (role === 'assistant' && !extra.className) {
            messageEl.innerHTML = renderMarkdown(content);
        } else {
            messageEl.innerHTML = content;
        }
        
        messagesEl.appendChild(messageEl);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        
        state.messages.push({ role, content, ...extra });
        
        if (state.messages.length > CONFIG.MAX_MESSAGES) {
            const firstMessage = messagesEl.querySelector('.hexo-agent-message:not(.system)');
            if (firstMessage) firstMessage.remove();
            state.messages.shift();
        }
    }

    function addAgentInfo(agentName, message) {
        addMessage('assistant', `<strong>${agentName}</strong><br>${message}`, { className: 'agent-info' });
    }

    function addSources(articles) {
        let html = '<strong>📚 参考来源：</strong><ul class="hexo-agent-sources-list">';
        articles.forEach(article => {
            const name = article.name || article.relative_path || '未知';
            const score = article.score ? ` (${(article.score * 100).toFixed(0)}%)` : '';
            html += `<li>${escapeHtml(name)}${score}</li>`;
        });
        html += '</ul>';
        addMessage('assistant', html, { className: 'sources' });
    }

    function showTyping() {
        $('#agentTyping').classList.add('active');
    }

    function hideTyping() {
        $('#agentTyping').classList.remove('active');
    }

    // ==================== 登录逻辑 ====================
    async function handleAnonymousLogin() {
        try {
            await anonymousLogin();
            updateUI();
            addMessage('system', '✅ 匿名登录成功！现在可以开始对话了。');
        } catch (error) {
            addMessage('error', '❌ 登录失败：' + error.message);
        }
    }

    function handleGithubLogin() {
        addMessage('system', '⚠️ GitHub 登录暂未实现，请使用匿名体验。');
    }

    function updateUI() {
        const isLoggedIn = !!state.token;
        
        $('#statusDot').classList.toggle('connected', isLoggedIn);
        $('#statusText').textContent = isLoggedIn ? '已连接' : '未连接';
        
        $('#agentLogin').style.display = isLoggedIn ? 'none' : 'flex';
        $('#agentInputArea').style.display = isLoggedIn ? 'flex' : 'none';
        
        $('#agentInput').disabled = !isLoggedIn;
        $('#agentSend').disabled = !isLoggedIn;
    }

    // ==================== 发送消息 ====================
    async function handleSend() {
        const input = $('#agentInput');
        const message = input.value.trim();
        
        if (!message || state.isProcessing) return;
        
        input.value = '';
        input.style.height = 'auto';
        
        addMessage('user', escapeHtml(message));
        
        state.isProcessing = true;
        $('#agentSend').disabled = true;
        showTyping();
        
        try {
            const response = await sendMessage(message);
            await handleStreamResponse(response);
        } catch (error) {
            addMessage('error', '❌ 发送失败：' + error.message);
        } finally {
            state.isProcessing = false;
            $('#agentSend').disabled = false;
            hideTyping();
        }
    }

    async function handleStreamResponse(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        let assistantMessage = '';
        let messageEl = null;
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const text = decoder.decode(value);
            const lines = text.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    const eventType = line.slice(7).trim();
                    const nextLine = lines[lines.indexOf(line) + 1];
                    
                    if (nextLine && nextLine.startsWith('data: ')) {
                        const data = JSON.parse(nextLine.slice(6));
                        
                        if (eventType === 'routing') {
                            hideTyping();
                            addAgentInfo(data.agent_name, data.message);
                            showTyping();
                        } else if (eventType === 'sources') {
                            addSources(data.articles);
                        } else if (eventType === 'done') {
                            state.sessionId = data.session_id;
                            saveState();
                        }
                    }
                } else if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        if (data.content) {
                            if (!messageEl) {
                                hideTyping();
                                messageEl = document.createElement('div');
                                messageEl.className = 'hexo-agent-message assistant';
                                $('#agentMessages').appendChild(messageEl);
                            }
                            assistantMessage += data.content;
                            // 实时渲染 Markdown
                            messageEl.innerHTML = renderMarkdown(assistantMessage);
                            $('#agentMessages').scrollTop = $('#agentMessages').scrollHeight;
                        }
                    } catch (e) {}
                }
            }
        }
    }

    // ==================== 拖拽功能 ====================
    function initDrag() {
        const trigger = $('#agentTrigger');
        let startX, startY, startLeft, startBottom;
        
        trigger.addEventListener('mousedown', (e) => {
            state.isDragging = true;
            trigger.classList.add('dragging');
            
            startX = e.clientX;
            startY = e.clientY;
            startLeft = trigger.offsetLeft;
            startBottom = window.innerHeight - trigger.offsetTop - trigger.offsetHeight;
            
            e.preventDefault();
        });
        
        document.addEventListener('mousemove', (e) => {
            if (!state.isDragging) return;
            
            const deltaX = e.clientX - startX;
            const deltaY = e.clientY - startY;
            
            const newLeft = startLeft + deltaX;
            const newBottom = startBottom - deltaY;
            
            const maxLeft = window.innerWidth - trigger.offsetWidth;
            const maxBottom = window.innerHeight - trigger.offsetHeight;
            
            trigger.style.left = Math.max(0, Math.min(newLeft, maxLeft)) + 'px';
            trigger.style.bottom = Math.max(0, Math.min(newBottom, maxBottom)) + 'px';
            trigger.style.right = 'auto';
        });
        
        document.addEventListener('mouseup', () => {
            if (!state.isDragging) return;
            
            state.isDragging = false;
            trigger.classList.remove('dragging');
            
            state.position = {
                x: trigger.style.left,
                y: trigger.style.bottom
            };
            saveState();
        });
    }

    function restorePosition() {
        if (state.position.x && state.position.y) {
            const trigger = $('#agentTrigger');
            trigger.style.left = state.position.x;
            trigger.style.bottom = state.position.y;
            trigger.style.right = 'auto';
        }
    }

    // ==================== 事件绑定 ====================
    function bindEvents() {
        $('#agentTrigger').addEventListener('click', (e) => {
            if (state.isDragging) return;
            togglePopup();
        });
        
        $('#agentClose').addEventListener('click', () => {
            togglePopup(false);
        });
        
        $('#btnAnonymous').addEventListener('click', handleAnonymousLogin);
        $('#btnGithub').addEventListener('click', handleGithubLogin);
        
        $('#agentSend').addEventListener('click', handleSend);
        
        $('#agentInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
            }
        });
        
        $('#agentInput').addEventListener('input', (e) => {
            e.target.style.height = 'auto';
            e.target.style.height = Math.min(e.target.scrollHeight, 100) + 'px';
        });

        // 监听系统主题变化
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', updateTheme);
        }
        
        // 监听 Chic 主题切换
        const observer = new MutationObserver(updateTheme);
        observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }

    function togglePopup(show) {
        const popup = $('#agentPopup');
        state.isOpen = show !== undefined ? show : !state.isOpen;
        popup.classList.toggle('active', state.isOpen);
        
        if (state.isOpen) {
            $('#agentInput').focus();
        }
    }

    // ==================== 初始化 ====================
    function init() {
        loadState();
        createWidget();
        restorePosition();
        bindEvents();
        initDrag();
        updateUI();
        updateTheme();
        
        console.log('✅ Hexo Agent Widget 初始化完成');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
