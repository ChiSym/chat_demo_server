const ACTIVE_COLOR = 'rgba(75, 192, 192, 1)'
const INACTIVE_COLOR ='rgba(75, 192, 192, 0.2)' 

function nextWidget() {
    const L = this.items.length
    this.index++;
    this.index = ((this.index % L)+L)%L;
}

function prevWidget() {
    const L = this.items.length
    this.index--;
    this.index = ((this.index % L)+L)%L;
}

function initializeUncertaintyPlot(probabilities, canvas) {
    const ctx = canvas.getContext('2d');
    const labels = probabilities.map((_, index) => '');
    const colors = new Array(probabilities.length).fill(INACTIVE_COLOR);
    colors[0] = ACTIVE_COLOR;
    console.log()

    const barChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Uncertainty',
                data: probabilities,
                backgroundColor: colors,
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 1
            }]
        },
        options: {
            indexAxis: 'y',
            scales: {
                x: {
                    beginAtZero: true,
                    max: Math.min(1,Math.max(...probabilities)*1.25),
                    grid: {
                        display: false
                    },
                },
                y: {
                    grid: {
                        display: false
                    },
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(tooltipItems) {
                            return `${(tooltipItems.parsed.x*100).toFixed(2)}%`
                        },
                        title: function(tooltipItem, probabilities) {
                            return "Probability"
                        }
                    }
                },
                legend: {
                    display: false
                }
            }
        }
    });
    canvas.chart = barChart;
}

function updateUncertaintyPlot(index, length, canvas) {
    const chart = canvas.chart;
    const colors = new Array(length).fill(INACTIVE_COLOR);
    colors[index] = ACTIVE_COLOR;
    chart.data.datasets[0].backgroundColor = colors;
    chart.update();
}

