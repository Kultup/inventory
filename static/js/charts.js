// Конфігурація кольорів для графіків
const CHART_COLORS = {
    primary: '#0d6efd',
    success: '#198754',
    warning: '#ffc107',
    danger: '#dc3545',
    info: '#0dcaf0',
    secondary: '#6c757d',
    purple: '#6f42c1',
    pink: '#d63384',
    orange: '#fd7e14',
    teal: '#20c997'
};

const BACKGROUND_COLORS = [
    'rgba(13, 110, 253, 0.7)',
    'rgba(25, 135, 84, 0.7)',
    'rgba(255, 193, 7, 0.7)',
    'rgba(220, 53, 69, 0.7)',
    'rgba(13, 202, 240, 0.7)',
    'rgba(108, 117, 125, 0.7)',
    'rgba(111, 66, 193, 0.7)',
    'rgba(214, 51, 132, 0.7)'
];

const BORDER_COLORS = [
    'rgba(13, 110, 253, 1)',
    'rgba(25, 135, 84, 1)',
    'rgba(255, 193, 7, 1)',
    'rgba(220, 53, 69, 1)',
    'rgba(13, 202, 240, 1)',
    'rgba(108, 117, 125, 1)',
    'rgba(111, 66, 193, 1)',
    'rgba(214, 51, 132, 1)'
];

// Кругова діаграма: Розподіл за статусами
async function loadDevicesByStatusChart() {
    try {
        const response = await fetch('/admin/api/chart/devices-by-status');
        const data = await response.json();
        
        const ctx = document.getElementById('devicesStatusChart');
        if (!ctx) return;
        
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Кількість пристроїв',
                    data: data.data,
                    backgroundColor: BACKGROUND_COLORS,
                    borderColor: BORDER_COLORS,
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 15,
                            font: {
                                size: 12
                            }
                        }
                    },
                    title: {
                        display: true,
                        text: 'Розподіл пристроїв за статусами',
                        font: {
                            size: 16,
                            weight: 'bold'
                        },
                        padding: {
                            top: 10,
                            bottom: 20
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.label || '';
                                let value = context.parsed || 0;
                                let total = context.dataset.data.reduce((a, b) => a + b, 0);
                                let percentage = ((value / total) * 100).toFixed(1);
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Помилка завантаження графіка статусів:', error);
    }
}

// Барна діаграма: Розподіл за типами
async function loadDevicesByTypeChart() {
    try {
        const response = await fetch('/admin/api/chart/devices-by-type');
        const data = await response.json();
        
        const ctx = document.getElementById('devicesTypeChart');
        if (!ctx) return;
        
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Кількість пристроїв',
                    data: data.data,
                    backgroundColor: CHART_COLORS.primary,
                    borderColor: CHART_COLORS.primary,
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    title: {
                        display: true,
                        text: 'Топ-10 типів обладнання',
                        font: {
                            size: 16,
                            weight: 'bold'
                        },
                        padding: {
                            top: 10,
                            bottom: 20
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Помилка завантаження графіка типів:', error);
    }
}

// Лінійний графік: Динаміка додавання
async function loadDevicesByMonthChart() {
    try {
        const response = await fetch('/admin/api/chart/devices-by-month');
        const data = await response.json();
        
        const ctx = document.getElementById('devicesMonthChart');
        if (!ctx) return;
        
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Додано пристроїв',
                    data: data.data,
                    fill: true,
                    backgroundColor: 'rgba(13, 110, 253, 0.1)',
                    borderColor: CHART_COLORS.primary,
                    borderWidth: 2,
                    tension: 0.4,
                    pointRadius: 4,
                    pointBackgroundColor: CHART_COLORS.primary,
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    title: {
                        display: true,
                        text: 'Динаміка додавання пристроїв (12 місяців)',
                        font: {
                            size: 16,
                            weight: 'bold'
                        },
                        padding: {
                            top: 10,
                            bottom: 20
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Помилка завантаження графіка за місяцями:', error);
    }
}

// Горизонтальна барна діаграма: Розподіл за містами
async function loadDevicesByCityChart() {
    try {
        const response = await fetch('/admin/api/chart/devices-by-city');
        const data = await response.json();
        
        const ctx = document.getElementById('devicesCityChart');
        if (!ctx) return;
        
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Кількість пристроїв',
                    data: data.data,
                    backgroundColor: BACKGROUND_COLORS,
                    borderColor: BORDER_COLORS,
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    title: {
                        display: true,
                        text: 'Розподіл обладнання за містами',
                        font: {
                            size: 16,
                            weight: 'bold'
                        },
                        padding: {
                            top: 10,
                            bottom: 20
                        }
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Помилка завантаження графіка за містами:', error);
    }
}

// Ініціалізація всіх графіків при завантаженні сторінки
document.addEventListener('DOMContentLoaded', function() {
    loadDevicesByStatusChart();
    loadDevicesByTypeChart();
    loadDevicesByMonthChart();
    loadDevicesByCityChart();
});

