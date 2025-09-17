// Professional Trading Dashboard - Clean Version
// Chart.js is loaded globally from the HTML <script> tag.

class TradingDashboard {
    setChartInterval(interval) {
    this.chartInterval = interval;

    // Remove 'active' class from all buttons
    document.querySelectorAll('.chart-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    // Add 'active' class only to the clicked button
    const activeBtn = document.querySelector(`.chart-btn[data-interval="${interval}"]`);
    if (activeBtn) activeBtn.classList.add('active');

    // Reload chart data
    this.loadChartData();
}


    constructor() {
        // --- Core properties ---
        this.currentSymbol = 'BTCUSDT';
        this.chartInterval = '1m';
        this.isConnected = false;
        this.socket = null;
        this.priceChart = null;

        // Kick off the dashboard
        this.init();
    }

    // ========= Initialization =========
    init() {
        this.setupSocketConnection();
        this.setupEventListeners();
        this.initializeChart();
        this.loadInitialData();
        this.startRealTimeUpdates();
    }

    // --------------------
// Socket & Real-Time Updates
// --------------------
setupSocketConnection() {
    this.socket = io(); // Connect to server

    // Connected
    this.socket.on('connect', () => {
        this.isConnected = true;
        this.updateConnectionStatus('connected', 'Connected');
        this.showToast('Connected to server', 'success');
        this.socket.emit('subscribe_symbol', this.currentSymbol);
    });

    // Disconnected
    this.socket.on('disconnect', () => {
        this.isConnected = false;
        this.updateConnectionStatus('disconnected', 'Disconnected');
        this.showToast('Disconnected from server', 'error');
    });

    // Price update (chart + ticker)
    let lastChartUpdate = 0; // throttle chart updates to once per second
    this.socket.on('price_update', (data) => {
        this.updatePriceTicker(data);
        const now = Date.now();
        if (now - lastChartUpdate > 1000) {
            this.updateChart(data);
            lastChartUpdate = now;
        }
    });

    // Order book updates

    this.socket.on('orderbook_update', (data) => this.updateOrderBook(data));
this.socket.on('price_update', (data) => {
    console.log('Price update:', data); // Debug
    this.updateChart(data);  // call chart updater
});

    // Recent trades updates
this.socket.on('recent_trades', (data) => {
    console.log('Recent trades received:', data); // DEBUG
    this.updateRecentTrades(data);
});

    // Account balance / portfolio updates
    this.socket.on('account_update', (data) => {
        this.updateAccountBalance(data);
        this.updatePortfolio(data);
    });

    // Open orders updates
    this.socket.on('orders_update', (data) => this.updateOpenOrders(data));

    // Order history updates
    this.socket.on('order_history', (data) => this.updateOrderHistory(data));

    // Order placement response
    this.socket.on('order_response', (data) => {
        if (data.success) {
            this.showToast(`Order placed successfully! ID: ${data.orderId}`, 'success');
            this.refreshOrders();
        } else {
            this.showToast(`Order failed: ${data.error}`, 'error');
        }
        this.hideLoading();
    });
}

// --------------------
// Remove setInterval polling
// --------------------
// No need for startRealTimeUpdates() at all, because everything is pushed by server
// Optional: If you need, you can add a heartbeat to request updates manually:
requestUpdates() {
    if (this.isConnected) {
        this.socket.emit('request_account_update');
        this.socket.emit('request_orders_update');
    }
}

    // ========= UI Event Listeners =========
    setupEventListeners() {
        document.getElementById('symbolSelect').addEventListener('change', (e) => {
            this.currentSymbol = e.target.value;
            this.socket.emit('subscribe_symbol', this.currentSymbol);
            this.loadChartData();
        });

        document.querySelectorAll('.tab-btn').forEach(btn =>
            btn.addEventListener('click', e => this.setOrderSide(e.target.dataset.side))
        );

        document.getElementById('orderType').addEventListener('change', e =>
            this.toggleOrderFields(e.target.value)
        );

        document.querySelectorAll('.chart-btn').forEach(btn =>
            btn.addEventListener('click', e => this.setChartInterval(e.target.dataset.interval))
        );

        document.getElementById('placeOrderBtn').addEventListener('click', () => this.placeOrder());
        document.getElementById('refreshOrders').addEventListener('click', () => this.refreshOrders());
        document.getElementById('historyFilter').addEventListener('change', e =>
            this.filterOrderHistory(e.target.value)
        );

        document.getElementById('currentPrice').addEventListener('click', () => {
            const priceInput = document.getElementById('price');
            const currentPrice = document.getElementById('currentPrice').textContent.replace('$', '');
            if (priceInput.style.display !== 'none') {
                priceInput.value = currentPrice;
            }
        });
    }

    // ========= Chart =========
    initializeChart() {
        const ctx = document.getElementById('priceChart').getContext('2d');

        this.priceChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Price',
                    data: [],
                    borderColor: '#0969da',
                    backgroundColor: 'rgba(9,105,218,0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.1,
                    pointRadius: 0,
                    pointHoverRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: {
                        grid: { color: '#30363d', drawBorder: false },
                        ticks: { color: '#8b949e', maxTicksLimit: 8 }
                    },
                    y: {
                        grid: { color: '#30363d', drawBorder: false },
                        ticks: {
                            color: '#8b949e',
                            callback: v => '$' + v.toFixed(2)
                        }
                    }
                },
                interaction: { intersect: false, mode: 'index' }
            }
        });
    }

    // ========= Data Loading =========
    async loadInitialData() {
        try {
            const balanceResponse = await fetch('/api/account/balance');
            const balanceData = await balanceResponse.json();
            if (balanceData.success) {
                this.updateAccountBalance(balanceData.data);
                this.updatePortfolio(balanceData.data);
            }

            this.refreshOrders();

            const historyResponse = await fetch('/api/orders/history');
            const historyData = await historyResponse.json();
            if (historyData.success) {
                this.updateOrderHistory(historyData.data);
            }

            this.loadChartData();
        } catch (error) {
            console.error('Error loading initial data:', error);
            this.showToast('Error loading initial data', 'error');
        }
    }

    async loadChartData() {
        try {
            const res = await fetch(`/api/klines/${this.currentSymbol}?interval=${this.chartInterval}&limit=100`);
            const data = await res.json();
            if (data.success) {
                const chartData = data.data.map(k => ({
                    time: new Date(k[0]).toLocaleTimeString(),
                    price: parseFloat(k[4])
                }));
                this.priceChart.data.labels = chartData.map(d => d.time);
                this.priceChart.data.datasets[0].data = chartData.map(d => d.price);
                this.priceChart.update('none');
            }
        } catch (err) {
            console.error('Error loading chart data:', err);
        }
    }

    // ========= Placeholders for rest of your original methods =========
    //startRealTimeUpdates() {}
    //refreshOrders() {}
    //showToast(msg, type) { console.log(`[${type}] ${msg}`); }
    updateConnectionStatus(status, text) {
        const el = document.getElementById('connectionStatus');
        if (!el) return;
        const circle = el.querySelector('i');
        const span = el.querySelector('span');
        span.textContent = text;
        circle.style.color = (status === 'connected') ? 'limegreen' : 'red';
}

    // Add your own real implementations of:
    // updatePriceTicker, updateChart, updateOrderBook, updateRecentTrades,
    // updateAccountBalance, updatePortfolio, updateOpenOrders,
    // updateOrderHistory, setOrderSide, toggleOrderFields,
    // setChartInterval, placeOrder, filterOrderHistory, hideLoading…

updateRecentTrades(data) {
    const tradesContainer = document.getElementById('recentTrades');
    tradesContainer.innerHTML = ''; // Clear previous trades

    if (!data || data.length === 0) {
        tradesContainer.innerHTML = '<div class="no-data">No recent trades</div>';
        return;
    }

    // Take latest 20 trades
    data.slice(0, 20).forEach(trade => {
        const row = document.createElement('div');
        row.className = 'trade-row';
        const isBuyerMaker = trade.isBuyerMaker;
        row.innerHTML = `
            <span class="trade-price ${isBuyerMaker ? 'sell' : 'buy'}">${parseFloat(trade.price).toFixed(2)}</span>
            <span class="trade-quantity">${parseFloat(trade.qty).toFixed(4)}</span>
            <span class="trade-time">${new Date(trade.time).toLocaleTimeString()}</span>
        `;
        tradesContainer.appendChild(row);
    });
}
updateChart(data) {
    if (!this.priceChart || !data.price) return;

    const currentTime = new Date().toLocaleTimeString();
    const price = parseFloat(data.price);

    // Add new data point
    this.priceChart.data.labels.push(currentTime);
    this.priceChart.data.datasets[0].data.push(price);

    // Keep only last 50 data points to avoid overload
    if (this.priceChart.data.labels.length > 50) {
        this.priceChart.data.labels.shift();
        this.priceChart.data.datasets[0].data.shift();
    }

    // Update the chart
    this.priceChart.update('none');
}

}

// ========= Single Initialization =========
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new TradingDashboard();
});
