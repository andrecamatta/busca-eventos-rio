// Calendário de Eventos Culturais Rio

let calendar;
let currentEvent = null;
let currentFilters = {
    categoria: '',
    venue: ''
};

// Inicialização
document.addEventListener('DOMContentLoaded', function() {
    initCalendar();
    loadFilters();
    setupEventListeners();
    updateStats();
});

// Inicializar FullCalendar
function initCalendar() {
    const calendarEl = document.getElementById('calendar');

    calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'pt-br',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,dayGridWeek,listWeek'
        },
        buttonText: {
            today: 'Hoje',
            month: 'Mês',
            week: 'Semana',
            list: 'Lista'
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
        if (currentFilters.venue) {
            params.append('venue', currentFilters.venue);
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

        // Carregar venues
        const venueResponse = await fetch('/api/venues');
        const venues = await venueResponse.json();

        const venueSelect = document.getElementById('filter-venue');
        venues.forEach(venue => {
            const option = document.createElement('option');
            option.value = venue;
            option.textContent = venue;
            venueSelect.appendChild(option);
        });

    } catch (error) {
        console.error('Erro ao carregar filtros:', error);
    }
}

// Aplicar filtros
function applyFilters() {
    currentFilters.categoria = document.getElementById('filter-categoria').value;
    currentFilters.venue = document.getElementById('filter-venue').value;

    calendar.refetchEvents();
    showToast('Filtros aplicados', 'success');
}

// Limpar filtros
function clearFilters() {
    document.getElementById('filter-categoria').value = '';
    document.getElementById('filter-venue').value = '';
    currentFilters = { categoria: '', venue: '' };

    calendar.refetchEvents();
    showToast('Filtros removidos', 'info');
}

// Configurar event listeners
function setupEventListeners() {
    // Botão de atualização
    document.getElementById('refresh-btn').addEventListener('click', refreshEvents);

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
    btn.classList.add('spinning');
    btn.disabled = true;

    try {
        const response = await fetch('/api/refresh', { method: 'POST' });
        const data = await response.json();

        showToast('Atualização iniciada! Aguarde alguns minutos...', 'info');

        // Aguardar 30 segundos e recarregar
        setTimeout(() => {
            calendar.refetchEvents();
            updateStats();
        }, 30000);

    } catch (error) {
        console.error('Erro ao atualizar:', error);
        showToast('Erro ao iniciar atualização', 'error');
    } finally {
        setTimeout(() => {
            btn.classList.remove('spinning');
            btn.disabled = false;
        }, 2000);
    }
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
    modalBody.innerHTML = `
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

        ${props.link_ingresso ? `
        <a href="${props.link_ingresso}" target="_blank" class="event-link">
            <i class="fas fa-external-link-alt"></i> Comprar Ingresso
        </a>
        ` : ''}
    `;

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
