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
    const conversationTitle = document.getElementById('conversationTitle');
    
    // Token stats elements
    const totalTokensElement = document.getElementById('totalTokens');
    const totalCostElement = document.getElementById('totalCost');
    const bot1TokensElement = document.getElementById('bot1Tokens');
    const bot1CostElement = document.getElementById('bot1Cost');
    const bot1StatsNameElement = document.getElementById('bot1StatsName');
    const bot2TokensElement = document.getElementById('bot2Tokens');
    const bot2CostElement = document.getElementById('bot2Cost');
    const bot2StatsNameElement = document.getElementById('bot2StatsName');
    const modalTotalTokensElement = document.getElementById('modalTotalTokens');
    const modalTotalCostElement = document.getElementById('modalTotalCost');
    
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
    
    socket.on('token_stats_update', (data) => {
        updateTokenStats(data);
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
                        
                        // 优先使用自定义标题，如果没有则显示默认格式
                        if (conversation.title) {
                            title.textContent = conversation.title;
                        } else {
                            title.textContent = `${conversation.bot1_name} & ${conversation.bot2_name}`;
                        }
                        
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
        
        // Update token stats in modal
        updateModalTokenStats(conversation);
        
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
                    
                    // Update token stats if available
                    if (data.token_stats) {
                        updateTokenStats(data.token_stats);
                    }
                    
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
        
        // Reset token statistics display
        totalTokensElement.textContent = '0';
        totalCostElement.textContent = 'NT$ 0.00 ($ 0.0000)';
        bot1StatsNameElement.textContent = 'Bot 1';
        bot1TokensElement.textContent = '0';
        bot1CostElement.textContent = 'NT$ 0.00 ($ 0.0000)';
        bot2StatsNameElement.textContent = 'Bot 2';
        bot2TokensElement.textContent = '0';
        bot2CostElement.textContent = 'NT$ 0.00 ($ 0.0000)';
        
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
            
            initial_message: initialMessage.value.trim() || 'Hello!',
            
            // 添加自定义对话标题
            conversation_title: conversationTitle.value.trim() || null
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
        // 簡化邏輯判斷，確保按鈕功能穩定
        if (pauseBtn.disabled) return;
        
        if (isConversationActive) {
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
        console.log('Adding message:', botName, text.substring(0, 30) + '...', timestamp); // 增加調試日誌
        
        const messageEl = document.createElement('div');
        // 修正判斷邏輯，確保正確分配bot1或bot2樣式
        messageEl.className = 'message';
        if (botName === bot1Name.value || (bot1Name.value === '' && botName === 'Bot 1')) {
            messageEl.classList.add('bot1');
        } else {
            messageEl.classList.add('bot2');
        }
        
        const headerEl = document.createElement('div');
        headerEl.className = 'message-header';
        headerEl.innerHTML = `<strong>${botName}</strong><span>${timestamp || new Date().toLocaleString()}</span>`;
        
        const contentEl = document.createElement('div');
        contentEl.className = 'message-content';
        
        // 支持顯示換行
        contentEl.innerText = text;
        
        messageEl.appendChild(headerEl);
        messageEl.appendChild(contentEl);
        conversationEl.appendChild(messageEl);
        
        // 確保消息顯示後立即滾動到底部，強制使用requestAnimationFrame確保UI更新
        requestAnimationFrame(() => {
            scrollToBottom();
        });
    }
    
    function setStatus(message, isError = false) {
        statusMessage.textContent = message;
        statusMessage.style.color = isError ? '#f44336' : '#fff';
    }
    
    function updateButtonStates() {
        // 修正按鈕狀態邏輯，確保暫停後可以重新開始對話
        startBtn.disabled = isConversationActive;
        pauseBtn.disabled = !activeConversationId; // 只要有對話ID，就能暫停/繼續
        
        // 表單元素禁用邏輯
        bot1Name.disabled = isConversationActive;
        bot1Model.disabled = isConversationActive;
        bot2Name.disabled = isConversationActive;
        bot2Model.disabled = isConversationActive;
        initialMessage.disabled = isConversationActive;
        
        // 更新暫停/繼續按鈕文字
        if (isConversationActive) {
            pauseBtn.innerHTML = '<i class="fas fa-pause"></i> 暫停';
        } else if (activeConversationId) {
            pauseBtn.innerHTML = '<i class="fas fa-play"></i> 繼續';
        }
    }
    
    function scrollToBottom() {
        const container = document.querySelector('.conversation-container');
        if (container) {
            // 使用setTimeout確保在DOM完全更新後執行滾動
            setTimeout(() => {
                container.scrollTop = container.scrollHeight;
            }, 0);
        }
    }

    // Update token stats in the UI
    function updateTokenStats(data) {
        if (!data) return;
        
        // Update total tokens and cost
        totalTokensElement.textContent = data.total_tokens || 0;
        
        // 显示新台币和美元价格
        const totalTwd = data.total_cost || 0;
        const totalUsd = data.total_cost_usd || (totalTwd / 31.5); // 如果后端没有提供，则使用估算值
        totalCostElement.textContent = `NT$ ${totalTwd.toFixed(2)} ($ ${totalUsd.toFixed(4)})`;
        
        // Update bot specific stats
        if (data.bot_stats) {
            const botNames = Object.keys(data.bot_stats);
            
            if (botNames.length > 0) {
                const firstBotName = botNames[0];
                const firstBotStats = data.bot_stats[firstBotName];
                bot1StatsNameElement.textContent = firstBotName;
                bot1TokensElement.textContent = firstBotStats.total_tokens || 0;
                
                const bot1Twd = firstBotStats.cost || 0;
                const bot1Usd = firstBotStats.cost_usd || (bot1Twd / 31.5);
                bot1CostElement.textContent = `NT$ ${bot1Twd.toFixed(2)} ($ ${bot1Usd.toFixed(4)})`;
            }
            
            if (botNames.length > 1) {
                const secondBotName = botNames[1];
                const secondBotStats = data.bot_stats[secondBotName];
                bot2StatsNameElement.textContent = secondBotName;
                bot2TokensElement.textContent = secondBotStats.total_tokens || 0;
                
                const bot2Twd = secondBotStats.cost || 0;
                const bot2Usd = secondBotStats.cost_usd || (bot2Twd / 31.5);
                bot2CostElement.textContent = `NT$ ${bot2Twd.toFixed(2)} ($ ${bot2Usd.toFixed(4)})`;
            }
        }
    }

    // Update token stats in the modal
    function updateModalTokenStats(conversation) {
        if (conversation && conversation.total_tokens !== undefined) {
            modalTotalTokensElement.textContent = conversation.total_tokens;
            
            // 计算美元价格（如果有新台币价格但没有美元价格）
            const totalTwd = parseFloat(conversation.total_cost || 0);
            const totalUsd = conversation.total_cost_usd || (totalTwd / 31.5);
            modalTotalCostElement.textContent = `NT$ ${totalTwd.toFixed(2)} ($ ${totalUsd.toFixed(4)})`;
        } else {
            modalTotalTokensElement.textContent = '0';
            modalTotalCostElement.textContent = 'NT$ 0.00 ($ 0.0000)';
        }
    }
});