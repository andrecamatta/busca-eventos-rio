// Calendário de Eventos Culturais Rio

let calendar;
let currentEvent = null;
let currentFilters = {
    categoria: ''
};

// Detectar dispositivo móvel
function isMobileDevice() {
    return window.innerWidth <= 768 || /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

// Versão do deployment (atualizar quando fizer deploy)
const DEPLOYMENT_VERSION = '2025-11-12-outdoor-fix-deploy';

// Verificar estado de execução ao carregar página
function checkExecutionState() {
    // Limpar localStorage se versão mudou (novo deploy)
    const storedVersion = localStorage.getItem('deployment_version');
    if (storedVersion !== DEPLOYMENT_VERSION) {
        console.log('Nova versão detectada - limpando localStorage');
        localStorage.removeItem('refresh_executed');
        localStorage.removeItem('judge_executed');
        localStorage.setItem('deployment_version', DEPLOYMENT_VERSION);
        return; // Não desabilitar botões
    }

    // Verificar se atualização já foi executada (apenas na mesma versão)
    if (localStorage.getItem('refresh_executed') === 'true') {
        const btn = document.getElementById('refresh-btn');
        btn.disabled = true;
        btn.title = 'Atualização já executada. Recarregue a página para executar novamente.';
    }

    // Verificar se julgamento já foi executado (apenas na mesma versão)
    if (localStorage.getItem('judge_executed') === 'true') {
        const btn = document.getElementById('judge-btn');
        btn.disabled = true;
        btn.title = 'Julgamento já executado. Recarregue a página para executar novamente.';
    }
}

// Inicialização
document.addEventListener('DOMContentLoaded', function() {
    initCalendar();
    loadFilters();
    setupEventListeners();
    updateStats();
    checkExecutionState();
});

// Inicializar FullCalendar
function initCalendar() {
    const calendarEl = document.getElementById('calendar');
    const isMobile = isMobileDevice();

    calendar = new FullCalendar.Calendar(calendarEl, {
        // Forçar modo lista em mobile, calendário em desktop
        initialView: isMobile ? 'listMonth' : 'dayGridMonth',
        locale: 'pt-br',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            // Em mobile, apenas lista; em desktop, todas as opções
            right: isMobile ? '' : 'dayGridMonth,dayGridWeek,listMonth'
        },
        buttonText: {
            today: 'Hoje',
            month: 'Mês',
            week: 'Semana',
            list: 'Lista'
        },
        // Configurar listMonth para mostrar período mais longo
        listDayFormat: { weekday: 'long', month: 'long', day: 'numeric' },
        listDaySideFormat: false,
        // Formato de horário melhorado (20:00 em vez de número quebrado)
        eventTimeFormat: {
            hour: '2-digit',
            minute: '2-digit',
            meridiem: false,
            hour12: false
        },
        events: fetchEvents,
        eventClick: handleEventClick,
        eventDidMount: function(info) {
            // Adicionar tooltip
            info.el.title = info.event.title;
        },
        height: 'auto',
        contentHeight: 600,
        aspectRatio: 1.8,
        expandRows: true,
        slotMinTime: '08:00:00',
        slotMaxTime: '24:00:00',
        nowIndicator: true,
        eventDisplay: 'block',
        displayEventTime: true,
        displayEventEnd: false,
    });

    calendar.render();
}

// Buscar eventos da API
async function fetchEvents(info, successCallback, failureCallback) {
    try {
        // Construir query params com filtros
        const params = new URLSearchParams();
        if (currentFilters.categoria) {
            params.append('categoria', currentFilters.categoria);
        }

        const response = await fetch(`/api/events?${params.toString()}`);
        if (!response.ok) {
            throw new Error('Erro ao carregar eventos');
        }

        const events = await response.json();
        successCallback(events);

        // Atualizar contador
        document.getElementById('event-count').textContent = events.length;

    } catch (error) {
        console.error('Erro ao buscar eventos:', error);
        showToast('Erro ao carregar eventos', 'error');
        failureCallback(error);
    }
}

// Carregar opções de filtros
async function loadFilters() {
    try {
        // Carregar categorias
        const catResponse = await fetch('/api/categories');
        const categorias = await catResponse.json();

        const catSelect = document.getElementById('filter-categoria');
        categorias.forEach(cat => {
            const option = document.createElement('option');
            option.value = cat;
            option.textContent = cat;
            catSelect.appendChild(option);
        });

    } catch (error) {
        console.error('Erro ao carregar filtros:', error);
    }
}

// Aplicar filtros
function applyFilters() {
    currentFilters.categoria = document.getElementById('filter-categoria').value;

    calendar.refetchEvents();
    showToast('Filtros aplicados', 'success');
}

// Limpar filtros
function clearFilters() {
    document.getElementById('filter-categoria').value = '';
    currentFilters = { categoria: '' };

    calendar.refetchEvents();
    showToast('Filtros removidos', 'info');
}

// Configurar event listeners
function setupEventListeners() {
    // Botão de atualização
    document.getElementById('refresh-btn').addEventListener('click', refreshEvents);

    // Botão de julgamento
    document.getElementById('judge-btn').addEventListener('click', startJudgement);

    // Aplicar filtros
    document.getElementById('apply-filters').addEventListener('click', applyFilters);

    // Limpar filtros
    document.getElementById('clear-filters').addEventListener('click', clearFilters);

    // Compartilhar WhatsApp
    document.getElementById('share-whatsapp').addEventListener('click', shareOnWhatsApp);
}

// Atualizar eventos
async function refreshEvents() {
    const btn = document.getElementById('refresh-btn');

    // Verificar se já foi executado nesta sessão (usando localStorage)
    if (localStorage.getItem('refresh_executed') === 'true') {
        showToast('⚠️ Atualização já foi executada nesta sessão. Recarregue a página para executar novamente.', 'warning');
        return;
    }

    btn.classList.add('spinning');
    btn.disabled = true;

    try {
        const response = await fetch('/api/refresh', { method: 'POST' });
        const data = await response.json();

        // Verificar status HTTP
        if (!response.ok) {
            // Erro HTTP (503, 500, etc.)
            console.error('Erro na requisição:', response.status, data);

            if (response.status === 503) {
                // API key não configurada
                showToast('⚠️ Atualização indisponível: API key não configurada', 'error');
            } else {
                // Outros erros
                showToast(data.detail || 'Erro ao iniciar atualização', 'error');
            }
            // Reabilitar botão apenas em caso de erro antes de iniciar
            btn.classList.remove('spinning');
            btn.disabled = false;
            return;
        }

        // Marcar como executado no localStorage (bloqueio permanente até reload)
        localStorage.setItem('refresh_executed', 'true');

        // Sucesso - iniciar polling de status
        showToast('✓ Atualização iniciada! Acompanhando progresso...', 'info');
        pollRefreshStatus();

    } catch (error) {
        console.error('Erro ao atualizar:', error);
        showToast('Erro de conexão ao iniciar atualização', 'error');
        // Restaurar botão em caso de erro de conexão
        setTimeout(() => {
            btn.classList.remove('spinning');
            btn.disabled = false;
        }, 2000);
    }
}

// Fazer polling do status da atualização
async function pollRefreshStatus() {
    const btn = document.getElementById('refresh-btn');
    let pollCount = 0;
    const maxPolls = 120; // 10 minutos (120 * 5s = 600s)

    const interval = setInterval(async () => {
        pollCount++;

        try {
            const response = await fetch('/api/refresh/status');
            const status = await response.json();

            console.log(`[Polling ${pollCount}/${maxPolls}]`, status);

            // Se ainda está rodando, continuar polling
            if (status.is_running) {
                // Atualizar mensagem de progresso
                if (pollCount % 6 === 0) { // A cada 30s
                    const elapsed = status.last_started ?
                        Math.floor((new Date() - new Date(status.last_started)) / 1000) : 0;
                    showToast(`⏳ Atualização em andamento... (${elapsed}s)`, 'info');
                }
                return; // Continuar polling
            }

            // Job terminou - parar polling
            clearInterval(interval);
            btn.classList.remove('spinning');
            // Manter botão desabilitado permanentemente após conclusão

            // Verificar resultado
            if (status.last_result === 'success') {
                showToast(`✅ Atualização concluída com sucesso! (${status.last_duration_seconds}s)`, 'success');
                // Recarregar eventos
                calendar.refetchEvents();
                updateStats();
            } else if (status.last_result === 'error') {
                showToast(`❌ Erro na atualização: ${status.last_error || 'Erro desconhecido'}`, 'error');
                console.error('Detalhes do erro:', status);
                // Em caso de erro durante execução, não permitir nova tentativa
            } else {
                // Resultado desconhecido
                showToast('⚠️ Atualização finalizada com status desconhecido', 'warning');
            }

        } catch (error) {
            console.error('Erro ao consultar status:', error);
            // Continuar tentando por algumas vezes
            if (pollCount >= maxPolls) {
                clearInterval(interval);
                btn.classList.remove('spinning');
                // Manter botão desabilitado mesmo em timeout
                showToast('⚠️ Timeout ao aguardar atualização', 'warning');
            }
        }
    }, 5000); // Polling a cada 5 segundos
}

// Atualizar estatísticas
async function updateStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();

        document.getElementById('event-count').textContent = stats.total_eventos;

    } catch (error) {
        console.error('Erro ao carregar estatísticas:', error);
    }
}

// Tratar clique no evento
function handleEventClick(info) {
    currentEvent = info.event;
    const props = info.event.extendedProps;

    // Preencher modal
    document.getElementById('eventModalTitle').textContent = info.event.title;

    const modalBody = document.getElementById('eventModalBody');

    // Montar HTML com detalhes do evento
    let detailsHTML = `
        <div class="event-detail">
            <div class="event-detail-label"><i class="fas fa-calendar"></i> Data e Horário</div>
            <div class="event-detail-value">${formatDateTime(info.event.start)}</div>
        </div>

        <div class="event-detail">
            <div class="event-detail-label"><i class="fas fa-map-marker-alt"></i> Local</div>
            <div class="event-detail-value">${props.local || 'Não informado'}</div>
        </div>

        <div class="event-detail">
            <div class="event-detail-label"><i class="fas fa-ticket-alt"></i> Preço</div>
            <div class="event-detail-value">${props.preco || 'Consultar'}</div>
        </div>

        ${props.categoria ? `
        <div class="event-detail">
            <div class="event-detail-label"><i class="fas fa-tag"></i> Categoria</div>
            <div class="event-detail-value">${props.categoria}</div>
        </div>
        ` : ''}

        ${props.venue ? `
        <div class="event-detail">
            <div class="event-detail-label"><i class="fas fa-building"></i> Venue</div>
            <div class="event-detail-value">${props.venue}</div>
        </div>
        ` : ''}

        ${props.descricao ? `
        <div class="event-detail">
            <div class="event-detail-label"><i class="fas fa-info-circle"></i> Descrição</div>
            <div class="event-detail-value">${props.descricao}</div>
        </div>
        ` : ''}
    `;

    // Adicionar informações de qualidade se disponíveis
    if (props.quality_score !== undefined && props.quality_score !== null) {
        const badgeColor = getScoreBadgeColor(props.quality_score);
        detailsHTML += `
        <div class="alert alert-${badgeColor} mt-3">
            <h6><i class="fas fa-balance-scale"></i> Avaliação de Qualidade</h6>
            <div class="row">
                <div class="col-6">
                    <strong>Nota Geral:</strong> ${props.quality_score.toFixed(1)}/10
                </div>
                <div class="col-6">
                    <strong>Aderência ao Prompt:</strong> ${(props.prompt_adherence || 0).toFixed(1)}/10
                </div>
            </div>
            <div class="row mt-2">
                <div class="col-12">
                    <strong>Correlação Link-Dados:</strong> ${(props.link_match || 0).toFixed(1)}/10
                </div>
            </div>
            ${props.quality_notes ? `
            <div class="mt-2">
                <small><strong>Observações:</strong> ${props.quality_notes}</small>
            </div>
            ` : ''}
        </div>
        `;
    }

    // Adicionar link de ingresso
    if (props.link_ingresso) {
        detailsHTML += `
        <a href="${props.link_ingresso}" target="_blank" class="event-link event-link-${props.link_type || 'info'}">
            <i class="${getLinkIcon(props.link_type)}"></i> ${getLinkLabel(props.link_type)}
        </a>
        `;
    }

    modalBody.innerHTML = detailsHTML;

    // Mostrar modal
    const modal = new bootstrap.Modal(document.getElementById('eventModal'));
    modal.show();
}

// Compartilhar no WhatsApp
function shareOnWhatsApp() {
    if (!currentEvent) return;

    const props = currentEvent.extendedProps;
    const message = `
🎭 *${currentEvent.title}*

📅 ${formatDateTime(currentEvent.start)}
📍 ${props.local}
💰 ${props.preco}

${props.descricao ? props.descricao.substring(0, 200) + '...' : ''}

${props.link_ingresso ? `🎫 Link: ${props.link_ingresso}` : ''}
    `.trim();

    const encodedMessage = encodeURIComponent(message);
    window.open(`https://wa.me/?text=${encodedMessage}`, '_blank');
}

// Formatar data/hora
function formatDateTime(date) {
    if (!date) return '';

    const options = {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };

    return new Date(date).toLocaleDateString('pt-BR', options);
}

// Mostrar toast
function showToast(message, type = 'info') {
    const toast = document.getElementById('notification-toast');
    const toastBody = document.getElementById('toast-message');

    toastBody.textContent = message;

    // Remover classes anteriores
    toast.classList.remove('bg-success', 'bg-danger', 'bg-info', 'bg-warning');

    // Adicionar classe baseada no tipo
    const colorClass = {
        success: 'bg-success text-white',
        error: 'bg-danger text-white',
        info: 'bg-info text-white',
        warning: 'bg-warning'
    }[type] || 'bg-info text-white';

    toast.classList.add(...colorClass.split(' '));

    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
}

// Iniciar julgamento de qualidade
async function startJudgement() {
    const btn = document.getElementById('judge-btn');

    // Verificar se já foi executado nesta sessão (usando localStorage)
    if (localStorage.getItem('judge_executed') === 'true') {
        showToast('⚠️ Julgamento já foi executado nesta sessão. Recarregue a página para executar novamente.', 'warning');
        return;
    }

    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

    try {
        const response = await fetch('/api/judge', { method: 'POST' });
        const data = await response.json();

        if (!response.ok) {
            if (response.status === 503) {
                showToast('⚠️ Julgamento indisponível: API key não configurada', 'error');
            } else if (response.status === 409) {
                showToast('⚠️ Julgamento já em andamento', 'warning');
            } else {
                showToast(data.detail || 'Erro ao iniciar julgamento', 'error');
            }
            // Reabilitar botão apenas em caso de erro antes de iniciar
            btn.disabled = false;
            btn.innerHTML = originalHTML;
            return;
        }

        // Marcar como executado no localStorage (bloqueio permanente até reload)
        localStorage.setItem('judge_executed', 'true');

        showToast('⚖️ Julgamento iniciado! Aguarde...', 'info');
        pollJudgeStatus(btn, originalHTML);

    } catch (error) {
        console.error('Erro ao iniciar julgamento:', error);
        showToast('Erro de conexão ao iniciar julgamento', 'error');
        // Restaurar botão em caso de erro de conexão
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

// Poll de status do julgamento
async function pollJudgeStatus(btn, originalHTML) {
    let pollCount = 0;
    const maxPolls = 240; // 20 minutos (240 * 5s)

    const interval = setInterval(async () => {
        pollCount++;

        try {
            const response = await fetch('/api/judge/status');
            const status = await response.json();

            console.log(`[Judge Polling ${pollCount}/${maxPolls}]`, status);

            if (status.is_running) {
                // Atualizar progresso a cada 6 polls (30s)
                if (pollCount % 6 === 0 && status.judged_count > 0) {
                    const progress = Math.round((status.judged_count / status.total_events) * 100);
                    showToast(
                        `⚖️ Julgando... ${status.judged_count}/${status.total_events} eventos (${progress}%)`,
                        'info'
                    );
                }
                return; // Continuar polling
            }

            // Job terminou
            clearInterval(interval);
            btn.innerHTML = originalHTML;
            // Manter botão desabilitado permanentemente após conclusão

            if (status.last_result === 'success') {
                showToast(
                    `✅ Julgamento concluído! Nota média: ${status.average_score}/10`,
                    'success'
                );
                // Recarregar eventos com notas
                loadJudgedEvents();
            } else if (status.last_result === 'error') {
                showToast(`❌ Erro no julgamento: ${status.last_error || 'Desconhecido'}`, 'error');
                console.error('Detalhes do erro:', status);
                // Em caso de erro durante execução, não permitir nova tentativa
            } else {
                showToast('⚠️ Julgamento finalizado com status desconhecido', 'warning');
            }

        } catch (error) {
            console.error('Erro ao consultar status do julgamento:', error);
            if (pollCount >= maxPolls) {
                clearInterval(interval);
                btn.innerHTML = originalHTML;
                // Manter botão desabilitado mesmo em timeout
                showToast('⚠️ Timeout ao aguardar julgamento', 'warning');
            }
        }
    }, 5000); // Poll a cada 5 segundos
}

// Carregar eventos julgados
async function loadJudgedEvents() {
    try {
        const response = await fetch('/api/judge/results');

        if (!response.ok) {
            console.log('Nenhum julgamento disponível ainda');
            return;
        }

        const data = await response.json();
        console.log('Eventos julgados carregados:', data.stats);

        // Recarregar calendário (que agora terá as notas)
        calendar.refetchEvents();

    } catch (error) {
        console.error('Erro ao carregar eventos julgados:', error);
    }
}

// Obter cor do badge baseado na nota
function getScoreBadgeColor(score) {
    if (score >= 8) return 'success';  // Verde
    if (score >= 5) return 'warning';  // Amarelo
    return 'danger';  // Vermelho
}

// Obter ícone baseado no tipo de link
function getLinkIcon(linkType) {
    const icons = {
        'purchase': 'fas fa-shopping-cart',  // Plataforma de venda
        'info': 'fas fa-info-circle',        // Site informativo
        'venue': 'fas fa-building'           // Página do venue
    };
    return icons[linkType] || 'fas fa-external-link-alt';
}

// Obter label baseado no tipo de link
function getLinkLabel(linkType) {
    const labels = {
        'purchase': 'Comprar Ingresso',     // Link direto de compra
        'info': 'Mais Informações',         // Site do artista ou informativo
        'venue': 'Site do Local'            // Homepage do venue
    };
    return labels[linkType] || 'Mais Informações';
}
