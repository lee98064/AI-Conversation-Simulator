document.addEventListener('DOMContentLoaded', () => {
    // Socket.io setup
    const socket = io();
    let activeConversationId = null;
    let isConversationActive = false;

    // DOM Elements
    const startBtn = document.getElementById('startBtn');
    const pauseBtn = document.getElementById('pauseBtn');
    const exportCSVBtn = document.getElementById('exportCSVBtn');
    const exportTXTBtn = document.getElementById('exportTXTBtn');
    const conversationEl = document.getElementById('conversation');
    const statusMessage = document.getElementById('statusMessage');
    const connectionStatus = document.getElementById('connectionStatus');
    const connectionIndicator = document.getElementById('connectionIndicator');
    
    // Bot settings fields
    const bot1Name = document.getElementById('bot1Name');
    const bot1Model = document.getElementById('bot1Model');
    const bot1SystemPrompt = document.getElementById('bot1SystemPrompt');
    const bot2Name = document.getElementById('bot2Name');
    const bot2Model = document.getElementById('bot2Model');
    const bot2SystemPrompt = document.getElementById('bot2SystemPrompt');
    const initialMessage = document.getElementById('initialMessage');
    
    // Socket event handlers
    socket.on('connect', () => {
        connectionStatus.textContent = '已連線';
        connectionIndicator.classList.remove('disconnected');
        connectionIndicator.classList.add('connected');
        setStatus('已連線到伺服器');
    });
    
    socket.on('disconnect', () => {
        connectionStatus.textContent = '未連線';
        connectionIndicator.classList.remove('connected');
        connectionIndicator.classList.add('disconnected');
        setStatus('已斷開與伺服器的連線');
        isConversationActive = false;
        updateButtonStates();
    });
    
    socket.on('new_message', (data) => {
        addMessage(data.bot, data.message, data.timestamp);
        scrollToBottom();
    });
    
    socket.on('error', (data) => {
        setStatus(`錯誤: ${data.message}`, true);
    });
    
    // Button event handlers
    startBtn.addEventListener('click', startConversation);
    pauseBtn.addEventListener('click', togglePause);
    exportCSVBtn.addEventListener('click', () => exportConversation('csv'));
    exportTXTBtn.addEventListener('click', () => exportConversation('txt'));
    
    // Changes to system prompts during active conversation
    bot1SystemPrompt.addEventListener('change', updateSystemPrompts);
    bot2SystemPrompt.addEventListener('change', updateSystemPrompts);
    
    // Functions
    function startConversation() {
        if (isConversationActive) return;
        
        // Get bot configurations
        const config = {
            bot1_name: bot1Name.value.trim() || 'Bot 1',
            bot1_system_prompt: bot1SystemPrompt.value.trim(),
            bot1_model: bot1Model.value,
            
            bot2_name: bot2Name.value.trim() || 'Bot 2',
            bot2_system_prompt: bot2SystemPrompt.value.trim(),
            bot2_model: bot2Model.value,
            
            initial_message: initialMessage.value.trim() || 'Hello!'
        };
        
        // Clear previous conversation
        conversationEl.innerHTML = '';
        
        // Emit start conversation event
        socket.emit('start_conversation', config, (response) => {
            if (response && response.status === 'success') {
                activeConversationId = response.conversation_id;
                isConversationActive = true;
                setStatus(`對話已開始 (ID: ${activeConversationId})`);
                updateButtonStates();
            } else {
                setStatus(`無法開始對話: ${response?.message || '未知錯誤'}`, true);
            }
        });
    }
    
    function togglePause() {
        if (!isConversationActive && !pauseBtn.textContent.includes('繼續')) return;
        
        if (pauseBtn.textContent.includes('暫停')) {
            socket.emit('pause_conversation', (response) => {
                if (response && response.status === 'success') {
                    isConversationActive = false;
                    pauseBtn.innerHTML = '<i class="fas fa-play"></i> 繼續';
                    setStatus('對話已暫停');
                    updateButtonStates();
                } else {
                    setStatus('暫停對話失敗', true);
                }
            });
        } else {
            socket.emit('resume_conversation', (response) => {
                if (response && response.status === 'success') {
                    isConversationActive = true;
                    pauseBtn.innerHTML = '<i class="fas fa-pause"></i> 暫停';
                    setStatus('對話已繼續');
                    updateButtonStates();
                } else {
                    setStatus(`無法繼續對話: ${response?.message || '未知錯誤'}`, true);
                }
            });
        }
    }
    
    function updateSystemPrompts() {
        if (!isConversationActive) return;
        
        const updatedPrompts = {
            bot1_system_prompt: bot1SystemPrompt.value.trim(),
            bot2_system_prompt: bot2SystemPrompt.value.trim()
        };
        
        socket.emit('update_system_prompts', updatedPrompts, (response) => {
            if (response && response.status === 'success') {
                setStatus('系統提示詞已更新');
            } else {
                setStatus(`無法更新系統提示詞: ${response?.message || '未知錯誤'}`, true);
            }
        });
    }
    
    function exportConversation(format) {
        if (!activeConversationId) {
            setStatus('沒有可匯出的對話', true);
            return;
        }
        
        const url = `/api/conversation/${activeConversationId}/export?format=${format}`;
        window.open(url, '_blank');
    }
    
    function addMessage(botName, text, timestamp) {
        const messageEl = document.createElement('div');
        messageEl.className = `message ${botName === bot1Name.value ? 'bot1' : 'bot2'}`;
        
        const headerEl = document.createElement('div');
        headerEl.className = 'message-header';
        headerEl.innerHTML = `<strong>${botName}</strong><span>${timestamp}</span>`;
        
        const contentEl = document.createElement('div');
        contentEl.className = 'message-content';
        contentEl.textContent = text;
        
        messageEl.appendChild(headerEl);
        messageEl.appendChild(contentEl);
        conversationEl.appendChild(messageEl);
    }
    
    function setStatus(message, isError = false) {
        statusMessage.textContent = message;
        statusMessage.style.color = isError ? '#f44336' : '#fff';
    }
    
    function updateButtonStates() {
        startBtn.disabled = isConversationActive;
        pauseBtn.disabled = !isConversationActive;
        
        bot1Name.disabled = isConversationActive;
        bot1Model.disabled = isConversationActive;
        bot2Name.disabled = isConversationActive;
        bot2Model.disabled = isConversationActive;
        initialMessage.disabled = isConversationActive;
    }
    
    function scrollToBottom() {
        const container = document.querySelector('.conversation-container');
        container.scrollTop = container.scrollHeight;
    }
});