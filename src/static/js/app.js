document.addEventListener('DOMContentLoaded', () => {
    // Socket.io setup
    const socket = io();
    let activeConversationId = null;
    let isConversationActive = false;
    let currentConversationDetails = null;

    // DOM Elements
    const startBtn = document.getElementById('startBtn');
    const pauseBtn = document.getElementById('pauseBtn');
    const exportCSVBtn = document.getElementById('exportCSVBtn');
    const exportTXTBtn = document.getElementById('exportTXTBtn');
    const newConversationBtn = document.getElementById('newConversationBtn');
    const conversationsList = document.getElementById('conversationsList');
    const conversationEl = document.getElementById('conversation');
    const statusMessage = document.getElementById('statusMessage');
    const connectionStatus = document.getElementById('connectionStatus');
    const connectionIndicator = document.getElementById('connectionIndicator');
    
    // Modal elements
    const modal = document.getElementById('conversationDetailsModal');
    const closeModal = document.querySelector('.close-modal');
    const modalTimestamp = document.getElementById('modalTimestamp');
    const modalBot1Name = document.getElementById('modalBot1Name');
    const modalBot1Model = document.getElementById('modalBot1Model');
    const modalBot1SystemPrompt = document.getElementById('modalBot1SystemPrompt');
    const modalBot2Name = document.getElementById('modalBot2Name');
    const modalBot2Model = document.getElementById('modalBot2Model');
    const modalBot2SystemPrompt = document.getElementById('modalBot2SystemPrompt');
    const loadConversationBtn = document.getElementById('loadConversationBtn');
    const deleteConversationBtn = document.getElementById('deleteConversationBtn');
    
    // Bot settings fields
    const bot1Name = document.getElementById('bot1Name');
    const bot1Model = document.getElementById('bot1Model');
    const bot1SystemPrompt = document.getElementById('bot1SystemPrompt');
    const bot2Name = document.getElementById('bot2Name');
    const bot2Model = document.getElementById('bot2Model');
    const bot2SystemPrompt = document.getElementById('bot2SystemPrompt');
    const initialMessage = document.getElementById('initialMessage');
    
    // Load conversations on page load
    loadConversations();
    
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
    newConversationBtn.addEventListener('click', resetConversation);
    
    // Modal event handlers
    closeModal.addEventListener('click', () => modal.style.display = 'none');
    window.addEventListener('click', (event) => {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
    loadConversationBtn.addEventListener('click', loadSelectedConversation);
    deleteConversationBtn.addEventListener('click', deleteSelectedConversation);
    
    // Changes to system prompts during active conversation
    bot1SystemPrompt.addEventListener('change', updateSystemPrompts);
    bot2SystemPrompt.addEventListener('change', updateSystemPrompts);
    
    // Functions
    function loadConversations() {
        fetch('/api/conversations')
            .then(response => response.json())
            .then(data => {
                conversationsList.innerHTML = '';
                if (data.conversations && data.conversations.length > 0) {
                    data.conversations.forEach(conversation => {
                        const item = document.createElement('div');
                        item.className = 'conversation-item';
                        item.dataset.id = conversation.id;
                        
                        const title = document.createElement('div');
                        title.className = 'conversation-title';
                        title.textContent = `${conversation.bot1_name} & ${conversation.bot2_name}`;
                        
                        const date = document.createElement('div');
                        date.className = 'conversation-date';
                        date.textContent = conversation.timestamp;
                        
                        item.appendChild(title);
                        item.appendChild(date);
                        
                        item.addEventListener('click', () => openConversationDetails(conversation));
                        
                        conversationsList.appendChild(item);
                    });
                } else {
                    const noConversations = document.createElement('div');
                    noConversations.className = 'no-conversations';
                    noConversations.textContent = '還沒有對話記錄';
                    conversationsList.appendChild(noConversations);
                }
            })
            .catch(error => {
                console.error('Failed to load conversations:', error);
                setStatus('載入對話歷史失敗', true);
            });
    }
    
    function openConversationDetails(conversation) {
        currentConversationDetails = conversation;
        
        modalTimestamp.textContent = conversation.timestamp;
        modalBot1Name.textContent = conversation.bot1_name;
        modalBot1Model.textContent = conversation.bot1_model;
        modalBot1SystemPrompt.textContent = conversation.bot1_system_prompt;
        
        modalBot2Name.textContent = conversation.bot2_name;
        modalBot2Model.textContent = conversation.bot2_model;
        modalBot2SystemPrompt.textContent = conversation.bot2_system_prompt;
        
        modal.style.display = 'block';
    }
    
    function loadSelectedConversation() {
        if (!currentConversationDetails) return;
        
        const conversationId = currentConversationDetails.id;
        
        // Reset current conversation state
        if (isConversationActive) {
            socket.emit('pause_conversation', (response) => {
                resetConversationUI();
                loadConversationMessages(conversationId);
            });
        } else {
            resetConversationUI();
            loadConversationMessages(conversationId);
        }
        
        // Update form fields with conversation settings
        bot1Name.value = currentConversationDetails.bot1_name;
        bot1SystemPrompt.value = currentConversationDetails.bot1_system_prompt;
        bot1Model.value = currentConversationDetails.bot1_model;
        
        bot2Name.value = currentConversationDetails.bot2_name;
        bot2SystemPrompt.value = currentConversationDetails.bot2_system_prompt;
        bot2Model.value = currentConversationDetails.bot2_model;
        
        // Close the modal
        modal.style.display = 'none';
    }
    
    function loadConversationMessages(conversationId) {
        fetch(`/api/conversation/${conversationId}`)
            .then(response => response.json())
            .then(data => {
                if (data.messages && data.messages.length > 0) {
                    conversationEl.innerHTML = '';
                    
                    data.messages.forEach(message => {
                        addMessage(message.bot_name, message.content, message.timestamp);
                    });
                    
                    scrollToBottom();
                    activeConversationId = conversationId;
                    setStatus(`已載入對話 (ID: ${conversationId})`);
                }
            })
            .catch(error => {
                console.error('Failed to load conversation messages:', error);
                setStatus('載入對話訊息失敗', true);
            });
    }
    
    function deleteSelectedConversation() {
        if (!currentConversationDetails) return;
        
        const conversationId = currentConversationDetails.id;
        
        if (confirm(`確定要刪除這個對話嗎？此操作無法撤銷。`)) {
            fetch(`/api/conversation/${conversationId}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    setStatus(`對話已刪除 (ID: ${conversationId})`);
                    loadConversations();
                    
                    // If currently viewing the deleted conversation, reset the UI
                    if (activeConversationId === conversationId) {
                        resetConversationUI();
                    }
                    
                    modal.style.display = 'none';
                } else {
                    setStatus(`刪除對話失敗: ${data.error || '未知錯誤'}`, true);
                }
            })
            .catch(error => {
                console.error('Failed to delete conversation:', error);
                setStatus('刪除對話失敗', true);
            });
        }
    }
    
    function resetConversation() {
        if (isConversationActive) {
            if (confirm('目前對話尚在進行中，確定要開始新對話嗎？')) {
                socket.emit('pause_conversation', (response) => {
                    resetConversationUI();
                });
            }
        } else {
            resetConversationUI();
        }
    }
    
    function resetConversationUI() {
        conversationEl.innerHTML = '';
        activeConversationId = null;
        isConversationActive = false;
        updateButtonStates();
        
        // Reset bot configuration to defaults if needed
        // bot1Name.value = 'Bot 1';
        // bot1SystemPrompt.value = '您是一個有用的AI助手。請用中文回答問題。';
        // bot2Name.value = 'Bot 2';
        // bot2SystemPrompt.value = '您是一個有用的AI助手，擅長問有深度的問題。請用中文回答。';
        // initialMessage.value = '你好！讓我們開始對話吧。';
        
        setStatus('已準備好新對話');
    }
    
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
                
                // Refresh the conversations list
                loadConversations();
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