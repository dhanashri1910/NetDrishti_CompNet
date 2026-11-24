
(async function () {
    await window.NP_READY;

    const $ = s => document.querySelector(s);
    const E = NP.esc;

    let graph = null;
    let cy = null;

    // Disable current topology if no network is selected.
    if (!NP.net) {
        const option = $('#rSource').querySelector('[value="net"]');
        if (option) option.disabled = true;
    }

    function label(id) {
        const node = graph.nodes.find(n => n.id === id);
        return node ? node.label : id;
    }

    function pathText(path) {
        return path.map(label).join(' → ');
    }

    // Load network graph.
    async function loadGraph() {
        try {
            const source = $('#rSource').value;

            graph = await NP.api(
                `/api/routing/graph?source=${source}&network=${NP.net || ''}`
            );

            if (!graph.nodes.length) {
                throw new Error('No routers found in this network.');
            }

            const options = graph.nodes.map(n =>
                `<option value="${E(n.id)}">${E(n.label)}</option>`
            ).join('');

            $('#rSrc').innerHTML = options;
            $('#rDst').innerHTML = options;

            if (graph.nodes.length > 1) {
                $('#rDst').selectedIndex = graph.nodes.length - 1;
            }

            $('#rFail').innerHTML = graph.edges.map(edge => `
                <label class="chip">
                    <input type="checkbox"
                           value="${E(edge.a + '-' + edge.b)}">
                    ${E(label(edge.a))} – ${E(label(edge.b))}
                </label>
            `).join('');

            drawGraph();

            $('#rOut').innerHTML =
                'Select two routers and click Find Best Route.';

        } catch (error) {
            $('#rOut').innerHTML =
                `<div class="text-danger">${E(error.message)}</div>`;
        }
    }

    // Draw network graph.
    function drawGraph(path = [], failed = []) {
        if (!graph) return;

        const elements = graph.nodes.map(n => ({
            data: {
                id: n.id,
                label: n.label
            }
        }));

        graph.edges.forEach(edge => {
            elements.push({
                data: {
                    id: edge.a + '-' + edge.b,
                    source: edge.a,
                    target: edge.b,
                    weight: edge.cost,
                    down: edge.up === false ||
                        failed.includes(edge.a + '-' + edge.b)
                }
            });
        });

        if (cy) cy.destroy();

        cy = cytoscape({
            container: $('#rCy'),
            elements: elements,
            layout: {
                name: 'cose',
                animate: false,
                padding: 25
            },
            style: [
                {
                    selector: 'node',
                    style: {
                        label: 'data(label)',
                        color: '#ffffff',
                        'background-color': '#3b5bdb',
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'font-size': 12,
                        width: 38,
                        height: 38
                    }
                },
                {
                    selector: 'edge',
                    style: {
                        label: 'data(weight)',
                        color: '#9fb2e8',
                        'font-size': 11,
                        width: 2.5,
                        'line-color': '#3b5bdb',
                        'text-background-color': '#0b1224',
                        'text-background-opacity': 1
                    }
                },
                {
                    selector: 'edge[?down]',
                    style: {
                        'line-color': '#ef4444',
                        'line-style': 'dashed'
                    }
                },
                {
                    selector: '.best',
                    style: {
                        'line-color': '#22d3ee',
                        width: 5
                    }
                },
                {
                    selector: 'node.best',
                    style: {
                        'background-color': '#06b6d4'
                    }
                }
            ]
        });

        // Highlight recommended route.
        for (let i = 0; i < path.length - 1; i++) {
            const first = cy.getElementById(path[i]);
            const second = cy.getElementById(path[i + 1]);

            first.addClass('best');
            second.addClass('best');

            first.edgesWith(second).addClass('best');
        }
    }

    // Routing table.
    function makeTable(rows, destination) {
        return `
            <div class="table-responsive">
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th>Router</th>
                            <th>Next router</th>
                            <th>Total cost</th>
                            <th>Hops</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map(row => `
                            <tr class="${row.dest === destination ? 'table-active' : ''}">
                                <td>${E(label(row.dest))}</td>
                                <td>${row.next_hop
                                    ? E(label(row.next_hop))
                                    : '—'}</td>
                                <td>${row.cost ?? 'Unreachable'}</td>
                                <td>${row.hops ?? '—'}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    // Display Dijkstra results only.
    function showResult(data, destination, heading, failed) {
        const dijkstra = data.dijkstra;
        const route = dijkstra.route;

        let html = `
            <div class="card-np p-3 mb-3">
                <h2>${heading}</h2>
        `;

        if (!route || route.cost === null) {
            html += `
                <div class="text-danger mt-3">
                    <h4>Destination unreachable</h4>
                    No available route connects these routers.
                </div>
            `;
        } else {
            const recommended = data.best_path || route;

            html += `
                <div class="mt-3">
                    <div class="small text-secondary">
                        Recommended route
                    </div>

                    <h3 class="text-info mt-2">
                        ${E(pathText(recommended.path))}
                    </h3>
                </div>

                <div class="row g-3 mt-2 mb-3">
                    <div class="col-4">
                        <div class="card-np p-2">
                            <h3>${recommended.cost}</h3>
                            <small class="text-secondary">Total cost</small>
                        </div>
                    </div>

                    <div class="col-4">
                        <div class="card-np p-2">
                            <h3>${recommended.hops}</h3>
                            <small class="text-secondary">Hops</small>
                        </div>
                    </div>

                    <div class="col-4">
                        <div class="card-np p-2">
                            <h3>${dijkstra.work.heap_pops}</h3>
                            <small class="text-secondary">Processing steps</small>
                        </div>
                    </div>
                </div>

                <div class="alert alert-success">
                    <strong>Best route found!</strong>
                    Dijkstra selected the lowest-cost available path.
                </div>
            `;
        }

        html += `
                <h3 class="h5 mt-3">Routing table</h3>
                <p class="small text-secondary">
                    Shows the best next router for each destination.
                </p>

                ${makeTable(dijkstra.table, destination)}
            </div>
        `;

        return html;
    }

    // Compute best route.
    $('#rGo').onclick = async function () {
        const src = $('#rSrc').value;
        const dst = $('#rDst').value;

        if (!src || !dst || src === dst) {
            $('#rOut').innerHTML =
                '<div class="text-warning">Please select two different routers.</div>';
            return;
        }

        const failed = [
            ...document.querySelectorAll('#rFail input:checked')
        ].map(input => input.value);

        const button = $('#rGo');
        button.disabled = true;
        button.textContent = 'Finding best route...';

        try {
            const response = await NP.api('/api/routing/compute', {
                json: {
                    source: $('#rSource').value,
                    network: NP.net,
                    src: src,
                    dst: dst,
                    fail: failed
                }
            });

            const result = response.result;

            let html = showResult(
                result.before,
                dst,
                'Best Route',
                []
            );

            let bestPath =
                result.before.best_path?.path ||
                result.before.dijkstra.route?.path ||
                [];

            if (result.after) {
                const afterRoute = result.after.dijkstra.route;
                const beforeRoute = result.before.dijkstra.route;

                html += showResult(
                    result.after,
                    dst,
                    'After Link Failure',
                    failed
                );

                html = `
                    <div class="card-np p-3 mb-3">
                        <h2>Network changes</h2>

                        ${afterRoute && afterRoute.cost !== null
                            ? `
                                <p>Old route cost:
                                    <strong>${beforeRoute?.cost ?? '∞'}</strong>
                                </p>
                                <p>New route cost:
                                    <strong>${afterRoute.cost}</strong>
                                </p>
                                <p class="text-success">
                                    The network found an alternative route.
                                </p>
                            `
                            : `
                                <p class="text-danger">
                                    The destination is unreachable after this failure.
                                </p>
                            `
                        }
                    </div>
                ` + html;

                bestPath =
                    result.after.best_path?.path ||
                    afterRoute?.path ||
                    [];
            }

            $('#rOut').innerHTML = html;

            drawGraph(bestPath, failed);

        } catch (error) {
            $('#rOut').innerHTML =
                `<div class="text-danger">Error: ${E(error.message)}</div>`;
        } finally {
            button.disabled = false;
            button.innerHTML = '<i class="fa-solid fa-route"></i> Find Best Route';
        }
    };

    $('#rSource').onchange = loadGraph;

    // Initial graph.
    loadGraph();

})();
